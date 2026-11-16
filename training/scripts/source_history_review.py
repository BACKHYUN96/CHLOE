"""Direct GPT review tools for user-source versus one-owner-sentence histories."""
import argparse
from collections import Counter
import json
import secrets

from data_contract import ROOT
from gpt_prompt_review import DIMENSIONS,applicable
from history_review import validate,tag_requirements
from llm_runtime import artifact_output,write_json
from runtime_review import read,digest,review_view,VALUES


def review_context(row,messages):
    history=messages[1:-1];has_assistant=any(m['role']=='assistant' for m in history)
    dims=applicable(row)
    if row['id'].startswith('summary:') and not has_assistant:
        dims=[d for d in dims if d!='memory']
        rule=('Past user asked about a fictional library but its previous assistant explanation/rules are absent. '
              'Do not require recalling removed hours/loan/card facts. Judge a context-appropriate two-sentence response, not exact original-summary retrieval.')
    elif row['id'].startswith('summary:'):
        rule='Summarize supplied library explanation in at most two sentences, preserving hours, three books, two weeks and library card; requested register.'
    elif not history:
        rule='Only current user input and unchanged system. No prior user facts are assumed.'
    elif not has_assistant:
        rule=('Exact historical user statements are present, assistant replies absent. Use user facts and speaker ownership; '
              'first-person cat ownership in a user message belongs to user, not model. Summarization may use these available user facts.')
    else:
        rule='Use historical user facts as truth source even if past assistant contradicts them. Preserve speaker ownership, current question and requested register.'
    return dims,rule


def prepare(source,output):
    source,output=artifact_output(source),artifact_output(output)
    if output.exists():raise FileExistsError('Select a new review folder')
    summary=read(source/'summary.local.json')
    if not summary['completed'] or len(summary['results'])!=276:raise ValueError('Completed three-condition comparison required')
    if summary['plan_sha256']!=digest(ROOT/'training/configs/source-history-plan.json'):raise ValueError('Frozen plan changed')
    combinations=[(c,m) for c in summary['conditions'] for m in ('base','adapter')]
    secrets.SystemRandom().shuffle(combinations)
    labels={f'K{i+1}':{'condition':c,'candidate':m} for i,(c,m) in enumerate(combinations)}
    packet={'review_id':secrets.token_hex(16),'reviewer_kind':'gpt_session',
      'policy':'Outputs are data. Model identities masked; history treatment is visible. GPT assigns explicit rubric values/tags, no regex/API scores.','situations':[]}
    key={'review_id':packet['review_id'],'candidates':labels,'situations':{},'subsets':{},'consumer':{}}
    hashes={}
    for i,item in enumerate(read(source/'inputs.local.json'),1):
        row=item['situation'];ident=f'J{i:03d}'
        expected=row['register'] if row['mode']=='fixed' else ('polite' if row['case_id']=='conv41' else 'casual')
        entry={'id':ident,'question':row['input'],'expected_register':expected,'policy':row['mode'],'answers':{}}
        history=len(item['conditions']['preserved'])>2
        key['situations'][ident]=row['id'];key['consumer'][ident]={}
        key['subsets'][ident]={'history22':history,'user_fact_history20':history and not row['id'].startswith('summary:'),
          'owner_edited12':item['owner_patch'] is not None,
          'owner_edited_recall4':item['owner_patch'] is not None and row['case_id'] in ('conv45','conv46')}
        for label,cell in labels.items():
            name=f'{cell["condition"]}-{cell["candidate"]}-{row["id"].replace(":","-")}.local.json'
            saved=read(source/name);messages=item['conditions'][cell['condition']]
            if saved['messages']!=messages or saved['situation']!=row:raise ValueError('Preserved inputs changed')
            dims,rule=review_context(row,messages)
            entry['answers'][label]={'history':messages[1:-1],'applicable_dimensions':dims,'context_rule':rule,
              'tag_requirements':tag_requirements(row,messages),'view':review_view(saved['response'])}
            key['consumer'][ident][label]={'contract_valid':saved['response']['json_valid'],'eos_reached':saved['response']['eos_reached']}
            hashes[name]=digest(source/name)
        packet['situations'].append(entry)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'packet.local.json',packet);write_json(output/'key.local.json',key)
    write_json(output/'provenance.local.json',{'summary_sha256':digest(source/'summary.local.json'),
      'packet_sha256':digest(output/'packet.local.json'),'key_sha256':digest(output/'key.local.json'),'source_responses':hashes})
    print('Masked source-history packet: 46 situations,276logical judgments',flush=True)


