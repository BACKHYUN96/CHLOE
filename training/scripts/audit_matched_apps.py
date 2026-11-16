"""Separate requested controls, delivered output and diagnostic-only candidates.

This module never assigns language/content quality scores. Those are direct GPT
judgments, recorded separately. A JSON tail extracted from raw debug text is not
a response delivered by the application and must not count as contract success.
"""
import hashlib
import json

from data_contract import validate_reply


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def candidate_from_debug(raw):
    if not isinstance(raw, str):
        return None
    tail = raw.rsplit('</think>', 1)[-1].strip()
    for offset, char in enumerate(tail):
        if char != '{':
            continue
        try:
            obj, end = json.JSONDecoder().raw_decode(tail[offset:])
        except ValueError:
            continue
        if not tail[offset + end:].strip() and isinstance(obj, dict) and isinstance(obj.get('spoken_text'), str):
            return obj
    return None


def delivered_contract(raw):
    if not isinstance(raw, str) or not raw.strip():
        return {'available': False, 'contract_pass': False, 'spoken_text': None}
    try:
        reply = validate_reply(raw)
    except (ValueError, KeyError, TypeError):
        return {'available': True, 'contract_pass': False, 'spoken_text': None}
    return {'available': True, 'contract_pass': True, 'spoken_text': reply['spoken_text']}


def audit_pocket(row, record, schema, generation):
    calls = [e for e in record['events'] if e['event'] == 'call' and e['name'] == 'completion']
    if len(calls) != 1:
        raise ValueError('Expected one actual completion, not aliases/retries')
    call = calls[0]
    actual = call['value'][0]
    controls = {key: actual.get(key) == generation[key] for key in ('temperature', 'seed', 'n_predict', 'enable_thinking', 'jinja', 'penalty_repeat')}
    controls['messages'] = actual.get('messages') == row['messages']
    controls['schema'] = actual.get('response_format', {}).get('json_schema', {}).get('schema') == schema
    formats = [e for e in record['events'] if e['name'] == 'getFormattedChat' and e['event'] == 'result' and e['id'] > call['id']]
    if len(formats) != 1:
        raise ValueError('Missing actual completion formatter result')
    formatted = formats[0]['value']
    raw = record['result'].get('text')
    content = record['result'].get('content')
    return {
        'id': row['id'], 'requested_controls': controls,
        'requested_controls_pass': all(controls.values()),
        'messages_sha256': fingerprint(row['messages']),
        'schema_sha256': fingerprint(schema),
        'generation_prompt': formatted.get('generation_prompt'),
        'thinking_forced_open': formatted.get('thinking_forced_open'),
        'grammar_sha256': hashlib.sha256(formatted.get('grammar', '').encode()).hexdigest(),
        'grammar_root': next((line for line in formatted.get('grammar', '').splitlines() if line.startswith('root ::= ')), None),
        'raw_restarts_assistant': isinstance(raw, str) and raw.startswith('<|im_start|>assistant'),
        'raw_has_thinking_block': isinstance(raw, str) and '<think>' in raw,
        'delivered': delivered_contract(content),
        'diagnostic_candidate_only': candidate_from_debug(raw),
        'context_observations': [e['value'] for e in record['events'] if e['name'] == 'completion' and e['event'] == 'context'],
    }
