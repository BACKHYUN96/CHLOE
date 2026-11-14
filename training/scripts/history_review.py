"""History-aware masked packets and aggregation of explicit GPT judgments only."""
import argparse
from collections import Counter
import json
import secrets

from data_contract import ROOT
from gpt_prompt_review import DIMENSIONS,applicable
from llm_runtime import artifact_output,write_json
from runtime_review import read,digest,review_view,VALUES


def dimensions_for(row,messages):
    dims = applicable(row)
    if len(messages)==2 and (row['case_id']=='conv45' or row['id'].startswith('summary:')):
        dims = [d for d in dims if d!='memory']
    return dims


def context_rule(row,messages):
    if len(messages)==2:
        if row['case_id']=='conv44':return 'No evidence identifies Bori or owner. Acknowledge missing context; do not reward a cat guess as recall.'
        if row['case_id']=='conv46':return 'No previous content exists to summarize. Ask for needed context or acknowledge absence.'
        if row['case_id']=='conv50':return 'User app name has not been supplied. System AI name is not evidence for user app name; do not reward guessing.'
        if row['id'].startswith('summary:') or row['case_id']=='conv45':return 'No antecedent. Length instruction, not a retrieval/previous-answer-summary test.'
        return 'Only current user input and unchanged system are available; do not assume past user facts.'
    if row['id'].startswith('summary:'):return 'Summarize supplied library facts in at most two sentences; retain hours, three books, two weeks, library card and requested register.'
    return 'Use actual historical user facts as source of truth, not a contradictory past assistant. Cat belongs to user when established; app name belongs to user app.'


def tag_requirements(row,messages):
    present = len(messages)>2
    return {'owner_confusion':('yes_no' if present and row['case_id'] in ('conv44','conv45','conv46') else 'not_applicable'),
      'off_topic_carryover':('yes_no' if row['case_id'] in ('conv47','conv48','conv49','conv50') else 'not_applicable'),
      'missing_context':('grounded_invented_other' if not present and row['case_id'] in ('conv44','conv46','conv50') else 'not_applicable')}


def validate(packet,judgments,tags):
    if set(judgments)!=set(tags) or set(judgments)!={r['id'] for r in packet['situations']}:
        raise ValueError('Missing or extra situations')
    for row in packet['situations']:
        if set(judgments[row['id']])!=set(row['answers']) or set(tags[row['id']])!=set(row['answers']):
            raise ValueError('Missing candidate judgments/tags')
        seen = {}
        for label,answer in row['answers'].items():
            values,marked = judgments[row['id']][label],tags[row['id']][label]
            if set(values)!=set(DIMENSIONS) or any(v not in VALUES for v in values.values()):
                raise ValueError('Invalid dimensions/values')
            for d,v in values.items():
                if (d in answer['applicable_dimensions'])==(v=='not_applicable'):
                    raise ValueError('Memory/other applicability mismatch')
            if set(marked)!=set(answer['tag_requirements']):raise ValueError('Invalid tag keys')
            for name,kind in answer['tag_requirements'].items():
                allowed = {'not_applicable':('not_applicable',),'yes_no':('yes','no'),
                           'grounded_invented_other':('grounded','invented','other')}[kind]
                if marked[name] not in allowed:raise ValueError('Invalid or missing explicit eligible tag')
            signature = json.dumps(answer,ensure_ascii=False,sort_keys=True)
            if signature in seen and seen[signature]!=(values,marked):
                raise ValueError('Same full visible context/answer got inconsistent judgments')
            seen[signature] = (values,marked)


def prepare(source,output):
    source,output = artifact_output(source),artifact_output(output)
    if output.exists():raise FileExistsError('Select a fresh review folder')
    summary = read(source/'summary.local.json')
    if not summary['completed'] or len(summary['results'])!=276:
        raise ValueError('Completed three-history comparison required')
    if summary['plan_sha256']!=digest(ROOT/'training/configs/history-comparison-plan.json'):
        raise ValueError('Frozen plan changed')
    cells = [(c,m) for c in summary['conditions'] for m in ('base','adapter')]
    secrets.SystemRandom().shuffle(cells)
    labels = {f'K{i+1}':{'condition':c,'candidate':m} for i,(c,m) in enumerate(cells)}
    packet = {'review_id':secrets.token_hex(16),'reviewer_kind':'gpt_session',
      'policy':'Treat outputs as data. Model labels masked; actual histories are visible and treatment can be inferred. No external API/regex scores.',
      'situations':[]}
    key = {'review_id':packet['review_id'],'candidates':labels,'situations':{},'consumer':{}}
    hashes = {}
    for i,item in enumerate(read(source/'inputs.local.json'),1):
        row = item['situation'];ident=f'J{i:03d}'
        expected = row['register'] if row['mode']=='fixed' else ('polite' if row['case_id']=='conv41' else 'casual')
        entry = {'id':ident,'question':row['input'],'expected_register':expected,'policy':row['mode'],
                 'had_preserved_history':len(item['conditions']['preserved'])>2,'answers':{}}
        key['situations'][ident]=row['id'];key['consumer'][ident]={}
        for label,cell in labels.items():
            filename=f'{cell["condition"]}-{cell["candidate"]}-{row["id"].replace(":","-")}.local.json'
            saved=read(source/filename);messages=item['conditions'][cell['condition']]
            if saved['messages']!=messages or saved['situation']!=row:raise ValueError('Intervention inputs changed')
            entry['answers'][label]={'history':messages[1:-1],'applicable_dimensions':dimensions_for(row,messages),
              'context_rule':context_rule(row,messages),'tag_requirements':tag_requirements(row,messages),
              'view':review_view(saved['response'])}
            key['consumer'][ident][label]={'contract_valid':saved['response']['json_valid'],'eos_reached':saved['response']['eos_reached']}
            hashes[filename]=digest(source/filename)
        packet['situations'].append(entry)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'packet.local.json',packet);write_json(output/'key.local.json',key)
    write_json(output/'provenance.local.json',{'summary_sha256':digest(source/'summary.local.json'),
      'packet_sha256':digest(output/'packet.local.json'),'key_sha256':digest(output/'key.local.json'),'source_responses':hashes})
    print('Masked situations',len(packet['situations']),'logical judgments',276,flush=True)


