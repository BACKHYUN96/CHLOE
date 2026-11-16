"""Frozen prompt interventions and corrected evaluation situations; no model imports."""
import hashlib
import json
from pathlib import Path

from data_contract import ROOT, persona


def read_plan(root=ROOT):
    return json.loads((root/'training/configs/prompt-comparison-plan.json').read_text(encoding='utf-8'))


def verify_frozen(root=ROOT):
    frozen = json.loads((root/'training/configs/evaluation-plan.json').read_text(encoding='utf-8'))
    for relative, expected in frozen['sources'].items():
        actual = hashlib.sha256((root/relative).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected['lf_normalized_sha256']:
            raise ValueError('Original app evaluation/persona/schema changed')
    return frozen


def system_prompt(variant, register, mode='fixed', root=ROOT):
    plan = read_plan(root)
    if register not in plan['registers'] or variant not in plan['variants'] or mode not in ('fixed','follow_user'):
        raise ValueError('Unknown prompt/register/policy')
    if variant == 'original':
        text = persona(register == 'polite', root=root)
    else:
        text = '\n'.join(plan['revised_prompt_sections']).replace('{register_rule}', plan['register_rules'][register])
    if mode == 'follow_user':
        text += '\n'+plan['corrections']['follow_user_register']['shared_policy_suffix']
    return text


def concise_prompt(register, mode='fixed', root=ROOT):
    if register not in ('casual','polite') or mode not in ('fixed','follow_user'):
        raise ValueError('Unknown concise prompt register/policy')
    plan = json.loads((root/'training/configs/prompt-comparison-concise.json').read_text(encoding='utf-8'))
    text = '\n'.join(plan['sections']).replace('{register_rule}',plan['register_rules'][register])
    if mode == 'follow_user':
        text += '\n'+read_plan(root)['corrections']['follow_user_register']['shared_policy_suffix']
    return text


def suite(root=ROOT):
    frozen = verify_frozen(root)
    plan = read_plan(root)
    rows = json.loads((root/'app/src/main/assets/conversation-cases.json').read_text(encoding='utf-8'))['cases']
    rows += [dict(row, group=row['category']) for row in frozen['supplemental_cases']]
    questions = {row['id']: row['input'] for row in rows}
    situations = []
    for register in plan['registers']:
        for row in rows:
            situations.append({'id': f'fixed:{register}:{row["id"]}', 'case_id': row['id'],
                               'register': register, 'mode': 'fixed', 'input': row['input'],
                               'sequence': 'context' if row['group'] == 'context' else None,
                               'reset': row['group'] != 'context' or row['id'] == 'conv41',
                               'initial_history': [], 'quality_review': row['id'] in plan['quality_case_ids']})
        situations.append({'id': f'summary:{register}:conv30', 'case_id': 'conv30',
                           'register': register, 'mode': 'fixed', 'input': questions['conv30'],
                           'sequence': None, 'reset': True,
                           'initial_history': plan['corrections']['summary_with_context']['history'],
                           'quality_review': True})
        for index, case in enumerate(plan['corrections']['follow_user_register']['question_sources']):
            situations.append({'id': f'follow:{register}:{case}', 'case_id': case,
                               'register': register, 'mode': 'follow_user', 'input': questions[case],
                               'sequence': 'follow', 'reset': index == 0, 'initial_history': [],
                               'quality_review': True})
    if len(situations) != 114 or len({r['id'] for r in situations}) != 114:
        raise ValueError('Expected 108 frozen situations plus six corrected conditions')
    return situations, frozen['generation']


def trim_history(history):
    history = list(history)
    while len(history) > 4 or sum(len((u+a).encode('utf-16-le'))//2 for u,a in history) > 1200:
        history.pop(0)
    return history


def messages_for(situation, variant, history):
    messages = [{'role': 'system', 'content': system_prompt(variant, situation['register'], situation['mode'])}]
    for user, answer in history:
        messages.extend([{'role':'user', 'content':user}, {'role':'assistant','content':answer}])
    messages.append({'role':'user','content':situation['input']})
    return messages
