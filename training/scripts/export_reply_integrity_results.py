"""Export frozen synthetic reply edits and explicit abstentions, never grade text."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract
from export_matched_app_results import overall
from export_reply_economy_results import deletion_only


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    plan = read(root/'training/configs/reply-integrity-plan.json')
    for path, expected in plan['source_hashes'].items():
        assert hashlib.sha256((root/path).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == expected
    old = {r['id']: r for r in read(root/plan['baseline_responses'])}
    previous = args.artifacts.parent/'reply-economy-20261115'
    prior_audits = {r['id']: r for r in read(previous/'final-audit.local.json')}
    prior_inputs = {r['id']: r for r in read(previous/'inputs.local.json')}
    inputs = {r['id']: r for r in read(args.artifacts/'inputs.local.json')}
    audits = {r['id']: r for r in read(args.artifacts/'final-audit.local.json')}
    judgments = read(args.artifacts/'gpt-judgments.local.json')
    labels = judgments['delivered']
    assert len(old) == plan['questions'] == 54
    assert set(old) == set(inputs) == set(audits) == set(labels)
    assert read(args.artifacts/'ground-audit.local.json') == read(previous/'ground-audit.local.json')
    output = []
    for ident, baseline in old.items():
        item, audit = inputs[ident], audits[ident]
        prior = dict(prior_inputs[ident], raw=prior_audits[ident]['final_raw'])
        assert item == prior, 'Changed frozen model request or baseline JSON'
        assert item['input'] == baseline['question']
        before, after = audit['before_spoken'], audit['after_spoken']
        assert before == baseline['after_spoken_text']
        assert deletion_only(before, after)
        if audit['blocked']:
            assert after == '' and audit['final_raw'] is None
            assert audit['after_failure_code'] == 'unusable_reply' and audit['after_fallback']
            assert overall(labels[ident]) == 'fail', 'Abstention is not an answer'
        else:
            assert after and audit['after_failure_code'] == 'none' and not audit['after_fallback']
            assert delivered_contract(audit['final_raw'])['contract_pass']
            original, final = json.loads(item['raw']), json.loads(audit['final_raw'])
            assert original.pop('spoken_text').strip() == before
            assert final.pop('spoken_text').strip() == after
            assert original == final
        if audit['integrity_action'] == 'none':
            assert before == after and labels[ident] == baseline['after_gpt_quality']
        else:
            assert len(after) < len(before)
        assert set(labels[ident]['criteria']) == set(baseline['after_gpt_quality']['criteria'])
        assert set(labels[ident]['criteria'].values()) <= {'pass','partial','fail','not_applicable'}
        output.append(dict(id=ident, question=baseline['question'],
                           before_spoken_text=before, after_spoken_text=after,
                           failure_notice=('답변을 제대로 완성하지 못했어요.' if item['register']=='polite' else '답변을 제대로 완성하지 못했어.') if audit['blocked'] else None,
                           integrity_action=audit['integrity_action'], blocked=audit['blocked'],
                           tts_and_history_eligible=not audit['blocked'],
                           before_gpt_overall=baseline['after_gpt_overall'],
                           after_gpt_overall=overall(labels[ident]), after_gpt_quality=labels[ident],
                           raw_gpt_overall=baseline['raw_gpt_overall']))
    summary = dict(questions=54, fresh_model_generations=0, frozen_device_replays=54,
                   before=dict(Counter(r['before_gpt_overall'] for r in output)),
                   after=dict(Counter(r['after_gpt_overall'] for r in output)),
                   raw_model_unchanged=dict(Counter(r['raw_gpt_overall'] for r in output)),
                   actions=dict(Counter(r['integrity_action'] for r in output)),
                   transitions=dict(Counter(r['before_gpt_overall']+'->'+r['after_gpt_overall'] for r in output)),
                   changed=sum(r['integrity_action']!='none' for r in output),
                   actual_consumer_accepted=sum(not r['blocked'] for r in output),
                   explicitly_suppressed=sum(r['blocked'] for r in output),
                   method=judgments['method'], limitations=plan['limitations'])
    checks = read(args.artifacts/'jvm-tests/checks.json')
    assert checks['junit_exit_code'] == 0
    assert 'OK (97 tests)' in (args.artifacts/'jvm-tests/step-2.log').read_text()
    log = (args.artifacts/'python-tests.log').read_text(encoding='utf-8-sig')
    assert 'Ran 126 tests' in log and 'OK (skipped=3)' in log
    preservation = read(args.artifacts/'preservation.local.json')
    assert preservation['original_chloe_settings_logs_contents_equal']
    checks.update(jvm_tests_passed=97, python_tests_total=126, python_tests_passed=123,
                  python_optional_skipped=3, deletion_or_abstention_only=54,
                  unchanged_model_inputs_and_grounding=54, preservation=preservation,
                  full_product_apk_ui_tts_verified=False, next_turn_generation_verified=False)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('responses.json',output),('summary.json',summary),('checks.json',checks),('plan.json',plan)]:
        (args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
