"""Validate fresh PC generations and export synthetic speech, fixed direct GPT labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
from audit_matched_apps import delivered_contract, fingerprint
from export_matched_app_results import overall


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def lines(p):return [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    plan=read(root/'training/configs/pc-4b-plan.json')
    for path,value in plan['source_hashes'].items():assert sha(root/path)==value,path
    assert sha(root/'app/src/main/java/ai/chloe/voicelab/conversation/ConversationActPolicy.java')==plan['final_policy_source_lf_sha256']
    assert sha(a.artifacts/'suite.local.json')==plan['suite_lf_sha256']
    assert sha(a.artifacts/'gates.local.json')==plan['gates_lf_sha256']
    suite=read(a.artifacts/'suite.local.json');native=lines(a.artifacts/'comparison.local.jsonl')
    assert len(native)==len(suite)==len({r['id'] for r in native})==108
    assert [r['id'] for r in native]==[r['id'] for r in suite]
    judgments=read(a.artifacts/'gpt-judgments.local.json')
    assert set(judgments['raw'])==set(judgments['delivered'])=={r['id'] for r in native}
    output=[];pair={}
    for request,record in zip(suite,native):
        ident=record['id'];assert all(record[k]==request[k] for k in request)
        result=record['native'];app=record['app']
        assert result['runtime_revision']==plan['runtime_revision'] and result['requested_gpu_layers']==99
        for key,value in plan['generation'].items():
            if key=='thinking':continue
            assert result[key]==value,(ident,key)
        assert result['schema_grammar'] and result['platform']=='wsl2-x86_64'
        raw=delivered_contract(result.get('raw'));final=delivered_contract(app.get('delivered_raw'))
        if final['contract_pass']:assert app['delivered_spoken']==final['spoken_text'].strip() and app['consumer_failure_code']=='none'
        for side in ['raw','delivered']:
            label=judgments[side][ident]
            assert set(label['criteria'])=={'content','register','honesty','identity_role','memory','instruction_handling'}
            assert set(label['criteria'].values())<={'pass','partial','fail','not_applicable'}
        row=dict(id=ident,source_id=record['source_id'],condition=record['condition'],question=record['input'],register=record['register'],
                 raw_spoken_text=raw['spoken_text'],delivered_spoken_text=final['spoken_text'],
                 raw_gpt_quality=judgments['raw'][ident],delivered_gpt_quality=judgments['delivered'][ident],
                 raw_gpt_overall=overall(judgments['raw'][ident]),delivered_gpt_overall=overall(judgments['delivered'][ident]),
                 judgment_provenance={s:judgments['provenance'][s+':'+ident] for s in ['raw','delivered']},
                 raw_contract_pass=raw['contract_pass'],delivered_contract_pass=final['contract_pass'],
                 policy_action=app['policy_action'],dialogue_action=app['dialogue_action'],economy_action=app.get('economy_action'),integrity_action=app.get('integrity_action'),
                 blocked=app['blocked'],consumer_failure_code=app['consumer_failure_code'],native_parse_status=result['native_parse_status'],truncated=result['truncated'],
                 tokens=result['tokens'],prompt_tokens=result['prompt_tokens'],elapsed_ms=record['elapsed_ms'],load_ms=result['load_ms'],native_request_ms=result['native_request_ms'],
                 inference_ms=result['native_request_ms']-result['load_ms'],prefill_ms=result['prefill_ms'],decode_ms=result['decode_ms'],
                 model_messages_sha256=fingerprint(record['actual_messages']),prompt_token_ids_sha256=fingerprint(result['prompt_token_ids']),raw_sha256=hashlib.sha256(result['raw'].encode()).hexdigest())
        output.append(row);pair[ident]=(row,record)
    paired=[]
    for request in suite:
        ident=request['source_id']
        if request['condition']!='before':continue
        b,br=pair['before-'+ident];c,cr=pair['after-'+ident]
        assert br['actual_messages']==cr['actual_messages'] and br['native']['prompt_token_ids']==cr['native']['prompt_token_ids']
        assert br['app']['dialogue_action']=='none'
        if cr['app']['dialogue_action']=='none':assert br['app']==cr['app']
        paired.append(dict(id=ident,question=b['question'],raw_identical=b['raw_sha256']==c['raw_sha256'],before=b['delivered_gpt_overall'],after=c['delivered_gpt_overall'],dialogue_action=c['dialogue_action'],model_messages_sha256=b['model_messages_sha256']))
    assert len(paired)==54
    rank={'fail':0,'partial':1,'pass':2}
    compatibility=read(a.artifacts/'compatibility.local.json');assert compatibility['gates_passed']
    summary=dict(platform='PC CUDA only; Android results separate',questions=54,new_comparison_generations=108,compatibility_generations=6,excluded_setup_probe_generations=3,total_PC_new_generations=117,historical_output_replays=0,training_steps=0,
                 gpt={c:{s:dict(Counter(r[s+'_gpt_overall'] for r in output if r['condition']==c)) for s in ['raw','delivered']} for c in ['before','after']},
                 improved=sum(rank[r['after']]>rank[r['before']] for r in paired),regressed=sum(rank[r['after']]<rank[r['before']] for r in paired),
                 transitions=dict(Counter(r['before']+'->'+r['after'] for r in paired)),raw_pair_identical=sum(r['raw_identical'] for r in paired),
                 dialogue_actions=dict(Counter(r['dialogue_action'] for r in paired)),raw_contract_pass=sum(r['raw_contract_pass'] for r in output),final_contract_pass=sum(r['delivered_contract_pass'] for r in output),
                 normal_native_finish=sum(r['native_parse_status']=='ok' for r in output),blocked=sum(r['blocked'] for r in output),truncated=sum(bool(r['truncated']) for r in output),
                 median_request_inference_ms=statistics.median(r['inference_ms'] for r in output),request_inference_ms_range=[min(r['inference_ms'] for r in output),max(r['inference_ms'] for r in output)],
                 summed_request_wall_seconds=sum(r['elapsed_ms'] for r in output)/1000,
                 max_prompt_tokens=max(r['prompt_tokens'] for r in output),judge=judgments['method'],
                 limits='Fixed independent one-turn histories, one seed, known development questions. Bounded app acts, not improved model knowledge. No original APK update, physical UI/TTS or generated long-history verification.')
    checks=read(a.artifacts/'jvm-tests-final/checks.json');assert checks['junit_exit_code']==0
    assert 'OK (125 tests)' in (a.artifacts/'jvm-tests-final/step-2.log').read_text()
    reconsumed=read(a.artifacts/'final-reconsumption.local.json');assert reconsumed['final_production_policy_outputs_equal_recorded_PC']==108
    python_log=(a.artifacts/'python-tests.local.log').read_text(encoding='utf-8-sig')
    assert 'Ran 126 tests' in python_log and 'OK (skipped=3)' in python_log
    checks.update(jvm_tests_passed=125,original_main_JVM_tests_passed=124,final_reconsumption=reconsumed,
                  python_tests_total=126,python_tests_passed=123,python_optional_skipped=3,
                  android_parity=read(a.artifacts/'bridge-ordered/checks.local.json'),preservation=read(a.artifacts/'preservation.local.json'),
                  full_product_apk_ui_tts_verified=False,generated_next_turn_history_verified=False)
    a.output.mkdir(parents=True,exist_ok=False)
    for name,data in [('responses.json',output),('paired.json',paired),('summary.json',summary),('checks.json',checks),('plan.json',plan),('compatibility.json',compatibility),('build-inputs.json',read(a.artifacts/'download-manifest.local.json'))]:
        (a.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
