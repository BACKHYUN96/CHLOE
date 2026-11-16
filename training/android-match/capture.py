from pathlib import Path
import json,subprocess,threading,time,sys
import argparse
from host_ui import command,select_session,configure,PKG
parser=argparse.ArgumentParser(description='Capture one actual PocketPal call per frozen situation in the isolated package')
parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--adb',type=Path,required=True);parser.add_argument('--device',required=True)
parser.add_argument('--start',type=int,default=0);parser.add_argument('--end',type=int,default=54);parser.add_argument('--suite',default='suite.local.json')
options=parser.parse_args();configure(options.artifacts,options.adb,options.device)
from host_ui import ADB,OUT
start=options.start;end=options.end;pid=subprocess.check_output(ADB+['shell','pidof',PKG]).decode().strip();assert pid
log=subprocess.Popen(ADB+['logcat','-v','raw','--pid='+pid,'-T','1','-s','ReactNativeJS:V'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
events=[];partial={};lock=threading.Lock();trace=OUT/('pocket-observer-'+str(start)+'-'+str(time.time_ns())+'.local.jsonl')
def reader():
 with trace.open('xb') as f:
  for line in iter(log.stdout.readline,b''):
   marker=b'CHLOE_MATCH_OBS '
   if b'CHLOE_MATCH_DIAGNOSTIC ' in line:
    try:diagnostic=json.loads(line.split(b'CHLOE_MATCH_DIAGNOSTIC ',1)[1])
    except ValueError:continue
    f.write(json.dumps({'diagnostic':diagnostic},ensure_ascii=False).encode()+b'\n');f.flush()
    with lock:events.append({'event':'diagnostic','name':'grammar_root','id':0,'value':diagnostic})
    continue
   if marker not in line:continue
   try:part=json.loads(line.split(marker,1)[1])
   except ValueError:continue
   f.write(json.dumps(part,ensure_ascii=False).encode()+b'\n');f.flush()
   key=(part['event'],part['name'],part['id']);pieces=partial.setdefault(key,{})
   pieces[part['part']]=part['text']
   if len(pieces)==part['total']:
    try:value=json.loads(''.join(pieces[i] for i in range(part['total'])))
    except (ValueError,KeyError):continue
    with lock:events.append({'event':part['event'],'name':part['name'],'id':part['id'],'value':value})
threading.Thread(target=reader,daemon=True).start()
suite=json.loads((OUT/options.suite).read_text(encoding='utf-8'))
try:
 for row in suite[start:end]:
  dest=OUT/('pocket-'+row['id']+'.local.json')
  if dest.exists():
   print('SKIP recorded',row['id'],flush=True);continue
  with lock:before=len(events)
  subprocess.run(ADB+['shell','input','keyevent','KEYCODE_WAKEUP'],capture_output=True,check=True);time.sleep(.5)
  select_session('MATCH '+row['id'],row['register'])
  r=command('text',text=row['input']);assert r.get('ok'),r;time.sleep(.15)
  r=command('tap',needle='Send');assert r.get('ok'),r
  deadline=time.monotonic()+240;result=None
  while time.monotonic()<deadline:
   with lock:current=list(events[before:])
   result=next((e for e in current if e['name']=='completion' and e['event']=='result'),None)
   error=next((e for e in current if e['name']=='completion' and e['event']=='error'),None)
   if result or error:break
   time.sleep(.3)
  if not result:raise RuntimeError('No completion result '+json.dumps(current[-3:],ensure_ascii=False))
  time.sleep(.4);ui=command('dump');record={'id':row['id'],'events':current,'result':result['value'],'ui':ui}
  dest=OUT/('pocket-'+row['id']+'.local.json');assert not dest.exists();dest.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
  print('COMPLETE',row['id'],json.dumps({'text_length':len(result['value'].get('text') or ''),'content_length':len(result['value'].get('content') or ''),'tokens':result['value'].get('tokens_predicted'),'stopped_eos':result['value'].get('stopped_eos')},ensure_ascii=False),flush=True)
finally:log.terminate();log.wait(timeout=10)
