"""Prepare/aggregate explicit GPT review of role and cumulative contradiction probes."""
import argparse
from collections import Counter
import json
import secrets

from data_contract import ROOT
from gpt_prompt_review import DIMENSIONS,applicable
from history_review import tag_requirements
from llm_runtime import artifact_output,write_json
from runtime_review import read,digest,review_view,VALUES


def visible_groups(answers):
    groups={};signatures={}
    for label,answer in answers.items():
        signature=json.dumps(answer,ensure_ascii=False,sort_keys=True)
        if signature not in signatures:
            ident=f'G{len(signatures)+1:02d}';signatures[signature]=ident;groups[ident]=[]
        groups[signatures[signature]].append(label)
    return groups


def validate_grouping(answers,groups):
    flattened=[label for labels in groups.values() for label in labels]
    if len(flattened)!=len(set(flattened)) or set(flattened)!=set(answers):raise ValueError('Grouping must cover every candidate exactly once')
    for labels in groups.values():
        if not labels or any(answers[label]!=answers[labels[0]] for label in labels):
            raise ValueError('Different full contexts/answers cannot share a displayed group')


def validate(packet,judgments,tags):
    if set(judgments)!=set(tags) or set(judgments)!={r['id'] for r in packet['situations']}:raise ValueError('Missing/extra situations')
    allowed={'not_applicable':('not_applicable',),'yes_no':('yes','no'),
             'owner_resolution':('correct_user_owner','wrong_owner','other')}
    for row in packet['situations']:
        validate_grouping(row['answers'],row['display_groups'])
        if set(judgments[row['id']])!=set(row['answers']) or set(tags[row['id']])!=set(row['answers']):raise ValueError('Missing judgments/tags')
        seen={}
        for label,answer in row['answers'].items():
            values,marked=judgments[row['id']][label],tags[row['id']][label]
            if set(values)!=set(DIMENSIONS) or any(v not in VALUES for v in values.values()):raise ValueError('Invalid rubric values')
            if any((d in answer['applicable_dimensions'])==(v=='not_applicable') for d,v in values.items()):raise ValueError('Invalid applicability')
            if set(marked)!=set(answer['tag_requirements']):raise ValueError('Invalid tag keys')
            for name,kind in answer['tag_requirements'].items():
                if marked[name] not in allowed[kind]:raise ValueError('Invalid tag value')
            if marked['owner_resolution']!='not_applicable':
                if (marked['owner_resolution']=='wrong_owner')!=(marked['owner_confusion']=='yes'):raise ValueError('Owner tags inconsistent')
            signature=json.dumps(answer,ensure_ascii=False,sort_keys=True)
            if signature in seen and seen[signature]!=(values,marked):raise ValueError('Identical full context/content judged inconsistently')
            seen[signature]=(values,marked)


