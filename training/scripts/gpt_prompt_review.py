"""Prepare masked GPT review and aggregate explicit session judgments, without APIs.

This script does not judge text. The GPT assistant reads the masked packet and
records rubric judgments; only then may aggregate() reveal candidate identities.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import secrets

from data_contract import ROOT
from llm_runtime import artifact_output, write_json
from prompt_suite import read_plan, suite

DIMENSIONS = ('register','relevance','naturalness','identity','honesty','memory','instruction_protection')
VALUES = ('pass','partial','fail','not_applicable')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def applicable(row):
    dimensions = {'register','relevance','naturalness'}
    case = row['case_id']
    if case in ('identity01','identity02'):
        dimensions.add('identity')
    if case in ('conv31','conv32','conv35','conv38','register01'):
        dimensions.add('honesty')
    if case in ('conv43','conv44','conv45','conv46','conv49','conv50') or row['id'].startswith('summary:'):
        dimensions.add('memory')
    if case in ('conv47','conv48'):
        dimensions.add('instruction_protection')
    return [d for d in DIMENSIONS if d in dimensions]


def prepare(source, output):
    source, output = artifact_output(str(source)), artifact_output(str(output))
    if output.exists():
        raise FileExistsError('Use a fresh review directory')
    summary = read(source/'summary.local.json')
    concise = summary.get('phase') == 'concise'
    expected = 92 if concise else 456
    if not summary['completed'] or len(summary['results']) != expected:
        raise ValueError('Completed factorial comparison required')
    plan_file = 'prompt-comparison-concise.json' if concise else 'prompt-comparison-plan.json'
    if summary['plan_lf_sha256'] != digest(ROOT/'training/configs'/plan_file):
        raise ValueError('Prompt/review plan changed after inference')
    if concise and summary['base_plan_sha256'] != digest(ROOT/'training/configs/prompt-comparison-plan.json'):
        raise ValueError('Original situations/rubric changed for followup')
    situations, _ = suite()
    chosen = [row for row in situations if row['quality_review']]
    combinations = [(variant, candidate) for variant in (('concise',) if concise else ('original','revised')) for candidate in ('base','adapter')]
    secrets.SystemRandom().shuffle(combinations)
    labels = {f'K{n+1}': {'variant':v,'candidate':c} for n,(v,c) in enumerate(combinations)}
    packet = {'review_id':secrets.token_hex(16),'reviewer_kind':'gpt_session',
              'rubric':read_plan()['review'],'situations':[]}
    source_hashes = {}
    key = {'review_id':packet['review_id'],'candidates':labels,'situations':{}}
    for number, row in enumerate(chosen, 1):
        ident = f'J{number:03d}'
        expected_register = row['register']
        if row['mode'] == 'follow_user':
            expected_register = 'polite' if row['case_id']=='conv41' else 'casual'
        entry = {'id':ident,'question':row['input'],'policy':row['mode'],'initial_register':row['register'],
                 'expected_register':expected_register,'applicable_dimensions':applicable(row),
                 'initial_history':row['initial_history'],'sequence':row['sequence'],'answers':{}}
        for label, cell in labels.items():
            filename = f'{cell["variant"]}-{cell["candidate"]}-{row["id"].replace(":","-")}.local.json'
            saved = read(source/filename)
            if saved['situation'] != row:
                raise ValueError('Situation/source mismatch')
            response = saved['response']
            entry['answers'][label] = {'spoken_text':response['reply']['spoken_text'] if response['reply'] else None,
                                       'history':saved['messages'][1:-1]}
            source_hashes[filename] = digest(source/filename)
        packet['situations'].append(entry)
        key['situations'][ident] = row['id']
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'packet.local.json',packet)
    write_json(output/'key.local.json',key)
    write_json(output/'provenance.local.json',{'summary_sha256':digest(source/'summary.local.json'),
               'packet_sha256':digest(output/'packet.local.json'),'key_sha256':digest(output/'key.local.json'),
               'source_response_hashes':source_hashes})
    print(json.dumps({'review_situations':len(chosen),'response_judgments':len(chosen)*len(labels)}))


def aggregate(review):
    review = artifact_output(str(review))
    provenance = read(review/'provenance.local.json')
    if digest(review/'packet.local.json') != provenance['packet_sha256'] or digest(review/'key.local.json') != provenance['key_sha256']:
        raise ValueError('Review packet/key changed')
    packet, key, verdicts = [read(review/name) for name in ('packet.local.json','key.local.json','verdicts.local.json')]
    if verdicts.get('review_id') != packet['review_id'] or verdicts.get('reviewer_kind') != 'gpt_session':
        raise ValueError('Review identity/kind mismatch')
    judgments = verdicts['judgments']
    if set(judgments) != {r['id'] for r in packet['situations']}:
        raise ValueError('Missing/extra situation judgments')
    counters = {f'{cell["variant"]}:{cell["candidate"]}': {dim:Counter({v:0 for v in VALUES}) for dim in DIMENSIONS}
                for cell in key['candidates'].values()}
    strict = {name:0 for name in counters}
    for row in packet['situations']:
        evaluated = judgments[row['id']]
        if set(evaluated) != set(key['candidates']):
            raise ValueError('Missing candidate judgment')
        for label, values in evaluated.items():
            if set(values) != set(DIMENSIONS) or any(v not in VALUES for v in values.values()):
                raise ValueError('Malformed dimension verdict')
            for dim, value in values.items():
                if (dim in row['applicable_dimensions']) == (value == 'not_applicable'):
                    raise ValueError('Applicable dimension was skipped or NA dimension was scored')
            cell = key['candidates'][label]
            name = f'{cell["variant"]}:{cell["candidate"]}'
            for dim, value in values.items():
                counters[name][dim][value] += 1
            if all(values[d] == 'pass' for d in row['applicable_dimensions']):
                strict[name] += 1
    result = {'review_id':packet['review_id'],'reviewer_kind':'gpt_session','gpt_review_completed':True,
              'human_review':False,'review_situations':len(packet['situations']),
              'judgment_count':len(packet['situations'])*len(key['candidates']),'rubric':packet['rubric'],
              'dimension_counts':{cell:{d:dict(c) for d,c in dims.items()} for cell,dims in counters.items()},
              'strict_all_applicable_pass':strict,
              'verdicts_sha256':digest(review/'verdicts.local.json'),
              'review_packet_sha256':provenance['packet_sha256'],'key_commitment_sha256':provenance['key_sha256'],
              'source_summary_sha256':provenance['summary_sha256'],'model_promotion_approved':False,
              'additional_training':False,'raw_responses_included':False,'raw_judgment_notes_included':False}
    write_json(review/'aggregate.local.json',result)
    print(json.dumps({'strict_all_applicable_pass':strict,'review_situations':len(packet['situations'])}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--source',required=True)
    prepare_parser.add_argument('--output',required=True)
    aggregate_parser = sub.add_parser('aggregate')
    aggregate_parser.add_argument('--review',required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.source,args.output)
    else:
        aggregate(args.review)


if __name__ == '__main__':
    main()
