"""Compile the JVM bridge and verify exact Android input/consumption vectors."""
import argparse
import json
from pathlib import Path
import subprocess


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['artifacts','jdk','policy-classes','json-jar','stdlib']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2];out=a.artifacts/'bridge-ordered';out.mkdir(exist_ok=False)
    cp=';'.join(str(x.resolve()) for x in [out,a.policy_classes,a.json_jar,a.stdlib])
    subprocess.run([str(a.jdk/'bin/javac.exe'),'-encoding','UTF-8','-cp',cp,'-d',str(out),str(root/'training/pc-match/PcPolicyBridge.java')],check=True)
    (out/'classpath.local.txt').write_text(cp,encoding='utf-8')
    process=subprocess.Popen([str(a.jdk/'bin/java.exe'),'-Dfile.encoding=UTF-8','-cp',cp,'ai.chloe.pc.PcPolicyBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
    def call(x):
        process.stdin.write(json.dumps(x,ensure_ascii=False)+'\n');process.stdin.flush()
        r=json.loads(process.stdout.readline());assert 'error' not in r,r;return r
    try:
        previous=a.artifacts.parent/'reply-integrity-20261115'
        inputs=read(previous/'inputs.local.json');original={x['id']:x for x in inputs}
        audits={x['id']:x for x in read(previous/'ground-audit.local.json')};cases=[]
        for i,x in enumerate(inputs):
            actual=call(dict(x,op='prepare'))['actual_messages'];assert actual==audits[x['id']]['actual_messages'],x['id']
            for condition in (['before','after'] if i%2==0 else ['after','before']):
                cases.append(dict(id=condition+'-'+x['id'],source_id=x['id'],condition=condition,input=x['input'],register=x['register'],messages=x['messages'],actual_messages=actual))
        phone=[json.loads(line) for line in (a.artifacts.parent/'turn-guidance-20261115/fresh-results.local.jsonl').read_text(encoding='utf-8-sig').splitlines()]
        for r in phone:
            x=original[r['id'].split('-',1)[1]];consumed=call(dict(x,condition='before',raw=r['result']['raw']))
            assert consumed['delivered_spoken']==r['delivered_spoken'] and consumed['blocked']==r['blocked'],r['id']
        gates=[next(dict(x,id='gate-'+ident,condition='before') for x in cases if x['source_id']==ident) for ident in ['conv01','conv29','conv37']]
        for name,data in [('suite.local.json',cases),('gates.local.json',gates)]:
            with (a.artifacts/name).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
        checks=dict(prepared_messages_equal_android=54,saved_android_outputs_same_consumption=len(phone),
                    json_implementation='Disclosed Android-ordered JSONObject compatibility shim; not a stock 2024 JVM HashMap implementation')
        (out/'checks.local.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8');print(checks)
    finally:
        process.stdin.close();process.wait()
        assert process.returncode==0


if __name__=='__main__':main()