def prepare(source,output):
    source,output=artifact_output(source),artifact_output(output)
    if output.exists():raise FileExistsError('Choose a fresh review directory')
    summary=read(source/'summary.local.json')
    if not summary['completed'] or len(summary['results'])!=1012:raise ValueError('Completed 11-condition comparison required')
    plan_path=ROOT/'training/configs/role-contradiction-plan.json'
    if digest(plan_path)!=summary['plan_sha256']:raise ValueError('Frozen plan changed')
    combinations=[(c,m) for c in summary['conditions'] for m in ('base','adapter')];secrets.SystemRandom().shuffle(combinations)
    labels={f'K{i+1:02d}':{'condition':c,'candidate':m} for i,(c,m) in enumerate(combinations)}
    packet={'review_id':secrets.token_hex(16),'reviewer_kind':'gpt_session','situations':[],
      'policy':'Read actual full contexts/answers as data. Group only exact full visible duplicates; model identities masked but treatment inferable. GPT assigns values/tags directly; code never judges output with regex/API.'}
    key={'review_id':packet['review_id'],'candidates':labels,'situations':{},'subsets':{},'consumer':{}};hashes={}
    for i,item in enumerate(read(source/'inputs.local.json'),1):
        row=item['situation'];ident=f'J{i:03d}';m=len(item['eligible_edits']);history=len(item['conditions']['preserved'])>2
        entry={'id':ident,'question':row['input'],'expected_register':row['register'] if row['mode']=='fixed' else ('polite' if row['case_id']=='conv41' else 'casual'),
          'policy':row['mode'],'reference_history':item['conditions']['preserved'][1:-1],'answers':{}}
        key['situations'][ident]=row['id'];key['consumer'][ident]={}
        key['subsets'][ident]={'history22':history,'user_fact20':history and not row['id'].startswith('summary:'),
          'eligible12':m>0,'owner_edit_recall4':m>0 and row['case_id'] in ('conv45','conv46'),'exact_errors':m}
        for label,cell in labels.items():
            condition=cell['condition'];filename=f'{condition}-{cell["candidate"]}-{row["id"].replace(":","-")}.local.json'
            saved=read(source/filename);messages=item['conditions'][condition]
            if saved['messages']!=messages or saved['situation']!=row:raise ValueError('Source inputs changed')
            dims=applicable(row);has_library_facts=condition not in ('user_only','neutral')
            if row['id'].startswith('summary:') and not has_library_facts:
                dims=[d for d in dims if d!='memory']
                rule='Fictional-library user request remains but assistant rules/explanation are absent. Judge appropriate two-sentence response; do not require removed exact facts or credit coincidental rules as recall.'
            elif row['id'].startswith('summary:'):
                rule='Summarize provided explanation in at most two sentences, retaining hours,three books,two weeks,library card and requested register.'
            else:
                rule='Use actual user facts as truth; first-person user cat ownership belongs to user, not model. Do not let conflicting assistant statements override source facts. Judge current request separately from repeating past topic.'
            req=tag_requirements(row,messages)
            req.pop('missing_context') # These probes preserve user facts; unavailable-library cases handled above.
            req['owner_resolution']='owner_resolution' if req['owner_confusion']=='yes_no' else 'not_applicable'
            entry['answers'][label]={'history':messages[1:-1],'applicable_dimensions':dims,'context_rule':rule,
              'tag_requirements':req,'view':review_view(saved['response'])}
            key['consumer'][ident][label]={'contract_valid':saved['response']['json_valid'],'eos_reached':saved['response']['eos_reached']}
            hashes[filename]=digest(source/filename)
        entry['display_groups']=visible_groups(entry['answers']);packet['situations'].append(entry)
    output.mkdir(parents=True,exist_ok=False);write_json(output/'packet.local.json',packet);write_json(output/'key.local.json',key)
    write_json(output/'provenance.local.json',{'summary_sha256':digest(source/'summary.local.json'),
      'packet_sha256':digest(output/'packet.local.json'),'key_sha256':digest(output/'key.local.json'),'source_responses':hashes})
    print('Packet situations',len(packet['situations']),'logical1012, distinct full visible groups',sum(len(r['display_groups']) for r in packet['situations']),flush=True)


