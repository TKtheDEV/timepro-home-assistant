#!/usr/bin/env python3
"""Loopback-only HA setup bridge. The owner credential never enters the browser.

Nginx restricts ingress to Supervisor; the separate phone listener cannot reach
this server. Only explicit routes are proxied, with bounded bodies and no CORS.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading

ROOT = Path('/opt/timepro/web')
RUN = Path('/run/timepro')
TOKEN = Path('/data/timepro/auth.token')
MAX_BODY = 16_384
MAX_REPLY = 2 * 1024 * 1024
ROUTES = {
    ('GET', '/setup/state'): '/api/v2/companion/state',
    ('GET', '/setup/config'): '/api/v1/state',
    ('GET', '/setup/devices'): '/api/v1/devices',
    ('PUT', '/setup/provider'): '/api/v1/provider',
    ('PUT', '/setup/language'): '/api/v2/companion/preferences',
    ('PUT', '/setup/calendar'): '/api/v1/calendar/connection',
    ('POST', '/setup/calendars'): '/api/v1/calendar/discover',
    ('POST', '/setup/sync'): '/api/v1/calendar/sync',
}


def api(method, path, body=None, timeout=70):
    token = TOKEN.read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', token):
        raise OSError('Invalid private credential.')
    # http.client bypasses proxy environment variables for this fixed loopback target.
    connection = http.client.HTTPConnection('127.0.0.1', 8214, timeout=timeout)
    try:
        connection.request(method, path, body=body,
                           headers={'Authorization': 'Bearer ' + token,
                                    'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(MAX_REPLY + 1)
        if len(data) > MAX_REPLY:
            raise OSError('Response limit exceeded.')
        return response.status, data
    finally:
        connection.close()


def status():
    config = json.loads((RUN / 'options.json').read_text())
    model = {'state': 'disabled'}
    if config['built_in_model']:
        try:
            model = json.loads((RUN / 'state/model.json').read_text())
        except (OSError, ValueError):
            model = {'state': 'starting'}
        try:
            connection = http.client.HTTPConnection('127.0.0.1', 11435, timeout=1)
            try:
                connection.request('GET', '/health')
                if connection.getresponse().status == 200:
                    model = {'state': 'ready'}
            finally:
                connection.close()
        except (OSError, http.client.HTTPException):
            if model.get('state') == 'ready':
                model = {'state': 'starting'}
    return {'phone_access': config['phone_access'], 'public_url': config['public_url'],
            'built_in_model': config['built_in_model'], 'model': model}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    slots = threading.BoundedSemaphore(8)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        print('TimePRO setup request failed; no credentials were logged.', flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = 'TimePRO'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass  # Paths and bodies can contain sensitive setup information.

    def reply(self, status_code, data, content_type='application/json'):
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src blob:; base-uri 'none'; frame-ancestors 'self'; form-action 'none'; object-src 'none'")
        self.end_headers()
        self.wfile.write(data)

    def error(self, code, message):
        self.reply(code, json.dumps({'error': message}).encode())

    def dispatch(self):
        path = self.path
        if self.command == 'GET' and path in ('/', '/app.js', '/style.css'):
            filename, content_type = {
                '/': ('index.html', 'text/html; charset=utf-8'),
                '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                '/style.css': ('style.css', 'text/css; charset=utf-8'),
            }[path]
            self.reply(200, (ROOT / filename).read_bytes(), content_type)
            return
        if self.command == 'GET' and path == '/health':
            code, _ = api('GET', '/api/v1/state', timeout=3)
            self.reply(200 if code == 200 else 503, b'{"service":"timepro"}')
            return
        # A custom header on every privileged read/write blocks cross-origin
        # forms and fetches. No Access-Control-Allow-* headers are ever returned.
        if self.headers.get('X-TimePRO-Setup') != '1':
            self.error(403, 'Open TimePRO through Home Assistant.')
            return
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.error(403, 'Open TimePRO through Home Assistant.')
            return
        body = None
        if self.command != 'GET':
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                self.error(415, 'Use JSON for setup requests.')
                return
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,6}', lengths[0]):
                self.error(400, 'A bounded request body is required.')
                return
            length = int(lengths[0])
            if length > MAX_BODY:
                self.error(413, 'Setup request is too large.')
                return
            body = self.rfile.read(length)
            try:
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                self.error(400, 'Enter valid setup details.')
                return
        if self.command == 'GET' and path == '/setup/status':
            self.reply(200, json.dumps(status()).encode())
        elif self.command == 'POST' and path == '/setup/pair':
            config = status()
            if config['phone_access'] == 'disabled' or not config['public_url']:
                self.error(409, 'Configure HTTPS phone access in the add-on options first.')
                return
            code, data = api('POST', '/api/v1/pairing/qr', json.dumps({'origin': config['public_url']}).encode())
            self.reply(code, data)
        elif self.command == 'DELETE' and re.fullmatch(r'/setup/devices/[0-9a-f-]{36}', path):
            code, data = api('DELETE', path.replace('/setup/', '/api/v1/', 1), body)
            self.reply(code, data)
        elif (self.command, path) in ROUTES:
            code, data = api(self.command, ROUTES[(self.command, path)], body)
            self.reply(code, data)
        else:
            self.error(404, 'Unknown setup action.')

    def handle_request(self):
        try:
            self.dispatch()
        except (OSError, ValueError, http.client.HTTPException):
            self.error(503, 'TimePRO is starting or unavailable. Check the add-on log, then retry.')

    do_GET = do_POST = do_PUT = do_DELETE = handle_request


if __name__ == '__main__':
    Server(('127.0.0.1', 8215), Handler).serve_forever(poll_interval=0.5)
