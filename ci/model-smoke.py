"""Exercise a portable CPU model against the released planner, without saving work."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import uuid

MODEL_URL = ('https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/'
             '91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_0.gguf')
MODEL_SHA = 'dcd819ff094852c38faba6873d8ff0c9d51eadb2844539e52042ae5d647bbfdb'
RUNTIME_URL = ('https://github.com/TKtheDEV/timepro-home-assistant/releases/download/'
               'v0.1.0/timepro-ha-amd64.tar.gz')
RUNTIME_SHA = '79bdacfe8f15c678bbe2d91afabeca0f985bec22dbf7daf8ced241120a2c8da7'


def download(url, path, checksum):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url,timeout=60) as response, path.open('wb') as stream:
        while chunk := response.read(1024*1024):
            digest.update(chunk); stream.write(chunk)
    assert digest.hexdigest() == checksum, 'Download integrity check failed'


def api(port, path, method='GET', payload=None, token=None):
    connection = http.client.HTTPConnection('127.0.0.1',port,timeout=80)
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization'] = 'Bearer '+token
    try:
        connection.request(method,path,json.dumps(payload).encode() if payload is not None else None,headers)
        response = connection.getresponse()
        data = response.read(1024*1024)
        return response.status, json.loads(data)
    finally: connection.close()


def wait(port, path, token=None):
    end = time.monotonic()+120
    while time.monotonic()<end:
        try:
            if api(port,path,token=token)[0]==200:return
        except (OSError,ValueError,http.client.HTTPException):pass
        time.sleep(1)
    raise AssertionError('Service startup timed out')


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); model=root/'model.gguf'; runtime=root/'runtime.tar.gz'
        print('Downloading pinned test weights and released planner.',flush=True)
        download(MODEL_URL,model,MODEL_SHA);download(RUNTIME_URL,runtime,RUNTIME_SHA)
        server=root/'timepro-server'
        with tarfile.open(runtime,'r:gz') as tar:
            server.write_bytes(tar.extractfile('usr/local/bin/timepro-server').read())
        server.chmod(0o755)
        data=root/'data';data.mkdir(mode=0o700)
        children=[]
        try:
            children.append(subprocess.Popen(['/build/bin/llama-server','--host','127.0.0.1','--port','11435',
                '--model',str(model),'--alias','timepro-local','--ctx-size','8192','--parallel','1',
                '--threads','2','--threads-batch','2','--n-gpu-layers','0','--no-webui','--log-disable']))
            wait(11435,'/health')
            env={**os.environ,'TIMEPRO_DATA_DIR':str(data),'TIMEPRO_BIND':'127.0.0.1:8214',
                 'TIMEPRO_INITIAL_TIMEZONE':'America/New_York','TIMEPRO_MODE':'personal'}
            children.append(subprocess.Popen([str(server)],env=env))
            end=time.monotonic()+10
            while not (data/'auth.token').exists() and time.monotonic()<end:time.sleep(.1)
            token=(data/'auth.token').read_text().strip()
            wait(8214,'/api/v1/state',token)
            assert api(8214,'/api/v1/provider','PUT',{'provider':'open_ai_compatible',
                'endpoint':'http://127.0.0.1:11435/v1','model':'timepro-local','allow_local_http':True},token)[0]==200
            _,state=api(8214,'/api/v2/companion/state',token=token)
            started=time.monotonic()
            code,result=api(8214,'/api/v2/companion/turn','POST',{
                'text':'I need one hour of physics homework by tomorrow.','conversation_id':'main',
                'expected_conversation_revision':state['conversation_revision'],'request_id':str(uuid.uuid4())},token)
            elapsed=round(time.monotonic()-started,2)
            assert code==200,(code,result)
            assert result['review'] and result['state']['tasks']==[], result
            print(json.dumps({'portable_model_turn':'passed','cold_seconds':elapsed,'saved_tasks':0}),flush=True)
            assert api(8214,'/api/v2/companion/turn','POST',{'text':'cancel','conversation_id':'main',
                'expected_conversation_revision':result['state']['conversation_revision'],'request_id':str(uuid.uuid4())},token)[0]==200
        finally:
            for child in children:child.send_signal(signal.SIGTERM)
            for child in children:
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