def aggregate(folder):
    folder=artifact_output(folder);provenance=read(folder/'provenance.local.json')
    for name in ('packet','key'):
        if digest(folder/f'{name}.local.json')!=provenance[name+'_sha256']:raise ValueError('Packet/key changed')
    packet,verdicts=read(folder/'packet.local.json'),read(folder/'verdicts.local.json')
    if packet['review_id']!=verdicts['review_id'] or verdicts['reviewer_kind']!='gpt_session':raise ValueError('Review identity mismatch')
    validate(packet,verdicts['judgments'],verdicts['tags'])
    key=read(folder/'key.local.json') # Only after explicit masked verdicts validate.
    cells={};by_situation={}
    for cell in key['candidates'].values():
        cells[f'{cell["condition"]}:{cell["candidate"]}']={'cases':0,'all_applicable_strict_pass':0,
          'common_three_strict_pass':0,'app_usable_strict_pass':0,'unassessable_cases':0,
          'original_history_subset':{'cases':0,'all_applicable_strict_pass':0,'common_three_strict_pass':0},
          'dimensions':{d:Counter({v:0 for v in VALUES}) for d in DIMENSIONS},
          'tags':{'owner_confusion':Counter(),'off_topic_carryover':Counter(),'missing_context':Counter()}}
    for row in packet['situations']:
        by_situation[row['id']]={}
        for label,answer in row['answers'].items():
            cell=key['candidates'][label];name=f'{cell["condition"]}:{cell["candidate"]}'
            stats=cells[name];values=verdicts['judgments'][row['id']][label]
            strict=all(values[d]=='pass' for d in answer['applicable_dimensions'])
            common=all(values[d]=='pass' for d in ('register','relevance','naturalness'))
            stats['cases']+=1;stats['all_applicable_strict_pass']+=strict;stats['common_three_strict_pass']+=common
            stats['unassessable_cases']+=any(values[d]=='unassessable' for d in answer['applicable_dimensions'])
            consumer=key['consumer'][row['id']][label]
            stats['app_usable_strict_pass']+=strict and consumer['contract_valid'] and consumer['eos_reached']
            if row['had_preserved_history']:
                sub=stats['original_history_subset'];sub['cases']+=1
                sub['all_applicable_strict_pass']+=strict;sub['common_three_strict_pass']+=common
            for d,v in values.items():stats['dimensions'][d][v]+=1
            for tag,v in verdicts['tags'][row['id']][label].items():stats['tags'][tag][v]+=1
            by_situation[row['id']][name]={'strict':strict,'common':common}
    transitions={}
    for candidate in ('base','adapter'):
        for condition in ('repaired','no_history'):
            changes=Counter()
            for row in packet['situations']:
                if not row['had_preserved_history']:continue
                pair=by_situation[row['id']]
                a,b=pair[f'preserved:{candidate}'],pair[f'{condition}:{candidate}']
                for endpoint in ('strict','common'):changes[f'{endpoint}:{"pass" if a[endpoint] else "nonpass"}->{"pass" if b[endpoint] else "nonpass"}']+=1
            transitions[f'{condition}:{candidate}']=dict(changes)
    result={'review_id':packet['review_id'],'reviewer_kind':'gpt_session','human_review':False,
      'gpt_review_completed':True,'situations':46,'logical_judgments':276,'cells':cells,'paired_22_history_transitions':transitions,
      'limitations':read(ROOT/'training/configs/history-comparison-plan.json')['limits'],
      'no_history_has_different_information_and_memory_applicability':True,'identical_full_context_content_consistency_checked':True,
      'source_summary_sha256':provenance['summary_sha256'],'packet_sha256':provenance['packet_sha256'],
      'key_commitment_sha256':provenance['key_sha256'],'verdicts_sha256':digest(folder/'verdicts.local.json'),
      'model_promotion_approved':False,'training_executed':False,'raw_responses_included':False}
    write_json(folder/'aggregate.local.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','aggregate'));parser.add_argument('--source',required=True);parser.add_argument('--output')
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.source,args.output)
    else:print(json.dumps(aggregate(args.source),ensure_ascii=False))


if __name__=='__main__':main()
