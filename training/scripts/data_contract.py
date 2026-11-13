"""Validate reviewed local smoke data without logging message contents."""
import difflib
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def persona(polite, root=ROOT):
    source = (root / 'app/src/main/java/ai/chloe/voicelab/conversation/ConversationEngine.kt').read_text(encoding='utf-8')
    text = re.search(r'fun system\(polite:Boolean\)="""(.*?)"""', source, re.S)
    if not text:
        raise ValueError('App persona source changed; review extraction')
    branch = re.search(r'\$\{if\(polite\)"([^"]*)" else "([^"]*)"\}', text[1])
    if not branch:
        raise ValueError('App persona register expression changed')
    return text[1][:branch.start()] + branch.group(1 if polite else 2) + text[1][branch.end():]


def check_schema(value, schema):
    if schema.get('type') == 'object':
        if not isinstance(value, dict):
            raise ValueError('Expected object')
        if not set(schema.get('required', ())) <= value.keys():
            raise ValueError('Missing output key')
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and not value.keys() <= properties.keys():
            raise ValueError('Unexpected output key')
        for name, item in value.items():
            check_schema(item, properties[name])
    if schema.get('type') == 'string':
        if not isinstance(value, str):
            raise ValueError('Expected string')
        # Kotlin String.length counts UTF-16 code units, including surrogate pairs.
        length = len(value.encode('utf-16-le')) // 2
        if not schema.get('minLength', 0) <= length <= schema.get('maxLength', float('inf')):
            raise ValueError('Output string length out of bounds')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Invalid output enum')


def validate_reply(raw, root=ROOT):
    obj = json.loads(raw)
    schema = json.loads((root / 'app/src/main/assets/conversation-schema.json').read_text(encoding='utf-8'))
    check_schema(obj, schema)
    if not obj['spoken_text'].strip() or any(ch in obj['spoken_text'] for ch in '{}<>'):
        raise ValueError('Unsafe spoken_text under app consumer contract')
    if obj['tts_instruction'] != '':
        raise ValueError('App persona requires empty tts_instruction')
    return obj


def diagnose_reply(raw, eos_reached, token_count, max_tokens, root=ROOT):
    """Content-free diagnostics; JSON syntax, schema and consumer checks differ."""
    errors = []
    try:
        obj = json.loads(raw)
    except (ValueError,TypeError):
        obj = None
        errors.append({'code':'json_syntax','path':'$'})
        syntax_valid = False
    else:
        syntax_valid = True
    schema = json.loads((root/'app/src/main/assets/conversation-schema.json').read_text(encoding='utf-8'))

    def inspect(value, rule, path):
        if rule.get('type')=='object':
            if not isinstance(value,dict):
                errors.append({'code':'object_type','path':path})
                return
            for key in rule.get('required',[]):
                if key not in value:
                    errors.append({'code':'missing_key','path':path+'.'+key})
            for key,item in value.items():
                if key not in rule.get('properties',{}):
                    errors.append({'code':'additional_key','path':path})
                else:
                    inspect(item,rule['properties'][key],path+'.'+key)
        if rule.get('type')=='string':
            if not isinstance(value,str):
                errors.append({'code':'string_type','path':path})
                return
            size=len(value.encode('utf-16-le'))//2
            if size < rule.get('minLength',0):
                errors.append({'code':'min_length','path':path})
            if size > rule.get('maxLength',float('inf')):
                errors.append({'code':'max_length','path':path})
        if 'enum' in rule and value not in rule['enum']:
            errors.append({'code':'enum','path':path})

    if syntax_valid:
        inspect(obj,schema,'$')
    schema_valid=syntax_valid and not errors
    if isinstance(obj,dict):
        spoken=obj.get('spoken_text')
        if isinstance(spoken,str):
            if not spoken.strip():
                errors.append({'code':'blank_spoken_text','path':'$.spoken_text'})
            if any(ch in spoken for ch in '{}<>'):
                errors.append({'code':'unsafe_spoken_text','path':'$.spoken_text'})
        if 'tts_instruction' in obj and obj['tts_instruction']!='':
            errors.append({'code':'nonempty_tts_instruction','path':'$.tts_instruction'})
    if not eos_reached:
        errors.append({'code':'token_limit' if token_count>=max_tokens else 'unfinished','path':'$'})
    return {'json_syntax_valid':syntax_valid,'schema_valid':schema_valid,
            'contract_valid':not errors,'errors':errors}


def normalized(text):
    return re.sub(r'[^0-9a-z가-힣]', '', text.lower())


def load_records(path, root=ROOT):
    records = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not records:
        raise ValueError('Dataset is empty')
    plan = json.loads((root / 'training/configs/evaluation-plan.json').read_text(encoding='utf-8'))
    for name, evidence in plan['sources'].items():
        raw = (root / name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != evidence['lf_normalized_sha256']:
            raise ValueError('Frozen evaluation/persona source changed')
    fixtures = json.loads((root / 'app/src/main/assets/conversation-cases.json').read_text(encoding='utf-8'))['cases']
    reserved = [normalized(case['input']) for case in fixtures + plan['supplemental_cases']]
    ids, families, prompts = set(), {}, {}
    for row in records:
        if row['id'] in ids:
            raise ValueError('Duplicate record id')
        ids.add(row['id'])
        if row['review_status'] != 'approved' or not row.get('reviewer'):
            raise ValueError('Dataset requires explicit human review approval')
        if row.get('approval_scope') != '10-step mechanical smoke only':
            raise ValueError('This trainer accepts smoke-only approval')
        if not row.get('source') or not row.get('license') or 'pending' in row['license'].lower():
            raise ValueError('Dataset provenance/license missing or pending')
        split, family = row['split'], row['family_id']
        if split not in ('train', 'validation', 'test') or not family:
            raise ValueError('Invalid split/family')
        if family in families and families[family] != split:
            raise ValueError('Conversation family leaks across splits')
        families[family] = split
        messages = row['messages']
        if [m['role'] for m in messages] != ['system', 'user', 'assistant']:
            raise ValueError('Smoke records must contain one complete system/user/assistant turn')
        if row['register'] not in ('casual', 'polite') or messages[0]['content'] != persona(row['register']=='polite', root):
            raise ValueError('System persona differs from app')
        prompt = normalized(messages[1]['content'])
        if not prompt:
            raise ValueError('Empty user input')
        if split in ('train', 'validation') and any(
                difflib.SequenceMatcher(None, prompt, other).ratio() >= 0.85 for other in reserved):
            raise ValueError('Reserved evaluation input or near duplicate in learning data')
        for other, other_split in prompts.items():
            if split != other_split and difflib.SequenceMatcher(None, prompt, other).ratio() >= 0.85:
                raise ValueError('Near-duplicate prompt across splits')
        prompts[prompt] = split
        validate_reply(messages[-1]['content'], root)
    return records
