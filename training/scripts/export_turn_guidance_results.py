"""Export every fresh paired Android generation; read direct GPT labels separately."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract, fingerprint
from export_matched_app_results import overall


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--partial',action='store_true',help='Explicit paused Android cohort; never imply all planned requests ran')
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    plan=read(root/'training/configs/turn-guidance-plan.json')
    for path,value in plan['source_hashes'].items():assert sha(root/path)==value
    assert sha(a.artifacts/'suite.local.json')==plan['suite_lf_sha256']
    suite=read(a.artifacts/'suite.local.json')
    native=[json.loads(line) for line in (a.artifacts/'fresh-results.local.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    assert [r['id'] for r in native]==[r['id'] for r in suite[:len(native)]]
    assert len(native)==len({r['id'] for r in native})
    if a.partial:
        checkpoint=read(a.artifacts/'CHECKPOINT.local.json')
        assert checkpoint['completed_candidate_generations']==len(native)==79
    else:assert len(native)==plan['planned_new_generations']==108
    judgments=read(a.artifacts/'gpt-judgments.local.json')
    prior_audits={r['id']:r for r in read(a.artifacts.parent/'reply-integrity-20261115/ground-audit.local.json')}
    assert set(judgments['raw'])==set(judgments['delivered'])=={r['id'] for r in native}
    output=[];by_id={}
    for request,record in zip(suite,native):
        ident=request['id'];result=record['result'];actual=record['actual_messages']
        # History/current user bytes and roles must be the same across arms.
        assert actual[-1]==request['messages'][-1]
        assert actual[0]['content'].startswith(request['messages'][0]['content'])
        assert actual[0]['role']=='system'
        if request['condition']=='before':assert actual==prior_audits[request['source_id']]['actual_messages']
        assert result['runtime_revision']==plan['runtime_revision']
        for key,value in plan['generation'].items():
            if key in ('temperature','seed'):continue # same fixed installed native path, not echoed by worker
            assert result[key]==value,(ident,key)
        assert result['schema_grammar'] and result['gpu_mode']=='cpu'
        raw=delivered_contract(result.get('raw'))
        final=delivered_contract(record.get('delivered_raw'))
        blocked=record.get('blocked',False)
        if blocked:
            assert record['consumer_failure_code']=='unusable_reply'
            assert not final['contract_pass'] and overall(judgments['delivered'][ident])=='fail'
        elif final['contract_pass']:
            assert record['consumer_failure_code']=='none'
            assert record['delivered_spoken']==final['spoken_text'].strip()
        for side in ('raw','delivered'):
            label=judgments[side][ident]
            assert set(label['criteria'])=={'content','register','honesty','identity_role','memory','instruction_handling'}
            assert set(label['criteria'].values())<={'pass','partial','fail','not_applicable'}
        row=dict(id=ident,source_id=request['source_id'],condition=request['condition'],question=request['input'],register=request['register'],
                 raw_spoken_text=raw['spoken_text'],delivered_spoken_text=final['spoken_text'],
                 raw_gpt_quality=judgments['raw'][ident],delivered_gpt_quality=judgments['delivered'][ident],
                 raw_gpt_overall=overall(judgments['raw'][ident]),delivered_gpt_overall=overall(judgments['delivered'][ident]),
                 raw_contract_pass=raw['contract_pass'],delivered_contract_pass=final['contract_pass'],
                 blocked=blocked,policy_action=record.get('policy_action'),economy_action=record.get('economy_action'),integrity_action=record.get('integrity_action'),
                 native_parse_status=result.get('native_parse_status'),truncated=result.get('truncated'),
                 elapsed_ms=record['elapsed_ms'],prompt_tokens=result.get('prompt_tokens'),tokens=result.get('tokens'),
                 thermal_status_start=result.get('thermal_status_start'),thermal_status_end=result.get('thermal_status_end'),
                 judgment_provenance={side:judgments['provenance'][side+':'+ident] for side in ('raw','delivered')},
                 model_messages_sha256=fingerprint(actual),raw_sha256=hashlib.sha256(result.get('raw','').encode()).hexdigest())
        output.append(row);by_id[ident]=(row,actual)
    pairs=[]
    unpaired=[]
    for question in dict.fromkeys(r['source_id'] for r in suite[:len(native)]):
        if 'before-'+question not in by_id or 'after-'+question not in by_id:
            unpaired.append(question);continue
        before,mb=by_id['before-'+question];after,ma=by_id['after-'+question]
        assert mb[1:]==ma[1:],'Guidance must not rewrite/filter prior utterances'
        assert ma[0]['content'].startswith(mb[0]['content'])
        changed=mb!=ma
        pairs.append(dict(id=question,question=before['question'],model_input_changed=changed,
                          raw_output_identical=before['raw_sha256']==after['raw_sha256'],
                          before_gpt=before['delivered_gpt_overall'],after_gpt=after['delivered_gpt_overall'],
                          before_raw_gpt=before['raw_gpt_overall'],after_raw_gpt=after['raw_gpt_overall'],
                          before_system_sha256=fingerprint(mb[0]),after_system_sha256=fingerprint(ma[0]),
                          appended_system_guidance=ma[0]['content'][len(mb[0]['content']):]))
    rank={'fail':0,'partial':1,'pass':2}
    summary=dict(planned_questions=54,completed_pairs=len(pairs),unpaired_questions=unpaired,
                 status='paused_incomplete' if a.partial else 'complete',new_generations=len(native),
                 planned_new_generations=108,remaining_new_generations=108-len(native),reused_outputs=0,training_steps=0,
                 condition_completed_counts=dict(Counter(r['condition'] for r in output)),
                 gpt={condition:{side:dict(Counter(r[side+'_gpt_overall'] for r in output if r['condition']==condition)) for side in ('raw','delivered')} for condition in ('before','after')},
                 paired_final_gpt={condition:dict(Counter(r[condition+'_gpt'] for r in pairs)) for condition in ('before','after')},
                 improved=sum(rank[r['after_gpt']]>rank[r['before_gpt']] for r in pairs),
                 regressed=sum(rank[r['after_gpt']]<rank[r['before_gpt']] for r in pairs),
                 transitions=dict(Counter(r['before_gpt']+'->'+r['after_gpt'] for r in pairs)),
                 model_input_changed=[r['id'] for r in pairs if r['model_input_changed']],
                 unchanged_input_controls_identical=sum(not r['model_input_changed'] and r['raw_output_identical'] for r in pairs),
                 unchanged_input_controls_diverged=[r['id'] for r in pairs if not r['model_input_changed'] and not r['raw_output_identical']],
                 raw_contract_pass=sum(r['raw_contract_pass'] for r in output),
                 final_contract_pass=sum(r['delivered_contract_pass'] for r in output),
                 blocked=sum(r['blocked'] for r in output),truncated=sum(bool(r['truncated']) for r in output),
                 max_prompt_tokens=max(r['prompt_tokens'] for r in output),
                 judgment_provenance=dict(Counter(judgments['provenance'].values())),
                 judge=('Direct GPT assessment of completed Android outputs only: 79 completions, 39 pairs and one unpaired after output; exact previously judged speech labels reused explicitly. Remaining 29 requests not run. Not blind/independent/holdout.' if a.partial else plan['quality']),limitations=plan['limits'])
    checks=read(a.artifacts/'jvm-tests/checks.json')
    assert checks['junit_exit_code']==0
    assert 'OK (107 tests)' in (a.artifacts/'jvm-tests/step-2.log').read_text()
    log=(a.artifacts/'python-tests.log').read_text(encoding='utf-8-sig')
    assert 'Ran 126 tests' in log and 'OK (skipped=3)' in log
    checks.update(jvm_tests_passed=107,python_tests_total=126,python_tests_passed=123,python_optional_skipped=3,
                  preservation=read(a.artifacts/'preservation.local.json') if (a.artifacts/'preservation.local.json').exists() else {'phone_recheck':'not run; user disconnected USB after saving 79 outputs'},full_product_apk_ui_tts_verified=False,next_turn_generation_verified=False)
    a.output.mkdir(parents=True,exist_ok=False)
    exported_plan=dict(plan,execution_status='paused_incomplete',actual_new_generations=79,remaining_new_generations=29) if a.partial else plan
    for name,data in [('responses.json',output),('paired-input-audit.json',pairs),('summary.json',summary),('checks.json',checks),('plan.json',exported_plan)]:
        (a.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
