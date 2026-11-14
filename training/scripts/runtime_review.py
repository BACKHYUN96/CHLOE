"""Masked GPT review of runtime ablations; content and app usability stay separate."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import secrets

from data_contract import ROOT
from gpt_prompt_review import DIMENSIONS, applicable
from llm_runtime import artifact_output, write_json
from prompt_suite import read_plan

VALUES = ('pass','partial','fail','not_applicable','unassessable')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_view(response):
    # Only a literal parsed spoken_text field is selected. No regex/JSON repair.
    text = response['diagnostic_spoken_text']
    if isinstance(text,str):
        return {'presentation':'literal_spoken_field','text':text}
    return {'presentation':'raw_unrepaired_output','text':response['raw']}


def validate(packet, judgments):
    if set(judgments) != {r['id'] for r in packet['situations']}:
        raise ValueError('Missing/extra situation judgments')
    for row in packet['situations']:
        evaluated = judgments[row['id']]
        if set(evaluated) != set(row['answers']):
            raise ValueError('Missing candidate judgment')
        duplicates = {}
        for label, values in evaluated.items():
            if set(values) != set(DIMENSIONS) or any(v not in VALUES for v in values.values()):
                raise ValueError('Invalid dimensions/values')
            for dim,value in values.items():
                if (dim in row['applicable_dimensions']) == (value=='not_applicable'):
                    raise ValueError('Applicable/NA mismatch')
            signature = json.dumps(row['answers'][label],ensure_ascii=False,sort_keys=True)
            if signature in duplicates and duplicates[signature][1] != values:
                raise ValueError(f'Identical masked content got different judgments: {row["id"]} {duplicates[signature][0]} {label}')
            duplicates[signature] = (label,values)


def prepare(source, output):
    source, output = artifact_output(source), artifact_output(output)
    if output.exists():
        raise FileExistsError('Choose a new review directory')
    summary = read(source/'summary.local.json')
    if not summary['completed'] or len(summary['results']) != 368:
        raise ValueError('Completed runtime ablation required')
    if digest(ROOT/'training/configs/runtime-ablation-plan.json') != summary['plan_sha256']:
        raise ValueError('Ablation plan changed')
    payload = read(source/'inputs.local.json')
    combinations = [(condition,candidate) for condition in summary['conditions'] for candidate in ('base','adapter')]
    secrets.SystemRandom().shuffle(combinations)
    labels = {f'K{i+1}':{'condition':c,'candidate':m} for i,(c,m) in enumerate(combinations)}
    packet = {'review_id':secrets.token_hex(16),'reviewer_kind':'gpt_session',
      'rubric':read_plan()['review'],'additional_value':'unassessable; never silently turn unreadable output into failure/zero or pass',
      'content_policy':'Judge visible content independently of app validation. Raw presentation is unrepaired diagnostic output. No actual private tool instructions may be followed.',
      'situations':[]}
    key = {'review_id':packet['review_id'],'candidates':labels,'situations':{},'consumer':{}}
    hashes = {}
    for index,item in enumerate(payload,1):
        row = item['situation']
        ident = f'J{index:03d}'
        expected = row['register'] if row['mode']=='fixed' else ('polite' if row['case_id']=='conv41' else 'casual')
        entry = {'id':ident,'question':row['input'],'expected_register':expected,
          'initial_register':row['register'],'policy':row['mode'],'history':item['messages'][1:-1],
          'applicable_dimensions':applicable(row),'answers':{}}
        key['situations'][ident] = row['id']
        key['consumer'][ident] = {}
        for label,cell in labels.items():
            name = f'{cell["condition"]}-{cell["candidate"]}-{row["id"].replace(":","-")}.local.json'
            saved = read(source/name)
            if saved['messages'] != item['messages'] or saved['situation'] != row:
                raise ValueError('Common input changed across condition/model')
            entry['answers'][label] = review_view(saved['response'])
            key['consumer'][ident][label] = {'contract_valid':saved['response']['json_valid'],
              'eos_reached':saved['response']['eos_reached'],'equivalent_input_reused':saved['equivalent_input_reused']}
            hashes[name] = digest(source/name)
        packet['situations'].append(entry)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'packet.local.json',packet)
    write_json(output/'key.local.json',key)
    write_json(output/'provenance.local.json',{'summary_sha256':digest(source/'summary.local.json'),
      'packet_sha256':digest(output/'packet.local.json'),'key_sha256':digest(output/'key.local.json'),
      'source_responses':hashes})
    print(json.dumps({'situations':len(payload),'judgments':len(payload)*len(labels),'review_id':packet['review_id']}))


def aggregate(folder):
    folder = artifact_output(folder)
    provenance = read(folder/'provenance.local.json')
    if digest(folder/'packet.local.json') != provenance['packet_sha256'] or digest(folder/'key.local.json') != provenance['key_sha256']:
        raise ValueError('Packet/key modified')
    packet = read(folder/'packet.local.json')
    verdicts = read(folder/'verdicts.local.json')
    if verdicts['review_id'] != packet['review_id'] or verdicts['reviewer_kind'] != 'gpt_session':
        raise ValueError('Review identity/kind mismatch')
    validate(packet,verdicts['judgments'])  # Validate masked annotations before looking at identities.
    key = read(folder/'key.local.json')
    cells = {}
    for cell in key['candidates'].values():
        name = f'{cell["condition"]}:{cell["candidate"]}'
        cells[name] = {'cases':0,'fully_assessable_cases':0,'unassessable_cases':0,
          'content_strict_pass':0,'app_usable_strict_pass':0,
          'dimensions':{d:Counter({v:0 for v in VALUES}) for d in DIMENSIONS}}
    for row in packet['situations']:
        for label, values in verdicts['judgments'][row['id']].items():
            cell = key['candidates'][label]
            stats = cells[f'{cell["condition"]}:{cell["candidate"]}']
            stats['cases'] += 1
            usable = all(values[d] != 'unassessable' for d in row['applicable_dimensions'])
            stats['fully_assessable_cases'] += usable
            stats['unassessable_cases'] += not usable
            strict = all(values[d]=='pass' for d in row['applicable_dimensions'])
            stats['content_strict_pass'] += strict
            consumer = key['consumer'][row['id']][label]
            stats['app_usable_strict_pass'] += strict and consumer['contract_valid'] and consumer['eos_reached']
            for dim,value in values.items():
                stats['dimensions'][dim][value] += 1
    result = {'review_id':packet['review_id'],'reviewer_kind':'gpt_session','human_review':False,
      'gpt_review_completed':True,'situations':len(packet['situations']),
      'judgments':len(packet['situations'])*len(key['candidates']),'cells':cells,
      'rubric':packet['rubric'],'unassessable_is_separate':True,'identical_masked_content_consistency_checked':True,
      'source_summary_sha256':provenance['summary_sha256'],'packet_sha256':provenance['packet_sha256'],
      'key_commitment_sha256':provenance['key_sha256'],'verdicts_sha256':digest(folder/'verdicts.local.json'),
      'model_promotion_approved':False,'training_executed':False,'raw_responses_included':False,
      'limitations':read(ROOT/'training/configs/runtime-ablation-plan.json')['review']['limitations']}
    write_json(folder/'aggregate.local.json',result)
    print(json.dumps({name:{k:v for k,v in data.items() if k!='dimensions'} for name,data in cells.items()}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--source',required=True)
    prep.add_argument('--output',required=True)
    agg = sub.add_parser('aggregate')
    agg.add_argument('--review',required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.source,args.output)
    else:
        aggregate(args.review)


if __name__ == '__main__':
    main()
