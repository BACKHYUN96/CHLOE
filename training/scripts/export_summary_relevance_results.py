"""Export synthetic evidence; quality labels are direct GPT judgments, not generated here."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract, fingerprint
from export_matched_app_results import overall, tally, criteria_tally
from matched_app_suite import build_suite


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def retained_history(source, actual):
    """The model view may omit whole pairs, never rewrite or invent utterances."""
    assert source[-1] == actual[-1]
    cursor = 1
    kept = []
    for row in actual[1:-1]:
        while cursor < len(source)-1 and source[cursor] != row:
            cursor += 1
        assert cursor < len(source)-1, 'Rewritten or invented model-view utterance'
        kept.append(cursor)
        cursor += 1
    omitted = [i for i in range(1, len(source)-1) if i not in kept]
    for i in range(1, len(source)-1, 2):
        assert (i in omitted) == (i+1 in omitted), 'Partial pair omission'
    roles = [m['role'] for m in actual]
    assert roles == ['system'] + ['user', 'assistant'] * ((len(actual)-2)//2) + ['user']
    return omitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory only')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    plan = read(root/'training/configs/summary-relevance-plan.json')
    assert file_digest(root/plan['baseline_responses']) == plan['baseline_responses_lf_sha256']
    assert file_digest(root/'app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java') == plan['policy_source_lf_sha256']
    suite = build_suite(root)
    before = {r['id']: r for r in read(root/plan['baseline_responses'])}
    previous_dir = args.artifacts.parent/'grounding-20261115'
    prior_audit = {r['id']: r for r in read(previous_dir/'scope-final-audit.local.json')}
    prior_final = {r['id']: r['raw'] for r in read(previous_dir/'final-consumer-input.local.json')}
    native = {r['id']: r['result'] for f in ('chloe-main.local.jsonl', 'chloe-supplement.local.jsonl') for r in jsonl(args.artifacts.parent/'apps-match-20261115'/f)}
    native.update({r['id'].removeprefix('grounded-'): r['result'] for r in jsonl(previous_dir/'scoped-final.local.jsonl')})
    fresh = {r['id'].removeprefix('relevance-'): r for r in jsonl(args.artifacts/'selected-native.local.jsonl')}
    assert len(fresh) == plan['selected_new_outputs'] == 6
    audits = {r['id']: r for r in read(args.artifacts/'final-audit.local.json')}
    consumed = {r['id']: r for r in read(args.artifacts/'actual-consumer.local.json')}
    judgments = read(args.artifacts/'gpt-judgments.local.json')
    expected = {r['id'] for r in suite}
    assert set(before) == set(audits) == set(consumed) == set(judgments['raw']) == set(judgments['delivered']) == expected
    output, inputs, transitions = [], [], Counter()
    for source in suite:
        ident = source['id']
        old, audit, consumer = before[ident], audits[ident], consumed[ident]
        alias = ident not in fresh
        if alias:
            assert audit == prior_audit[ident], 'Alias changes model request or app decision'
            result, raw, final = native[ident], native[ident]['raw'], prior_final[ident]
            assert judgments['raw'][ident] == old['raw_gpt_quality']
            assert judgments['delivered'][ident] == old['delivered_gpt_quality']
        else:
            record = fresh[ident]
            result, raw, final = record['result'], record['result']['raw'], record['delivered_raw']
            assert record['actual_messages'] == audit['actual_messages']
            assert record['policy_action'] == audit['policy_action']
        actual = audit['actual_messages']
        assert actual[0]['role'] == 'system'
        assert actual[0]['content'].startswith(source['messages'][0]['content'])
        omitted = retained_history(source['messages'], actual)
        for key, value in {'runtime_revision':'aa75ff3239f9cc675b081697deda9e1b112345c6', 'context_tokens':2048, 'max_generation_tokens':384, 'prefill_threads':4, 'decode_threads':4, 'backend':'cpu'}.items():
            assert result[key] == value, (ident, key)
        raw_contract, final_contract = delivered_contract(raw), delivered_contract(final)
        assert raw_contract['contract_pass'] and final_contract['contract_pass']
        assert not result.get('truncated')
        assert consumer['actual_prompt_equal'] and not consumer['fallback'] and consumer['failureCode'] == 'none'
        assert consumer['spokenText'] == final_contract['spoken_text'].strip()
        if audit['policy_reply'] is not None:
            assert final == audit['policy_reply']
        else:
            assert final == raw and judgments['raw'][ident] == judgments['delivered'][ident]
        for j in (judgments['raw'][ident], judgments['delivered'][ident]):
            assert set(j['criteria'].values()) <= {'pass','partial','fail','not_applicable'}
        previous_grade, current_grade = old['delivered_gpt_overall'], overall(judgments['delivered'][ident])
        transitions[(previous_grade, current_grade)] += 1
        inputs.append({'id':ident, 'raw_model_output_alias':alias, 'question_unchanged':True, 'base_system_preserved':True, 'original_messages_sha256':fingerprint(source['messages']), 'previous_model_messages_sha256':fingerprint(prior_audit[ident]['actual_messages']), 'model_messages_sha256':fingerprint(actual), 'omitted_original_history_indices':omitted, 'kept_history_utterances_verbatim':True, 'policy_action':audit['policy_action'], 'base_builder_equal':True, 'final_consumer_pass':True})
        output.append({'id':ident, 'question':source['input'], 'register':source['register'], 'original_history':source['messages'][1:-1], 'model_history':actual[1:-1], 'system_suffix':actual[0]['content'][len(source['messages'][0]['content']):], 'raw_model_output_alias':alias, 'baseline_spoken_text':old['delivered_spoken_text'], 'baseline_gpt_quality':old['delivered_gpt_quality'], 'baseline_gpt_overall':previous_grade, 'previous_raw_gpt_quality':old['raw_gpt_quality'], 'raw_sha256':digest(raw), 'raw_spoken_text':raw_contract['spoken_text'], 'raw_gpt_quality':judgments['raw'][ident], 'raw_gpt_overall':overall(judgments['raw'][ident]), 'policy_action':audit['policy_action'], 'delivered_sha256':digest(final), 'delivered_spoken_text':consumer['spokenText'], 'delivered_gpt_quality':judgments['delivered'][ident], 'delivered_gpt_overall':current_grade, 'raw_contract_pass':True, 'delivered_contract_pass':True, 'actual_consumer_pass':True, 'tokens':result.get('tokens'), 'prompt_tokens':result.get('prompt_tokens'), 'native_parse_status':result.get('native_parse_status'), 'truncated':result.get('truncated')})
    order = {'fail':0,'partial':1,'pass':2}
    summary = {'questions':54, 'comparison_cells':108, 'baseline_reused':54, 'selected_new_model_outputs':len(fresh), 'previous_model_output_aliases':54-len(fresh), 'new_generate_completions':7, 'excluded_candidate_outputs':1, 'training_steps':0, 'model_sha256':plan['model_sha256'], 'policy_source_lf_sha256':plan['policy_source_lf_sha256'], 'base_builder_and_final_consumer_pass':54, 'fresh_native_parse_ok':sum(r['result'].get('native_parse_status')=='ok' for r in fresh.values()), 'raw_contract_pass':54, 'final_contract_pass':54, 'truncated':0, 'paired_omission_cases':[r['id'] for r in inputs if r['omitted_original_history_indices']], 'policy_actions':dict(Counter(r['policy_action'] for r in output)), 'gpt_previous_raw':tally([r['previous_raw_gpt_quality'] for r in output]), 'gpt_baseline':tally([r['baseline_gpt_quality'] for r in output]), 'gpt_raw':tally([r['raw_gpt_quality'] for r in output]), 'gpt_delivered':tally([r['delivered_gpt_quality'] for r in output]), 'changed_subset_baseline':tally([r['baseline_gpt_quality'] for r in output if not r['raw_model_output_alias']]), 'changed_subset_raw':tally([r['raw_gpt_quality'] for r in output if not r['raw_model_output_alias']]), 'changed_subset_delivered':tally([r['delivered_gpt_quality'] for r in output if not r['raw_model_output_alias']]), 'criteria_delivered':criteria_tally([r['delivered_gpt_quality'] for r in output]), 'transitions':{a+' -> '+b:n for (a,b),n in transitions.items()}, 'improved':sum(n for (a,b),n in transitions.items() if order[b]>order[a]), 'regressed':sum(n for (a,b),n in transitions.items() if order[b]<order[a]), 'same':sum(n for (a,b),n in transitions.items() if a==b), 'judge':'GPT direct, same author knows conditions; fixed known development set, not blind/independent/human', 'scope':'Source-complete app summary and relevant model view; no model retraining or full product UI/TTS release validation.'}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('responses.json',output),('input-audit.json',inputs),('summary.json',summary)]:
        (args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