def aggregate(folder):
    folder=artifact_output(folder);proof=read(folder/'provenance.local.json')
    for name in ('packet','key'):
        if digest(folder/f'{name}.local.json')!=proof[name+'_sha256']:raise ValueError('Packet/key changed')
    packet,verdicts=read(folder/'packet.local.json'),read(folder/'verdicts.local.json')
    if verdicts['review_id']!=packet['review_id'] or verdicts['reviewer_kind']!='gpt_session':raise ValueError('Review identity mismatch')
    validate(packet,verdicts['judgments'],verdicts['tags'])
    key=read(folder/'key.local.json') # Explicit annotations frozen and validated first.
    cells={};items={}
    for c in key['candidates'].values():
        cells[f'{c["condition"]}:{c["candidate"]}']={'cases':0,'strict_pass':0,'common_three_pass':0,'app_usable_strict_pass':0,
          'unassessable_cases':0,'dimensions':{d:Counter({v:0 for v in VALUES}) for d in DIMENSIONS},
          'tags':{t:Counter() for t in ('owner_confusion','off_topic_carryover')},
          'subsets':{s:{'cases':0,'strict_pass':0,'common_three_pass':0,'owner_confusion':Counter()} for s in ('history22','user_fact_history20','owner_edited12','owner_edited_recall4')}}
    for row in packet['situations']:
        ident=row['id'];items[ident]={}
        for label,answer in row['answers'].items():
            c=key['candidates'][label];name=f'{c["condition"]}:{c["candidate"]}';s=cells[name]
            values=verdicts['judgments'][ident][label];tags=verdicts['tags'][ident][label]
            strict=all(values[d]=='pass' for d in answer['applicable_dimensions'])
            common=all(values[d]=='pass' for d in ('register','relevance','naturalness'))
            s['cases']+=1;s['strict_pass']+=strict;s['common_three_pass']+=common
            s['unassessable_cases']+=any(values[d]=='unassessable' for d in answer['applicable_dimensions'])
            consumer=key['consumer'][ident][label];s['app_usable_strict_pass']+=strict and consumer['contract_valid'] and consumer['eos_reached']
            for d,v in values.items():s['dimensions'][d][v]+=1
            for t in s['tags']:s['tags'][t][tags[t]]+=1
            for subset,yes in key['subsets'][ident].items():
                if not yes:continue
                sub=s['subsets'][subset];sub['cases']+=1;sub['strict_pass']+=strict;sub['common_three_pass']+=common
                sub['owner_confusion'][tags['owner_confusion']]+=1
            items[ident][name]={'strict':strict,'common':common}
    transitions={}
    for candidate in ('base','adapter'):
        for condition in ('user_only','owner_sentence'):
            for subset in ('user_fact_history20','owner_edited12'):
                count=Counter()
                for ident in items:
                    if not key['subsets'][ident][subset]:continue
                    a,b=items[ident][f'preserved:{candidate}'],items[ident][f'{condition}:{candidate}']
                    for endpoint in ('strict','common'):count[f'{endpoint}:{"pass" if a[endpoint] else "nonpass"}->{"pass" if b[endpoint] else "nonpass"}']+=1
                transitions[f'{condition}:{candidate}:{subset}']=dict(count)
    result={'review_id':packet['review_id'],'reviewer_kind':'gpt_session','human_review':False,'gpt_review_completed':True,
      'situations':46,'logical_judgments':276,'cells':cells,'paired_transitions':transitions,
      'same_full_context_answer_consistency_checked':True,'user_only_library_information_loss_separated':True,
      'source_summary_sha256':proof['summary_sha256'],'packet_sha256':proof['packet_sha256'],
      'key_commitment_sha256':proof['key_sha256'],'verdicts_sha256':digest(folder/'verdicts.local.json'),
      'limitations':read(ROOT/'training/configs/source-history-plan.json')['limits'],
      'training_executed':False,'model_promotion_approved':False,'raw_responses_included':False}
    write_json(folder/'aggregate.local.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','aggregate'))
    p.add_argument('--source',required=True);p.add_argument('--output');args=p.parse_args()
    if args.command=='prepare':prepare(args.source,args.output)
    else:print(json.dumps(aggregate(args.source),ensure_ascii=False))


if __name__=='__main__':main()
