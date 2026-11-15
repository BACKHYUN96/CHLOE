"""Experiment preparation for the two preserved installed APK versions.
Source databases must come from a newly created comparison package, never the user's PocketPal.
Output files are new local copies; no device commands, model downloads or training are executed.
"""
from pathlib import Path
import sqlite3,json,zipfile,time,shutil,hashlib,sys
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from matched_app_suite import build_suite
parser=argparse.ArgumentParser(description='Seed fresh, synthetic-only isolated PocketPal SQLite copies. Does not touch any phone.')
parser.add_argument('--fresh-async-storage',type=Path,required=True);parser.add_argument('--fresh-chat-db',type=Path,required=True)
parser.add_argument('--chloe-apk',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args();root=Path(__file__).resolve().parents[2];out=options.output.resolve();out.mkdir(parents=True,exist_ok=False)
pkg='ai.chloe.match.pocketpal';plan=json.loads((root/'training/configs/matched-apps-plan.json').read_text(encoding='utf-8'));suite=build_suite()
source=sqlite3.connect('file:'+str(options.fresh_chat_db.resolve())+'?mode=ro',uri=True)
assert source.execute('select count(*) from chat_sessions').fetchone()[0]==0, 'Refusing a nonempty chat database'
source.close()
(out/'suite.local.json').write_text(json.dumps(suite,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(options.chloe_apk) as z:schema=json.loads(z.read('assets/conversation-schema.json'))
(out/'schema.local.json').write_text(json.dumps(schema,ensure_ascii=False),encoding='utf-8')
rk=out/'pocket-configured-rk.sqlite';shutil.copy2(options.fresh_async_storage,rk);db=sqlite3.connect(rk)
m=json.loads(db.execute('select value from catalystLocalStorage where key=?',('ModelStore',)).fetchone()[0]);template=m['models'][0]
settings=dict(template['completionSettings']);settings.update(plan['generation']);settings['response_format']={'type':'json_schema','json_schema':{'name':'chloe','strict':True,'schema':schema}};settings.pop('prompt',None);settings['stop']=[]
model=dict(template,id='chloe-match-4b',author='',name='MATCH Qwen3.5 4B',filename='4b.gguf',fullPath='/data/user/0/'+pkg+'/files/conversation-models/4b.gguf',size=2740937888,isLocal=True,origin='local',isDownloaded=True,downloadUrl='',hfUrl='',progress=0,params=4000000000,completionSettings=settings,defaultCompletionSettings=settings)
model.pop('hfModelFile',None);model['chatTemplate']={**template['chatTemplate'],'systemPrompt':plan['personas']['polite']};model['defaultChatTemplate']=model['chatTemplate'];m['models']=[model];m['lastUsedModelId']=model['id'];m['useAutoRelease']=False
m['contextInitParams'].update({k:plan['generation'][k] for k in ['n_ctx','n_batch','n_ubatch','n_threads','n_gpu_layers']});m['contextInitParams'].update(use_mmap='true',speculativeEnabled=False)
db.execute('update catalystLocalStorage set value=? where key=?',(json.dumps(m,ensure_ascii=False),'ModelStore'))
u=json.loads(db.execute('select value from catalystLocalStorage where key=?',('UIStore',)).fetchone()[0]);u['hasCompletedOnboarding']=True;db.execute('update catalystLocalStorage set value=? where key=?',(json.dumps(u),'UIStore'));db.commit();db.close()
main=out/'pocket-configured.sqlite';shutil.copy2(options.fresh_chat_db,main);db=sqlite3.connect(main);now=int(time.time()*1000)
def insert(table,values):
 columns=[x[1] for x in db.execute('pragma table_info('+table+')')];row={c:None for c in columns};row.update(_changed='',_status='synced');row.update(values)
 db.execute('insert into '+table+' ('+','.join('"'+c+'"' for c in row)+') values ('+','.join('?' for c in row)+')',list(row.values()))
for register,persona in plan['personas'].items():
 insert('local_pals',dict(id='match-'+register,name='MATCH '+register,description='Synthetic local comparison',system_prompt=persona,original_system_prompt='',is_system_prompt_changed=False,use_ai_prompt=False,default_model=json.dumps(model),parameters='{}',parameter_schema='[]',capabilities='[]',categories='[]',tags='[]',source='local',is_owned=True,generation_settings=json.dumps(settings),created_at=now,updated_at=now))
for index,row in enumerate(suite):
 insert('chat_sessions',dict(id=row['id'],title='MATCH '+row['id'],date='2026-11-15T00:00:00.000Z',active_pal_id='match-'+row['register'],settings_source='custom',pinned=False,created_at=now-index,updated_at=now-index))
 insert('completion_settings',dict(id='settings-'+row['id'],session_id=row['id'],settings=json.dumps(settings),created_at=now,updated_at=now))
 for j,msg in enumerate(row['messages'][1:-1]):
  author={'id':'y9d7f8pgn','firstName':'User'} if msg['role']=='user' else {'id':'h3o3lc5xj','firstName':'Assistant'}
  insert('messages',dict(id=f'{row["id"]}-history-{j}',session_id=row['id'],author=author['id'],text=msg['content'],type='text',created_at=now-10000+j,metadata=json.dumps({'authorData':author}),position=j))
insert('global_settings',dict(id='match-global',key='newChatCompletionSettings',value=json.dumps(settings),created_at=now,updated_at=now))
db.commit();db.close()
print('Fresh synthetic seed created:',out)
