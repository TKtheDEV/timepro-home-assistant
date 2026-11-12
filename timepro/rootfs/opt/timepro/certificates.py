#!/usr/bin/env python3
"""Reload nginx after a valid /ssl renewal; keep the last working TLS config."""
import json
from pathlib import Path
import signal
import subprocess
import threading


def signature(paths):
    return tuple((s.st_ino,s.st_mtime_ns,s.st_size) for p in paths for s in [p.stat()])


def refresh(paths, previous):
    current = signature(paths)
    if current == previous:
        return previous
    # Never reload half-written, mismatched or invalid certificate/key files.
    check = subprocess.run(['nginx','-c','/run/timepro/nginx.conf','-t'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if check.returncode:
        print('TimePRO TLS files changed but validation failed; keeping the active certificate.',flush=True)
        return previous
    reload = subprocess.run(['nginx','-c','/run/timepro/nginx.conf','-s','reload'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if reload.returncode:
        return previous
    print('TimePRO reloaded its renewed TLS certificate.',flush=True)
    return current


def main():
    stop = threading.Event()
    for sig in [signal.SIGTERM,signal.SIGINT]:
        signal.signal(sig,lambda *_: stop.set())
    config = json.loads(Path('/run/timepro/options.json').read_text())
    if config['phone_access'] != 'tls':
        stop.wait()
        return
    paths = [Path('/ssl')/config[key] for key in ['certfile','keyfile']]
    previous = signature(paths)
    while not stop.wait(60):
        try:
            previous = refresh(paths, previous)
        except OSError:
            print('TimePRO is waiting for complete TLS renewal files; the planner remains running.',flush=True)


if __name__ == '__main__': main()
