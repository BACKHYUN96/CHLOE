"""Fresh isolated WSL CPU/CUDA inference plus production JVM reply consumption."""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading
import time


def linux(path):
    p=path.resolve().as_posix()
    assert len(p)>2 and p[1]==':',p
    return '/mnt/'+p[0].lower()+p[2:]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['input','output','model','schema','bridge-classpath','jdk']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--backend',choices=['cpu','cuda'],required=True)
    p.add_argument('--distro',default='CHLOE-Training-24.04')
    p.add_argument('--runtime-root',default='/home/chloetrain/chloe-pc-4b-20261115')
    p.add_argument('--training-root',default='/home/chloetrain/CHLOE')
    a=p.parse_args();rows=json.loads(a.input.read_text(encoding='utf-8-sig'))
    cp=a.bridge_classpath.read_text(encoding='utf-8')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    stderr_path=a.output.with_suffix('.stderr.log')
    bridge=subprocess.Popen([str(a.jdk/'bin/java.exe'),'-Dfile.encoding=UTF-8','-cp',cp,'ai.chloe.pc.PcPolicyBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
    libraries=a.training_root+'/.venv-llm/lib/python3.12/site-packages/nvidia/cublas/lib:'+a.runtime_root+'/cuda/lib64:/usr/lib/wsl/lib'
    with a.output.open('x',encoding='utf-8') as output,stderr_path.open('xb') as errors:
        worker=subprocess.Popen(['wsl.exe','-d',a.distro,'-u','chloetrain','--','env','LD_LIBRARY_PATH='+libraries,'CUDA_VISIBLE_DEVICES=0','CUBLAS_WORKSPACE_CONFIG=:4096:8',a.runtime_root+'/build/chloe_pc',linux(a.model),linux(a.schema),'99' if a.backend=='cuda' else '0'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8')
        incoming=queue.Queue()
        def reader():
            for line in worker.stdout:incoming.put(line)
            incoming.put(None)
        threading.Thread(target=reader,daemon=True).start()
        try:
            for index,row in enumerate(rows):
                started=time.monotonic();worker.stdin.write(json.dumps(dict(id=row['id'],messages=row['actual_messages']),ensure_ascii=False)+'\n');worker.stdin.flush()
                line=incoming.get(timeout=240)
                if line is None:raise RuntimeError('Native worker exited; inspect isolated stderr log')
                native=json.loads(line)
                if 'error' in native:raise RuntimeError(native['error'])
                assert native['id']==row['id']
                bridge.stdin.write(json.dumps(dict(row,raw=native['result']['raw']),ensure_ascii=False)+'\n');bridge.stdin.flush()
                consumed=json.loads(bridge.stdout.readline());assert 'error' not in consumed,consumed
                record=dict(row,backend=a.backend,native=native['result'],app=consumed,elapsed_ms=(time.monotonic()-started)*1000)
                output.write(json.dumps(record,ensure_ascii=False)+'\n');output.flush()
                print(json.dumps(dict(completed=index+1,total=len(rows),id=row['id'],native_status=native['result']['native_parse_status'],consumer_status=consumed['consumer_failure_code'],elapsed_ms=round(record['elapsed_ms'],1))),flush=True)
        finally:
            worker.stdin.close();worker.wait(timeout=30)
            bridge.stdin.close();bridge.wait(timeout=30)
        assert worker.returncode==0 and bridge.returncode==0


if __name__=='__main__':main()