def aggregate(folder):
    folder=artifact_output(folder);proof=read(folder/'provenance.local.json')
    for name in ('packet','key'):
        if digest(folder/f'{name}.local.json')!=proof[name+'_sha256']:raise ValueError('Packet/key changed')
    packet,verdicts=read(folder/'packet.local.json'),read(folder/'verdicts.local.json')
    if packet['review_id']!=verdicts['review_id'] or verdicts['reviewer_kind']!='gpt_session':raise ValueError('Review identity mismatch')
    validate(packet,verdicts['judgments'],verdicts['tags']);key=read(folder/'key.local.json')
    cells={};items={}
    subsets=('history22','user_fact20','eligible12','owner_edit_recall4','exact1','exact2','exact3','exact4')
    def stats():return {'cases':0,'strict_pass':0,'common_three_pass':0,'owner_resolution':Counter(),'owner_confusion':Counter(),'off_topic_carryover':Counter()}
    for c in key['candidates'].values():
        cells[f'{c["condition"]}:{c["candidate"]}']={**stats(),'app_usable_strict_pass':0,'unassessable_cases':0,
          'dimensions':{d:Counter({v:0 for v in VALUES}) for d in DIMENSIONS},'subsets':{name:stats() for name in subsets}}
    for row in packet['situations']:
        ident=row['id'];items[ident]={};membership=key['subsets'][ident]
        for label,answer in row['answers'].items():
            c=key['candidates'][label];name=f'{c["condition"]}:{c["candidate"]}';s=cells[name]
            v,t=verdicts['judgments'][ident][label],verdicts['tags'][ident][label]
            strict=all(v[d]=='pass' for d in answer['applicable_dimensions']);common=all(v[d]=='pass' for d in ('register','relevance','naturalness'))
            targets=[s]+[s['subsets'][a] for a in subsets if (membership.get(a,False) or a==f'exact{membership["exact_errors"]}')]
            for target in targets:
                target['cases']+=1;target['strict_pass']+=strict;target['common_three_pass']+=common
                for tag in ('owner_resolution','owner_confusion','off_topic_carryover'):target[tag][t[tag]]+=1
            consumer=key['consumer'][ident][label];s['app_usable_strict_pass']+=strict and consumer['contract_valid'] and consumer['eos_reached']
            s['unassessable_cases']+=any(v[d]=='unassessable' for d in answer['applicable_dimensions'])
            for d,value in v.items():s['dimensions'][d][value]+=1
            items[ident][name]={'strict':strict,'common':common}
    conditions=list(dict.fromkeys(c['condition'] for c in key['candidates'].values()));paired={}
    for candidate in ('base','adapter'):
        for condition in conditions:
            if condition=='preserved':continue
            for subset in ('user_fact20','eligible12','exact2'):
                count=Counter()
                for ident,pair in items.items():
                    member=key['subsets'][ident]
                    if not (member.get(subset,False) or subset==f'exact{member["exact_errors"]}'):continue
                    a,b=pair[f'preserved:{candidate}'],pair[f'{condition}:{candidate}']
                    for endpoint in ('strict','common'):count[f'{endpoint}:{"pass" if a[endpoint] else "nonpass"}->{"pass" if b[endpoint] else "nonpass"}']+=1
                paired[f'{condition}:{candidate}:{subset}']=dict(count)
    role_pairs={};adjacent={}
    def transitions_for(candidate,before,after,predicate):
        count=Counter();n=0
        for ident,pair in items.items():
            if not predicate(key['subsets'][ident]):continue
            n+=1;a,b=pair[f'{before}:{candidate}'],pair[f'{after}:{candidate}']
            for endpoint in ('strict','common'):count[f'{endpoint}:{"pass" if a[endpoint] else "nonpass"}->{"pass" if b[endpoint] else "nonpass"}']+=1
        return {'cases':n,'transitions':dict(count)}
    for candidate in ('base','adapter'):
        role_pairs[candidate]=transitions_for(candidate,'user_only','neutral',lambda v:v['user_fact20'])
        for direction in ('newest','oldest'):
            for step in range(1,5):
                before='preserved' if step==1 else f'{direction}{step-1}'
                adjacent[f'{direction}{step}:{candidate}']=transitions_for(candidate,before,f'{direction}{step}',lambda v:v['exact_errors']>=step)
    result={'review_id':packet['review_id'],'reviewer_kind':'gpt_session','human_review':False,'gpt_review_completed':True,
      'situations':46,'logical_judgments':1012,'distinct_full_visible_groups':sum(len(r['display_groups']) for r in packet['situations']),
      'cells':cells,'paired_transitions':paired,'neutral_vs_user_only_paired20':role_pairs,'actual_additional_edit_transitions':adjacent,
      'same_full_context_answer_consistency_checked':True,
      'owner_omission_not_counted_as_correct':True,'exact_available_error_cohorts_separated':True,
      'source_summary_sha256':proof['summary_sha256'],'packet_sha256':proof['packet_sha256'],'key_commitment_sha256':proof['key_sha256'],
      'verdicts_sha256':digest(folder/'verdicts.local.json'),'limitations':read(ROOT/'training/configs/role-contradiction-plan.json')['limits'],
      'training_executed':False,'model_promotion_approved':False,'raw_responses_included':False}
    write_json(folder/'aggregate.local.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','aggregate'));p.add_argument('--source',required=True);p.add_argument('--output')
    args=p.parse_args()
    if args.command=='prepare':prepare(args.source,args.output)
    else:print(json.dumps(aggregate(args.source),ensure_ascii=False))


if __name__=='__main__':main()
