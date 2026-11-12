#!/usr/bin/env python3
"""Validate Supervisor options and prepare private runtime files. No shell templates."""
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATA = Path('/data')
RUN = Path('/run/timepro')


def origin(value):
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith('https://'):
        raise ValueError('public_url must be an HTTPS origin, without a path.')
    if any(c.isspace() or ord(c) < 32 or c in '\\$;{}"\'' for c in value):
        raise ValueError('public_url contains invalid characters.')
    url = urlsplit(value)
    if (not url.hostname or url.username is not None or url.password is not None
            or url.path not in ('', '/') or url.query or url.fragment or '?' in value or '#' in value):
        raise ValueError('public_url must be an HTTPS origin, without a path.')
    host = url.hostname
    try:
        ip = ipaddress.ip_address(host)
        host = f'[{ip.compressed}]' if ip.version == 6 else str(ip)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
            raise ValueError('public_url must contain a valid hostname.') from None
    port = url.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('public_url has an invalid port.')
    return f'https://{host.lower()}' + (f':{port}' if port and port != 443 else '')


def options(raw, ssl_dir=Path('/ssl')):
    timezone = raw.get('initial_timezone', 'America/New_York')
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError('initial_timezone must be a named IANA timezone.') from None
    mode = raw.get('phone_access', 'disabled')
    if mode not in ('disabled', 'tls', 'reverse_proxy'):
        raise ValueError('Choose disabled, tls or reverse_proxy for phone_access.')
    public = raw.get('public_url', '')
    public = origin(public) if public else ''
    if mode != 'disabled' and not public:
        raise ValueError('Set public_url to the HTTPS address phones will use.')
    enabled = raw.get('built_in_model', False)
    threads = raw.get('model_threads', 2)
    if type(enabled) is not bool or type(threads) is not int or not 1 <= threads <= 4:
        raise ValueError('built_in_model must be boolean; model_threads must be 1 to 4.')
    result = dict(phone_access=mode, public_url=public, built_in_model=enabled,
                  model_threads=threads, initial_timezone=timezone)
    for key, default in [('certfile', 'fullchain.pem'), ('keyfile', 'privkey.pem')]:
        name = raw.get(key, default)
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name):
            raise ValueError(f'{key} must be a filename inside /ssl, without directories.')
        if mode == 'tls':
            path = (ssl_dir / name).resolve(strict=True)
            if not path.is_relative_to(ssl_dir.resolve()) or not path.is_file():
                raise ValueError(f'{key} must refer to a file inside /ssl.')
        result[key] = name
    return result


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Refusing a symlink in TimePRO storage.')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError('TimePRO storage must be a directory.')
    path.chmod(0o700)
    os.chown(path, 10001, 10001)


def token_file(path):
    if not path.exists() and not path.is_symlink():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_hex(32) + '\n')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError('Existing owner token must be a private regular file; it was not replaced.')
    value = path.read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Existing owner token is invalid; it was not replaced.')
    os.chown(path, 10001, 10001)


def nginx(config):
    external = ''
    if config['phone_access'] != 'disabled':
        tls = config['phone_access'] == 'tls'
        port = 8443 if tls else 8216
        certificate = (f'ssl_certificate /ssl/{config["certfile"]};\n'
                       f'ssl_certificate_key /ssl/{config["keyfile"]};\n'
                       'ssl_protocols TLSv1.2 TLSv1.3; ssl_session_tickets off;') if tls else ''
        external = f'''
        server {{
            listen [::]:{port} ipv6only=off{' ssl' if tls else ''};
            {certificate}
            # No ingress routes or owner credential injection on the phone listener.
            location /api/ {{
                proxy_pass http://127.0.0.1:8214;
                proxy_set_header Host $host;
                proxy_set_header Authorization $http_authorization;
                proxy_set_header Connection "";
                proxy_read_timeout 75s;
            }}
            location / {{ return 404; }}
        }}'''
    return f'''worker_processes 1;
pid /run/nginx.pid;
error_log /dev/stderr warn;
events {{ worker_connections 128; }}
http {{
    access_log off;
    server_tokens off;
    client_max_body_size 16k;
    client_body_timeout 15s;
    send_timeout 30s;
    keepalive_timeout 15s;
    proxy_connect_timeout 3s;
    proxy_http_version 1.1;
    server {{
        listen [::]:8099 ipv6only=off;
        allow 172.30.32.2;
        deny all;
        location / {{
            proxy_pass http://127.0.0.1:8215;
            proxy_set_header Host $host;
            proxy_set_header Connection "";
            proxy_read_timeout 75s;
        }}
    }}
    {external}
}}
'''


def main():
    os.umask(0o077)
    config = options(json.loads((DATA / 'options.json').read_text()))
    for path in [DATA / 'timepro', DATA / 'models', RUN]:
        private_directory(path)
    token_file(DATA / 'timepro/auth.token')
    (RUN / 'options.json').write_text(json.dumps(config))
    os.chown(RUN / 'options.json', 10001, 10001)
    (RUN / 'timezone').write_text(config['initial_timezone'])
    os.chown(RUN / 'timezone', 10001, 10001)
    (RUN / 'nginx.conf').write_text(nginx(config))
    print('TimePRO storage ready. Hosting mode:', config['phone_access'], flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError):
        # Validation failures must not echo options, credentials or certificate material.
        raise SystemExit('TimePRO setup failed. Check phone_access, public_url, /ssl files and storage permissions. Existing data was kept.') from None
