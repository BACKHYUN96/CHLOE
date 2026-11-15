"""Export synthetic, content-filtered evidence after all calls and direct reviews.

No grading model/API is invoked. Quality labels must already exist in the direct
GPT review file. Raw generated reasoning, app databases and private backups stay
in the ignored artifact directory.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit_matched_apps import audit_pocket, candidate_from_debug, delivered_contract, fingerprint
from matched_app_suite import build_suite


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def overall(judgment):
    if judgment is None:
        return None
    values = list(judgment['criteria'].values())
    if 'fail' in values:
        return 'fail'
    return 'partial' if 'partial' in values else 'pass'


def sha(text):
    return hashlib.sha256((text or '').encode()).hexdigest()


def tally(judgments):
    counts = Counter(overall(judgment) for judgment in judgments)
    return {'pass': counts['pass'], 'partial': counts['partial'], 'fail': counts['fail'],
            'unassessable': counts[None], 'assessable': sum(j is not None for j in judgments)}


def criteria_tally(judgments):
    keys = ('content', 'register', 'honesty', 'identity_role', 'memory', 'instruction_handling')
    return {key: dict(Counter(j['criteria'][key] if j else 'unassessable' for j in judgments)) for key in keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--judgments', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New public directory; refuses overwrite')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    plan = read(root / 'training/configs/matched-apps-plan.json')
    suite = build_suite(root)
    assert suite == read(args.artifacts / 'suite.local.json')
    schema = read(args.artifacts / 'schema.local.json')
    assert schema == read(root / 'app/src/main/assets/conversation-schema.json')
    judgments = read(args.judgments)
    original = []
    for file in ('chloe-main.local.jsonl', 'chloe-supplement.local.jsonl'):
        original.extend(json.loads(line) for line in (args.artifacts / file).read_text(encoding='utf-8').splitlines())
    assert len(original) == len({row['id'] for row in original}) == 54
    chloe = {row['id']: row['result'] for row in original}
    consumed = {row['id']: row for row in read(args.artifacts / 'chloe-actual-app-audit.local.json')}
    assert set(chloe) == set(consumed) == {row['id'] for row in suite}
    output, audits = [], []
    for row in suite:
        ident = row['id']
        native = chloe[ident]
        consumer = consumed[ident]
        assert consumer['actual_prompt_equal']
        pocket = read(args.artifacts / f'pocket-{ident}.local.json')
        audit = audit_pocket(row, pocket, schema, plan['generation'])
        assert audit['requested_controls_pass'], (ident, audit['requested_controls'])
        audits.append(audit)
        candidate = audit.pop('diagnostic_candidate_only')
        j_chloe = judgments['chloe'][ident]
        j_pocket = None  # Debug tails are forensic evidence, not delivered quality grades.
        for judgment in (j_chloe, j_pocket):
            if judgment is not None:
                assert set(judgment['criteria'].values()) <= {'pass', 'partial', 'fail', 'not_applicable'}
        p = pocket['result']
        output.append({
            'id': ident, 'group': row['group'], 'register': row['register'], 'question': row['input'],
            'initial_history': row['messages'][1:-1], 'messages_sha256': fingerprint(row['messages']),
            'chloe': {'spoken_text': consumer['spokenText'], 'actual_consumer_fallback': consumer['fallback'],
                      'actual_consumer_failure_code': consumer['failureCode'], 'actual_prompt_equal': consumer['actual_prompt_equal'],
                      'common_contract': delivered_contract(native.get('raw')), 'raw_sha256': sha(native.get('raw')),
                      'native_parse_status': native.get('native_parse_status'), 'tokens_reported': native.get('tokens'),
                      'truncated': native.get('truncated'), 'gpt_quality': j_chloe, 'gpt_overall': overall(j_chloe)},
            'pocketpal': {'common_contract': audit['delivered'], 'delivered_content': p.get('content'),
                          'delivered_language_quality': None if not p.get('content') else j_pocket,
                          'debug_spoken_candidate_only': candidate.get('spoken_text') if candidate else None,
                          'debug_candidate_contract': delivered_contract(json.dumps(candidate, ensure_ascii=False)) if candidate else None,
                          'debug_raw_sha256': sha(p.get('text')), 'debug_raw_characters': len(p.get('text') or ''),
                          'tokens_reported': p.get('tokens_predicted'),
                          'termination': {key: p.get(key) for key in ('truncated', 'stopped_eos', 'stopped_limit', 'stopped_word', 'stopping_word', 'interrupted')},
                          'requested_controls_match': audit['requested_controls_pass'],
                          'raw_restarts_assistant': audit['raw_restarts_assistant'], 'raw_has_thinking_block': audit['raw_has_thinking_block'],
                          'gpt_analysis_of_debug_candidate_only': j_pocket, 'gpt_debug_candidate_overall': overall(j_pocket)},
        })
    diagnostics = []
    corrected_rows = read(args.artifacts / 'diagnostic-suite.local.json')
    remaining = read(args.artifacts / 'corrected-remaining-suite.local.json')
    assert all((args.artifacts / f'pocket-{r["id"]}.local.json').exists() for r in remaining), 'Corrected condition incomplete'
    corrected_rows += remaining
    assert len(corrected_rows) == len({r['source_id'] for r in corrected_rows}) == 54
    for row in corrected_rows:
        record = read(args.artifacts / f'pocket-{row["id"]}.local.json')
        audit = audit_pocket(row, record, schema, plan['generation'])
        assert audit['requested_controls_pass']
        events = [event['value'] for event in record['events'] if event['event'] == 'diagnostic' and event['name'] == 'grammar_root']
        assert len(events) == 1 and events[0]['new_root'] == 'root ::= response-format'
        baseline = next(r for r in output if r['id'] == row['source_id'])
        assert fingerprint(row['messages']) == baseline['messages_sha256']
        result = record['result']
        judgment = judgments['pocket_corrected'][row['source_id']]
        delivered = audit['delivered']
        # Grade only validated content returned to the app, never a debug tail.
        assert (judgment is None) == (not delivered['contract_pass'])
        diagnostics.append({'id': row['id'], 'source_id': row['source_id'], 'messages_sha256': fingerprint(row['messages']),
                            'root_change': events[0], 'requested_controls_match': True,
                            'delivered_content': result.get('content'), 'common_contract': audit['delivered'],
                            'spoken_text': delivered['spoken_text'],
                            'raw_sha256': sha(result.get('text')), 'tokens_reported': result.get('tokens_predicted'),
                            'raw_restarts_assistant': audit['raw_restarts_assistant'], 'raw_has_thinking_block': audit['raw_has_thinking_block'],
                            'termination': {key: result.get(key) for key in ('truncated', 'stopped_eos', 'stopped_limit', 'stopped_word')},
                            'gpt_quality': judgment, 'gpt_overall': overall(judgment)})
    summary = {
        'recorded_primary_generations': 108, 'recorded_exploratory_generations': len(diagnostics), 'training_steps_this_experiment': 0,
        'questions': 54, 'common_model_sha256': plan['model']['sha256'],
        'chloe_actual_prompt_equal': sum(r['chloe']['actual_prompt_equal'] for r in output),
        'chloe_actual_consumer_nonfallback': sum(not r['chloe']['actual_consumer_fallback'] for r in output),
        'chloe_common_contract_pass': sum(r['chloe']['common_contract']['contract_pass'] for r in output),
        'pocket_actual_completion_request_controls_match': sum(r['pocketpal']['requested_controls_match'] for r in output),
        'pocket_nonempty_delivered_content': sum(bool(r['pocketpal']['delivered_content']) for r in output),
        'pocket_common_contract_pass': sum(r['pocketpal']['common_contract']['contract_pass'] for r in output),
        'pocket_frame_restarts': sum(r['pocketpal']['raw_restarts_assistant'] for r in output),
        'pocket_generated_thinking_blocks': sum(r['pocketpal']['raw_has_thinking_block'] for r in output),
        'pocket_token_limit_stops': sum(bool(r['pocketpal']['termination']['stopped_limit']) for r in output),
        'gpt_chloe': tally([r['chloe']['gpt_quality'] for r in output]),
        'gpt_pocket_delivered_language_quality': None if not any(r['pocketpal']['delivered_content'] for r in output) else 'see per-case records',
        'gpt_pocket_debug_candidates_only': None,
        'diagnostic_nonempty_content': sum(bool(r['delivered_content']) for r in diagnostics),
        'diagnostic_common_contract_pass': sum(r['common_contract']['contract_pass'] for r in diagnostics),
        'diagnostic_frame_restarts': sum(r['raw_restarts_assistant'] for r in diagnostics),
        'diagnostic_thinking_blocks': sum(r['raw_has_thinking_block'] for r in diagnostics),
        'corrected_questions': len(diagnostics),
        'gpt_corrected': tally([r['gpt_quality'] for r in diagnostics]),
        'criteria_chloe': criteria_tally([r['chloe']['gpt_quality'] for r in output]),
        'criteria_corrected': criteria_tally([r['gpt_quality'] for r in diagnostics]),
        'exact_spoken_text_matches': sum(r['spoken_text'] == next(o['chloe']['spoken_text'] for o in output if o['id'] == r['source_id']) for r in diagnostics),
        'judge': 'GPT direct, same author and known app identities; not independent blind or human ratings',
        'quality_limit': 'Extracted debug candidates are analysis-only; unavailable delivered content is null, never a numeric quality zero or a delivered success.',
    }
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, value in [('responses.json', output), ('input-audits.json', audits), ('corrected.json', diagnostics), ('summary.json', summary)]:
        (args.output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
