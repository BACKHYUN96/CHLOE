"""Atomic command transport to the isolated PocketPal instrumentation only."""
from pathlib import Path
import subprocess,json,time,sys,xml.etree.ElementTree as ET,re
OUT=None;ADB=None;PKG='ai.chloe.match.pocketpal'

def configure(artifacts, adb, device):
 global OUT,ADB
 OUT=Path(artifacts).resolve();ADB=[str(adb),'-s',device]
 if not OUT.is_dir():raise ValueError('Artifact directory does not exist')
def command(op,**kw):
 counter=OUT/'driver-seq.local';n=int(counter.read_text()) if counter.exists() else 1
 payload=json.dumps(dict(op=op,**kw),ensure_ascii=False).encode()
 base=f'files/match-driver/cmd-{n}'
 previous=subprocess.run(ADB+['shell','run-as',PKG,'ls','-d',base+'.json',f'files/match-driver/out-{n}.json'],capture_output=True,timeout=10)
 if previous.stdout.strip():raise ValueError('Stale command number; start the driver and local counter in a fresh range')
 subprocess.run(ADB+['shell','-T','run-as',PKG,'tee',base+'.tmp'],input=payload,capture_output=True,check=True,timeout=10)
 subprocess.run(ADB+['shell','run-as',PKG,'mv',base+'.tmp',base+'.json'],capture_output=True,check=True,timeout=10)
 if op=='stop':
  counter.write_text(str(n+1));return {'sent':True}
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  p=subprocess.run(ADB+['shell','run-as',PKG,'cat',f'files/match-driver/out-{n}.json'],capture_output=True)
  if p.returncode==0:
   result=json.loads(p.stdout);counter.write_text(str(n+1));return result
  time.sleep(.15)
 raise TimeoutError(n)


def select_session(label, register, retries=0):
 """Select by current accessibility order, including upward scrolling."""
 import re
 def case_buttons(ui):
  return [(i,n) for i,n in enumerate(ui) if n.get('class')=='android.widget.Button' and str(n.get('desc','')).startswith('MATCH ')]
 def backward(bounds):
  left,top,right,bottom=map(int,re.findall(r'-?[0-9]+',bounds))
  x=(left+right)//2;h=bottom-top
  subprocess.run(ADB+['shell','input','swipe',str(x),str(top+int(h*.2)),str(x),str(top+int(h*.8)),'650'],check=True)
 ui=command('dump').get('ui',[])
 if not any(n.get('visible') for _,n in case_buttons(ui)):
  r=command('tap',needle='Open drawer');time.sleep(.4)
  if not r.get('ok'):r=command('tap',needle='Open drawer');time.sleep(.4)
  if not r.get('ok'):raise RuntimeError(r)
 bounds=None;selected=False
 for attempt in range(30):
  ui=command('dump').get('ui',[]);buttons=case_buttons(ui)
  target=next(((i,n) for i,n in buttons if n.get('desc')==label),None)
  if target and target[1].get('visible'):
   r=command('tap',needle=label)
   if r.get('ok'):selected=True;break
  visible=[i for i,n in buttons if n.get('visible')]
  if not target:raise RuntimeError('Cannot locate frozen session in current drawer')
  if not visible:
   r=command('scroll',needle=label);bounds=r.get('bounds')
   if not r.get('ok') or not bounds:raise RuntimeError(r)
   time.sleep(2.0);continue
  if target[0]<min(visible):
   if bounds is None:
    r=command('scroll',needle=label);bounds=r.get('bounds')
    if not r.get('ok') or not bounds:raise RuntimeError(r)
    backward(bounds)
   backward(bounds)
  else:
   r=command('scroll',needle=label);bounds=r.get('bounds')
   if not r.get('ok') or not bounds:raise RuntimeError(r)
  time.sleep(2.0)
 if not selected:raise RuntimeError('Could not select '+label)
 for attempt in range(20):
  ui=command('dump').get('ui',[])
  header=any(n.get('visible') and n.get('text')==label for n in ui)
  pal=any(n.get('visible') and (n.get('desc')=='Pal: MATCH '+register or n.get('text')=='Pal: MATCH '+register) for n in ui)
  if header and pal and not any(n.get('visible') for _,n in case_buttons(ui)):return
  time.sleep(.2)
 if retries<3:return select_session(label,register,retries+1)
 raise RuntimeError('Selected session/persona did not become active')
