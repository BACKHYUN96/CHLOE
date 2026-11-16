"""Audit exact histories/controls and export direct GPT stage judgments.

This tool never judges meaning. Every unique speech within a request must have
a supplied direct review. Failures/blocked replies are not successful answers.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract, fingerprint
from export_matched_app_results import overall


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def bounded_add(history, user, answer):
    history.append((user, answer))
    def utf16(s):
        return len(s.encode('utf-16-le')) // 2
    while len(history) > 4 or sum(utf16(u) + utf16(a) for u, a in history) > 1200:
        history.pop(0)


def audit(rows, tasks):
    assert len(rows) == len(tasks) == 208
    assert len({r['id'] for r in rows}) == 208
    histories = defaultdict(list)
    for r, t in zip(rows, tasks):
        assert all(r[k] == v for k, v in t.items()), r['id']
        n, a = r['native'], r['app']
        assert n['runtime_revision'] == 'aa75ff3239f9cc675b081697deda9e1b112345c6'
        for k, v in dict(requested_gpu_layers=99, temperature=0, seed=42, context_tokens=2048,
                         max_generation_tokens=384, prefill_threads=4, decode_threads=4).items():
            assert n[k] == v, (r['id'], k)
        assert n['prompt_tokens'] == len(n['prompt_token_ids']) <= 1664
        assert n['schema_grammar']
        # Retain any parse/token-limit/contract failure for reporting, never grade it as success.
        if r['route'] == 'minimal':
            assert r['actual_messages'] == r['messages'], r['id']
            assert a['delivered_spoken'] == a['stages'][0]['speech']
        else:
            assert a['delivered_spoken'] == a['stages'][-1]['speech']
        if 'session' in r:
            key = (r['route'], r['session'])
            expected = [{'role':'system','content':r['messages'][0]['content']}]
            for u, answer in histories[key]:
                expected += [dict(role='user',content=u), dict(role='assistant',content=answer)]
            expected += [dict(role='user',content=r['input'])]
            assert r['messages'] == expected, (r['id'], 'history contamination')
            if not a['blocked']:
                bounded_add(histories[key], r['input'], a['delivered_spoken'])
            assert a['retained_history_pairs'] == len(histories[key])
    return dict(records=len(rows), exact_scripted_inputs=True, route_local_actual_history=True,
                minimal_input_untouched=True, final_stage_matches_delivery=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['artifacts','output']:
        p.add_argument('--'+name,type=Path,required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    rows = [json.loads(s) for s in (a.artifacts/'results.local.jsonl').read_text(encoding='utf-8').splitlines()]
    plan, tasks = read(a.artifacts/'plan.local.json'), read(a.artifacts/'tasks.local.json')
    for path, sha in plan['source_hashes'].items():
        data = (root/path).read_bytes()
        lf = data.replace(b'\r\n',b'\n')
        # Frozen hashes are execution-time bytes; Git may change only line endings.
        assert sha in {hashlib.sha256(v).hexdigest() for v in [data,lf,lf.replace(b'\n',b'\r\n')]}, path
    checks = audit(rows, tasks)
    if (a.artifacts/'verification.local.json').exists():
        checks.update(read(a.artifacts/'verification.local.json'))
    judgments = read(a.artifacts/'judgments.local.json')
    assert set(judgments['responses']) == {r['id'] for r in rows}
    exported, pairs = [], defaultdict(dict)
    for r in rows:
        app, n = r['app'], r['native']
        labels = judgments['responses'][r['id']]
        assert len(labels) == len(app['stages'])
        stages = []
        for s, label in zip(app['stages'], labels):
            assert set(label['criteria']) == {'content','register','honesty','identity_role','memory','instruction_handling'}
            assert set(label['criteria'].values()) <= {'pass','partial','fail','not_applicable'}
            assert label['reason']
            stages.append(dict(s, gpt=label, overall=overall(label)))
        raw_contract, final_contract = delivered_contract(n['raw']), delivered_contract(app['delivered_raw'])
        selected = stages[0] if r['route']=='minimal' else stages[-1]
        final_quality = selected['overall'] if final_contract['contract_pass'] and not app['blocked'] and n['native_parse_status']=='ok' else 'fail'
        if final_contract['contract_pass']:
            assert final_contract['spoken_text'].strip() == app['delivered_spoken']
        item = {k:r[k] for k in ['id','source_id','route','cohort','input','register','messages','actual_messages']}
        item.update({k:r[k] for k in ['session','turn','expectation','topic'] if k in r})
        item.update(stages=stages, delivered_spoken=app['delivered_spoken'], final_gpt_overall=final_quality,
                    raw=n['raw'], delivered_raw=app['delivered_raw'], blocked=app['blocked'],
                    raw_contract_pass=raw_contract['contract_pass'], final_contract_pass=final_contract['contract_pass'],
                    native_parse_status=n['native_parse_status'], truncated=n['truncated'], prompt_tokens=n['prompt_tokens'],
                    output_tokens=n['tokens'], prompt_token_ids_sha256=fingerprint(n['prompt_token_ids']),
                    input_messages_sha256=fingerprint(r['actual_messages']), inference_ms=n['native_request_ms']-n['load_ms'],
                    elapsed_ms=r['elapsed_ms'], load_ms=n['load_ms'])
        exported.append(item)
        pairs[r['source_id']][r['route']] = item
    rank = {'fail':0, 'partial':1, 'pass':2}
    paired = []
    for ident, pair in pairs.items():
        m, c = pair['minimal'], pair['current']
        paired.append(dict(id=ident,cohort=m['cohort'],minimal=m['final_gpt_overall'],current=c['final_gpt_overall'],
                           input_messages_equal=m['actual_messages']==c['actual_messages'],
                           input_tokens_equal=m['prompt_token_ids_sha256']==c['prompt_token_ids_sha256'],
                           raw_equal=m['raw']==c['raw'], final_speech_equal=m['delivered_spoken']==c['delivered_spoken'],
                           original_history_equal=m['messages']==c['messages']))
    cohorts = {}
    for cohort in ['known','new_single','dialogue']:
        subset = [p for p in paired if p['cohort']==cohort]
        cohorts[cohort] = dict(questions=len(subset),
            scores={route:dict(Counter(p[route] for p in subset)) for route in ['minimal','current']},
            raw_scores={route:dict(Counter(r['stages'][0]['overall'] for r in exported if r['cohort']==cohort and r['route']==route)) for route in ['minimal','current']},
            improved=sum(rank[p['current']]>rank[p['minimal']] for p in subset),
            regressed=sum(rank[p['current']]<rank[p['minimal']] for p in subset),
            input_tokens_equal=sum(p['input_tokens_equal'] for p in subset),raw_equal=sum(p['raw_equal'] for p in subset),
            original_history_equal=sum(p['original_history_equal'] for p in subset))
    stage_effects = {}
    for route in ['minimal','current']:
        stage_effects[route] = {}
        subset = [r for r in exported if r['route']==route]
        for index in range(1,5):
            changed = [r for r in subset if len(r['stages'])>index and (r['stages'][index]['speech'] != r['stages'][index-1]['speech'] or r['stages'][index]['blocked'] != r['stages'][index-1]['blocked'])]
            stage_effects[route][['parse','grounded_reply','conversation_act','economy','integrity'][index]] = dict(changed=len(changed),
                improved=sum(rank[r['stages'][index]['overall']]>rank[r['stages'][index-1]['overall']] for r in changed),
                regressed=sum(rank[r['stages'][index]['overall']]<rank[r['stages'][index-1]['overall']] for r in changed),
                changed_ids=[r['id'] for r in changed])
    summary = dict(new_generations=len(rows),training_steps=0,cohorts=cohorts,stage_effects=stage_effects,
                   raw_contract_pass=sum(r['raw_contract_pass'] for r in exported),final_contract_pass=sum(r['final_contract_pass'] for r in exported),
                   normal_native_finish=sum(r['native_parse_status']=='ok' for r in exported),blocked=sum(r['blocked'] for r in exported),
                   truncated=sum(r['truncated'] for r in exported),max_prompt_tokens=max(r['prompt_tokens'] for r in exported),
                   judge=judgments['method'], limits=plan['quality'])
    a.output.mkdir(parents=True,exist_ok=False)
    for name, data in [('responses.json',exported),('paired.json',paired),('summary.json',summary),('checks.json',checks),('plan.json',plan)]:
        (a.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
