#!/usr/bin/env python3
"""Opt-in CPU model; pinned weights, verified download, no cloud fallback."""
import hashlib
import json
import os
import platform
from pathlib import Path
import signal
import time
import urllib.request

RUN = Path('/run/timepro/state')
MODELS = Path('/data/models')
NAME = 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
SIZE = 1_117_320_736
SHA256 = '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
URL = ('https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/'
       '91cad51170dc346986eccefdc2dd33a9da36ead9/' + NAME)


def status(state, **extra):
    path = RUN / 'model.tmp'
    path.write_text(json.dumps({'state': state, **extra}))
    path.replace(RUN / 'model.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def available_memory():
    available = 0
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available = int(line.split()[1]) * 1024
    try:
        limit = (Path('/sys/fs/cgroup/memory.max')).read_text().strip()
        used = int(Path('/sys/fs/cgroup/memory.current').read_text())
        if limit != 'max':
            available = min(available, int(limit) - used)
    except (OSError, ValueError):
        pass
    return available


def supported_cpu():
    if platform.machine() not in ('x86_64', 'amd64'):
        return True
    # The portable optimized amd64 bundle targets Haswell-era instructions.
    # Some VM CPU profiles hide these even on a recent physical Intel/AMD host.
    for line in Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith('flags'):
            flags = set(line.partition(':')[2].split())
            return {'sse4_2','avx','avx2','f16c','fma','bmi2'} <= flags
    return False


def model():
    path = MODELS / NAME
    if path.is_symlink():
        raise ValueError('Model path cannot be a symlink.')
    status('checking')
    if path.is_file() and path.stat().st_size == SIZE and digest(path) == SHA256:
        return path
    partial = MODELS / (NAME + '.partial')
    if partial.is_symlink():
        raise ValueError('Partial model path cannot be a symlink.')
    status('downloading', percent=0)
    # Network access happens only after explicit built_in_model opt-in. HTTPS
    # certificate checking remains enabled, including redirected weight storage.
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, partial.open('wb') as stream:
            downloaded = 0
            checksum = hashlib.sha256()
            last_percent = -1
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > SIZE:
                    raise ValueError('Unexpected model size.')
                stream.write(chunk)
                checksum.update(chunk)
                percent = int(downloaded * 100 / SIZE)
                if percent != last_percent:
                    status('downloading', percent=percent)
                    last_percent = percent
            stream.flush()
            os.fsync(stream.fileno())
        if downloaded != SIZE or checksum.hexdigest() != SHA256:
            raise ValueError('Model integrity check failed.')
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def main():
    os.umask(0o077)
    config = json.loads(Path('/run/timepro/options.json').read_text())
    if not config['built_in_model']:
        status('disabled')
        signal.pause()
        return
    if not supported_cpu():
        status('error', message='The local amd64 model needs AVX2, FMA, F16C and BMI2. For a Proxmox HA VM, expose the host CPU features or choose another provider. The planner remains available.')
        signal.pause()
        return
    if available_memory() < 2_500_000_000:
        status('error', message='Local model needs at least 2.5 GB of available memory. Assign more RAM or use another provider, then restart.')
        signal.pause()
        return
    path = model()
    status('starting')
    # Fixed context and parallelism bound CPU/RAM usage; no model listener is
    # exposed outside this container. Model selection remains a user choice.
    os.execv('/usr/local/bin/llama-server', [
        'llama-server', '--host', '127.0.0.1', '--port', '11435',
        '--model', str(path), '--alias', 'timepro-local',
        '--ctx-size', '8192', '--parallel', '1',
        '--threads', str(config['model_threads']), '--threads-batch', str(config['model_threads']),
        '--n-gpu-layers', '0', '--no-webui', '--log-disable',
    ])


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        status('error', message='Local model setup failed. Check disk space and Internet access, then restart to retry. No cloud provider was used.')
        print('TimePRO local model unavailable. The planner and setup page remain running.', flush=True)
        signal.pause()
