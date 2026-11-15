"""Fresh before/after filter comparison using separately compiled policy bridges.

Same worker/schema/persona/output policies. Each bridge owns its actual bounded
dialogue history. Frozen-history probes isolate retrieval from prior-answer drift.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from run_comparison import linux


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['output','previous','policy-classes','jdk','model','schema']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    a.output.mkdir(parents=True,exist_ok=False)
    bridge_dir=a.output/'bridge-after';bridge_dir.mkdir()
    old_cp=(a.previous/'bridge/classpath.local.txt').read_text(encoding='utf-8').strip()
    pieces=old_cp.split(';')
    jsonjar=next(x for x in pieces if x.endswith('android-json-ordered.jar'))
    stdlib=next(x for x in pieces if x.endswith('kotlin-stdlib-2.1.0.jar'))
    after_cp=';'.join([str(bridge_dir.resolve()),str(a.policy_classes.resolve()),jsonjar,stdlib])
    subprocess.run([str(a.jdk/'bin/javac.exe'),'-encoding','UTF-8','-cp',after_cp,'-d',str(bridge_dir),str(root/'training/pc-match/RouteBridge.java')],check=True)
    (bridge_dir/'classpath.local.txt').write_text(after_cp,encoding='utf-8')
    bridges={condition:subprocess.Popen([str(a.jdk/'bin/java.exe'),'-Dfile.encoding=UTF-8','-cp',cp,'ai.chloe.pc.RouteBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8') for condition,cp in [('before',old_cp),('after',after_cp)]}

    def call(condition,request):
        b=bridges[condition];b.stdin.write(json.dumps(request,ensure_ascii=False)+'\n');b.stdin.flush()
        line=b.stdout.readline()
        if not line:raise RuntimeError('Policy bridge exited: '+condition)
        result=json.loads(line)
        if 'error' in result:raise RuntimeError(result['error'])
        return result

    previous=[json.loads(s) for s in (a.previous/'results.local.jsonl').read_text(encoding='utf-8').splitlines()]
    current=[r for r in previous if r['route']=='current'];assert len(current)==104
    gates=[]
    for r in current:
        # Stateless replay audit only: never seed new dialogue sessions with old answers.
        request={k:v for k,v in r.items() if k not in ['session','native','app']}
        b=call('before',dict(request,op='prepare'));c=call('after',dict(request,op='prepare'))
        assert b['actual_messages']==r['actual_messages'],r['id']
        assert b['actual_messages'][0]==c['actual_messages'][0],r['id']
        consumed=call('before',dict(request,op='consume',raw=r['native']['raw']))
        assert consumed['delivered_spoken']==r['app']['delivered_spoken'] and consumed['blocked']==r['app']['blocked']
        gates.append(dict(id=r['id'],before_messages=len(b['actual_messages']),after_messages=len(c['actual_messages']),changed=b['actual_messages']!=c['actual_messages']))
    tasks=[]
    for i,r in enumerate(current):
        task={k:r[k] for k in ['source_id','cohort','input','register']}
        task.update({k:r[k] for k in ['session','turn','topic','expectation'] if k in r})
        if 'session' not in task:task['messages']=r['messages']
        for condition in (['before','after'] if i%2==0 else ['after','before']):
            tasks.append(dict(task,id=condition+'-'+r['source_id'],route='current',condition=condition))
    for index,ident in enumerate(['current-dialog02-t2','current-dialog02-t5']):
        r=next(x for x in current if x['id']==ident)
        for condition in (['before','after'] if index%2==0 else ['after','before']):
            tasks.append(dict(id=condition+'-fixed-'+r['source_id'],source_id='fixed-'+r['source_id'],cohort='fixed_history_probe',condition=condition,route='current',messages=r['messages'],input=r['input'],register=r['register'],expectation=r['expectation']))
    assert len(tasks)==212
    policy=root/'app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java'
    snapshot=root/'training/snapshots/relevance-filter-20261115/GroundedConversationPolicy.before.java.txt'
    before=snapshot.read_text(encoding='utf-8');after=policy.read_text(encoding='utf-8')
    assert before.split('    private static boolean relevantHistory')[0]==after.split('    public static final String RELEVANCE_VERSION')[0]
    assert before.split('    private static JSONArray modelView')[1]==after.split('    private static JSONArray modelView')[1]
    paths=[policy,snapshot,root/'training/pc-match/compare_relevance.py',root/'training/pc-match/RouteBridge.java',root/'training/pc-match/worker.cpp',a.schema]
    paths += list((root/'app/src/main/java/ai/chloe/voicelab/conversation').glob('*Policy.java'))
    paths += [root/'app/src/main/java/ai/chloe/voicelab/conversation/ConversationEngine.kt',root/'training/configs/route-ablation-new-cases.json']
    model_hash=hashlib.sha256()
    with a.model.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):model_hash.update(chunk)
    assert model_hash.hexdigest()=='00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'
    plan=dict(base_commit='4d2e4881f1569a6533bf3c272f75fd7d3b45ab1a',model_sha256=model_hash.hexdigest(),training_steps=0,native_requests=212,main_requests=208,fixed_history_probes=4,
              change='Only relevanceHistory/helpers. Fact extraction, reply resolution, system construction, persona, schema, native worker and all output policies unchanged.',
              cohorts=dict(known=54,new_single=20,dialogue_turns=30,fixed_history_probe_questions=2),
              system='Known54 retains prior frozen system; new20/dialogues use actual PersonaManager. Compare conditions only within cohort.',
              generation=dict(temperature=0,seed=42,context_tokens=2048,max_generation_tokens=384,threads=4,thinking=False,gpu_layers=99),
              dialogue_history='Each independent bridge uses actual manager and own delivered speech, max4 pairs/1200 UTF16 chars; scripted same user turns. No prior outputs added.',
              source_hashes={str(x.resolve().relative_to(root)).replace('\\','/'):sha(x) for x in paths},
              baseline_input_and_consumption_parity=104,common_history_system_bytes_unchanged=104,
              judge='Direct GPT six-criterion review; exact context/speech labels may be reused with provenance. Known development questions, same author, visible conditions; not blind/independent/human/holdout.')
    for name,data in [('plan.local.json',plan),('tasks.local.json',tasks),('preflight.local.json',gates)]:
        (a.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    runtime='/home/chloetrain/chloe-pc-4b-20261115'
    libraries='/home/chloetrain/CHLOE/.venv-llm/lib/python3.12/site-packages/nvidia/cublas/lib:'+runtime+'/cuda/lib64:/usr/lib/wsl/lib'
    with (a.output/'results.local.jsonl').open('x',encoding='utf-8') as output,(a.output/'native.stderr.log').open('xb') as errors:
        worker=subprocess.Popen(['wsl.exe','-d','CHLOE-Training-24.04','-u','chloetrain','--','env','LD_LIBRARY_PATH='+libraries,'CUDA_VISIBLE_DEVICES=0','CUBLAS_WORKSPACE_CONFIG=:4096:8',runtime+'/build/chloe_pc',linux(a.model),linux(a.schema),'99'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8')
        incoming=queue.Queue()
        def reader():
            for line in worker.stdout:incoming.put(line)
            incoming.put(None)
        threading.Thread(target=reader,daemon=True).start()
        try:
            for index,task in enumerate(tasks,1):
                condition=task['condition'];prepared=call(condition,dict(task,op='prepare'));start=time.monotonic()
                worker.stdin.write(json.dumps(dict(id=task['id'],messages=prepared['actual_messages']),ensure_ascii=False)+'\n');worker.stdin.flush()
                line=incoming.get(timeout=240)
                if line is None:raise RuntimeError('Native worker exited')
                native=json.loads(line)
                if 'error' in native:raise RuntimeError(native['error'])
                assert native['id']==task['id']
                consumed=call(condition,dict(task,**prepared,op='consume',raw=native['result']['raw']))
                record=dict(task,**{k:v for k,v in prepared.items() if k not in task},native=native['result'],app=consumed,elapsed_ms=(time.monotonic()-start)*1000)
                output.write(json.dumps(record,ensure_ascii=False)+'\n');output.flush()
                print(json.dumps(dict(completed=index,total=len(tasks),id=task['id'],status=native['result']['native_parse_status'],blocked=consumed['blocked'])),flush=True)
        finally:
            worker.stdin.close();worker.wait(timeout=30)
            for bridge in bridges.values():bridge.stdin.close();bridge.wait(timeout=30)
        assert worker.returncode==0 and all(b.returncode==0 for b in bridges.values())
    (a.output/'GENERATION-COMPLETE.local.json').write_text(json.dumps(dict(generations=212,worker_exit_code=0,bridge_exit_codes=[b.returncode for b in bridges.values()])),encoding='utf-8')


if __name__=='__main__':main()
