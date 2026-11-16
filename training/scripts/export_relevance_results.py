"""Verify fresh paired filter runs and export supplied direct GPT judgments.

No semantic grading rules/API. History, controls, contract and source assertions
are independent of the direct six-criterion quality labels.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract, fingerprint
from export_matched_app_results import overall
from export_route_ablation import bounded_add


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def audit(rows,tasks,expected_count=212):
    assert len(rows)==len(tasks)==len({r['id'] for r in rows})==expected_count
    histories=defaultdict(list)
    for r,t in zip(rows,tasks):
        assert all(r[k]==v for k,v in t.items()),r['id']
        n,a=r['native'],r['app']
        assert r['condition'] in ['before','after'] and r['route']=='current'
        for key,value in dict(requested_gpu_layers=99,temperature=0,seed=42,context_tokens=2048,max_generation_tokens=384,prefill_threads=4,decode_threads=4).items():
            assert n[key]==value,(r['id'],key)
        assert n['runtime_revision']=='aa75ff3239f9cc675b081697deda9e1b112345c6' and n['schema_grammar']
        assert len(n['prompt_token_ids'])==n['prompt_tokens']<=1664
        assert a['delivered_spoken']==a['stages'][-1]['speech']
        if 'session' not in r:continue
        key=(r['condition'],r['session']);expected=[r['messages'][0]]
        for u,speech in histories[key]:expected += [dict(role='user',content=u),dict(role='assistant',content=speech)]
        expected.append(dict(role='user',content=r['input']))
        assert r['messages']==expected,(r['id'],'history contamination')
        if not a['blocked']:bounded_add(histories[key],r['input'],a['delivered_spoken'])
        assert a['retained_history_pairs']==len(histories[key])
    return dict(fresh_requests=len(rows),independent_actual_history_reconstructed=True,exact_scripted_inputs=True,settings_verified=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    plan=read(a.artifacts/'plan.local.json');tasks=read(a.artifacts/'tasks.local.json')
    hashes = plan.get('source_hashes')
    if hashes is None:
        hashes = {'app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java':plan['policy_sha256']}
    for path,value in hashes.items():
        assert hashlib.sha256((root/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==value,path
    rows=[json.loads(s) for s in (a.artifacts/'results.local.jsonl').read_text(encoding='utf-8').splitlines()]
    checks=audit(rows,tasks,plan['native_requests']);labels=read(a.artifacts/'judgments.local.json')
    assert set(labels['raw'])==set(labels['final'])=={r['id'] for r in rows}
    exported=[];pairs=defaultdict(dict)
    for r in rows:
        n,app=r['native'],r['app'];raw=delivered_contract(n['raw']);final=delivered_contract(app['delivered_raw'])
        for side in ['raw','final']:
            label=labels[side][r['id']]
            assert set(label['criteria'])=={'content','register','honesty','identity_role','memory','instruction_handling'}
            assert set(label['criteria'].values())<={'pass','partial','fail','not_applicable'} and label['reason'] and label['provenance']
        if final['contract_pass']:assert final['spoken_text'].strip()==app['delivered_spoken']
        item={k:r[k] for k in ['id','source_id','condition','cohort','input','register','messages','actual_messages']}
        item.update({k:r[k] for k in ['session','turn','topic','expectation'] if k in r})
        item.update(raw=n['raw'],raw_speech=raw['spoken_text'],delivered_raw=app['delivered_raw'],delivered_speech=app['delivered_spoken'],
                    stages=app['stages'],raw_gpt=labels['raw'][r['id']],final_gpt=labels['final'][r['id']],
                    raw_gpt_overall=overall(labels['raw'][r['id']]) if raw['contract_pass'] and n['native_parse_status']=='ok' else 'fail',
                    final_gpt_overall=overall(labels['final'][r['id']]) if final['contract_pass'] and not app['blocked'] and n['native_parse_status']=='ok' else 'fail',
                    raw_contract_pass=raw['contract_pass'],final_contract_pass=final['contract_pass'],blocked=app['blocked'],native_parse_status=n['native_parse_status'],
                    truncated=n['truncated'],prompt_tokens=n['prompt_tokens'],output_tokens=n['tokens'],
                    input_tokens_sha256=fingerprint(n['prompt_token_ids']),inference_ms=n['native_request_ms']-n['load_ms'],load_ms=n['load_ms'],elapsed_ms=r['elapsed_ms'])
        exported.append(item);pairs[r['source_id']][r['condition']]=item
    paired=[];rank={'fail':0,'partial':1,'pass':2}
    for ident,pair in pairs.items():
        assert set(pair)=={'before','after'},ident
        b,c=pair['before'],pair['after']
        assert b['input']==c['input'] and b['register']==c['register'] and b['messages'][0]==c['messages'][0]
        if b['actual_messages']==c['actual_messages']:assert b['input_tokens_sha256']==c['input_tokens_sha256']
        paired.append(dict(id=ident,cohort=b['cohort'],before=b['final_gpt_overall'],after=c['final_gpt_overall'],
                           original_history_equal=b['messages']==c['messages'],model_input_equal=b['actual_messages']==c['actual_messages'],
                           raw_equal=b['raw']==c['raw'],final_speech_equal=b['delivered_speech']==c['delivered_speech']))
    summary=dict(fresh_requests=len(rows),main_requests=sum(r['cohort'] in ('known','new_single','dialogue') for r in rows),
                 supplemental_fixed_history_requests=sum(r['cohort']=='fixed_history_probe' for r in rows),training_steps=0,cohorts={})
    if any(r['cohort']=='control' for r in paired):
        summary['supplemental_control_requests']=sum(r['cohort']=='control' for r in rows)
    for cohort in dict.fromkeys(r['cohort'] for r in paired):
        group=[r for r in paired if r['cohort']==cohort]
        summary['cohorts'][cohort]=dict(questions=len(group),scores={c:dict(Counter(r[c] for r in group)) for c in ['before','after']},
            raw_scores={c:dict(Counter(r['raw_gpt_overall'] for r in exported if r['cohort']==cohort and r['condition']==c)) for c in ['before','after']},
            improved=sum(rank[r['after']]>rank[r['before']] for r in group),regressed=sum(rank[r['after']]<rank[r['before']] for r in group),
            model_input_equal=sum(r['model_input_equal'] for r in group),raw_equal=sum(r['raw_equal'] for r in group),original_history_equal=sum(r['original_history_equal'] for r in group))
    summary.update(raw_contract_pass=sum(r['raw_contract_pass'] for r in exported),final_contract_pass=sum(r['final_contract_pass'] for r in exported),
                   normal_native_finish=sum(r['native_parse_status']=='ok' for r in exported),blocked=sum(r['blocked'] for r in exported),truncated=sum(r['truncated'] for r in exported),max_prompt_tokens=max(r['prompt_tokens'] for r in exported),judge=labels['method'])
    if (a.artifacts/'verification.local.json').exists():checks.update(read(a.artifacts/'verification.local.json'))
    a.output.mkdir(parents=True,exist_ok=False)
    files=[('summary.json',summary),('responses.json',exported),('paired.json',paired),('checks.json',checks),('plan.json',plan)]
    if 'source_hashes' in plan or (a.artifacts/'preflight.local.json').is_file():
        files.append(('input-audit.json',read(a.artifacts/'preflight.local.json')))
    for name,data in files:
        (a.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
