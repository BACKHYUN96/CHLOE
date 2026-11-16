"""Validate frozen device replay and export synthetic reply economy evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from audit_matched_apps import delivered_contract
from export_matched_app_results import overall


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def deletion_only(before, after):
    iterator = iter(before)
    return all(any(c == wanted for c in iterator) for wanted in after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    plan = read(root/'training/configs/reply-economy-plan.json')
    assert digest(root/plan['baseline_responses']) == plan['baseline_lf_sha256']
    source = root/'app/src/main/java/ai/chloe/voicelab/conversation'
    assert digest(source/'ReplyEconomyPolicy.java') == plan['reply_policy_lf_sha256']
    assert digest(source/'GroundedConversationPolicy.java') == plan['grounding_policy_lf_sha256']
    before = {r['id']: r for r in read(root/plan['baseline_responses'])}
    inputs = {r['id']: r for r in read(args.artifacts/'inputs.local.json')}
    audits = {r['id']: r for r in read(args.artifacts/'final-audit.local.json')}
    judgments = read(args.artifacts/'gpt-judgments.local.json')
    labels = judgments['delivered']
    assert set(before) == set(inputs) == set(audits) == set(labels)
    assert len(before) == plan['comparison_questions'] == 54
    previous = args.artifacts.parent/'summary-relevance-20261115'
    assert read(args.artifacts/'ground-audit.local.json') == read(previous/'final-audit.local.json')
    assert read(args.artifacts/'inputs.local.json') == read(previous/'consumer-input.local.json')
    output, transitions = [], Counter()
    for ident, old in before.items():
        row, item = audits[ident], inputs[ident]
        a, b = row['before_spoken'], row['after_spoken']
        assert a == old['delivered_spoken_text']
        assert item['input'] == old['question']
        assert row['after_failure_code'] == 'none' and not row['after_fallback']
        assert b and len(b.encode('utf-16-le'))//2 <= 220 and deletion_only(a, b)
        original, final = json.loads(item['raw']), json.loads(row['final_raw'])
        assert original.pop('spoken_text').strip() == a
        assert final.pop('spoken_text').strip() == b
        assert original == final, 'Changed non-speech JSON metadata'
        assert delivered_contract(row['final_raw'])['contract_pass']
        quality = labels[ident]
        assert set(quality['criteria']) == set(old['delivered_gpt_quality']['criteria'])
        assert set(quality['criteria'].values()) <= {'pass','partial','fail','not_applicable'}
        if row['economy_action'] == 'none':
            assert a == b and quality == old['delivered_gpt_quality']
        else:
            assert len(b) < len(a)
        grade = overall(quality)
        transitions[old['delivered_gpt_overall']+'->'+grade] += 1
        output.append(dict(id=ident, question=old['question'], before_spoken_text=a,
                           after_spoken_text=b, economy_action=row['economy_action'],
                           before_gpt_overall=old['delivered_gpt_overall'],
                           after_gpt_overall=grade, after_gpt_quality=quality,
                           raw_gpt_overall=old['raw_gpt_overall'],
                           actual_consumer_pass=True))
    summary = dict(questions=54, fresh_model_generations=0, device_replays=54,
                   before=dict(Counter(r['before_gpt_overall'] for r in output)),
                   after=dict(Counter(r['after_gpt_overall'] for r in output)),
                   raw_model_unchanged=dict(Counter(r['raw_gpt_overall'] for r in output)),
                   actions=dict(Counter(r['economy_action'] for r in output)),
                   transitions=dict(transitions), actual_consumer_pass=54,
                   deletion_only_pass=54, unchanged_model_inputs_and_grounding=54,
                   method=judgments['method'], limitations=plan['scope_limit'])
    checks = read(args.artifacts/'jvm-tests-complete/checks.json')
    assert checks['junit_exit_code'] == 0
    assert 'OK (81 tests)' in (args.artifacts/'jvm-tests-complete/step-2.log').read_text()
    python_log = (args.artifacts/'python-tests.log').read_text(encoding='utf-8-sig')
    assert 'Ran 126 tests' in python_log and 'OK (skipped=3)' in python_log
    preservation = read(args.artifacts/'preservation.local.json')
    assert preservation['original_chloe_settings_logs_contents_equal']
    checks.update(jvm_tests_passed=81, python_tests_total=126,
                  python_tests_passed=123, python_optional_skipped=3,
                  device_consumer_passed=54, deletion_only_passed=54,
                  non_speech_metadata_unchanged=54, model_request_and_grounding_unchanged=54,
                  preservation=preservation, full_product_apk_ui_tts_verified=False,
                  next_turn_generation_verified=False)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [('responses.json', output), ('summary.json', summary),
                        ('plan.json', plan), ('checks.json', checks)]:
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
