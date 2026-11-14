"""Neutral role-preserving history and cumulative owner contradiction interventions."""
import argparse
from collections import Counter
import copy
from datetime import datetime,timezone
import re
import sys

from data_contract import ROOT
from llm_runtime import artifact_output,clear_cuda,infer,load_base,read_config,setup_seed,sha256,write_json
from compare_histories import encode_ids,read
from compare_text_paths import response_diagnostic
from prompt_suite import suite
from runtime_ablation import token_hash


def eligible_owner_edits(messages,register,plan):
    edits=[]
    for index,message in enumerate(messages[1:-1],1):
        if message['role']!='assistant':continue
        text=message['content'];end=next((i+1 for i,c in enumerate(text) if c in '.!?'),len(text))
        found=list(re.finditer(r'(?<!\S)내(?= 고양이(?:네|예요)\.)',text[:end]))
        if not found:continue
        if len(found)!=1:raise ValueError('Ambiguous source ownership sentence')
        edits.append({'message_index':index,'span':list(found[0].span()),'replacement':plan['owner_replacement'][register]})
    if len(edits)>4:raise ValueError('Unreviewed source with more than four owner errors')
    return edits


def conditions_for(item,plan):
    original=copy.deepcopy(item['conditions']['preserved']);row=item['situation']
    if original[0]['role']!='system' or original[-1]!={'role':'user','content':row['input']}:
        raise ValueError('Frozen system/current question required')
    edits=eligible_owner_edits(original,row['register'],plan)
    cells={'preserved':original,'user_only':[m for m in copy.deepcopy(original) if m['role']!='assistant'],
           'neutral':copy.deepcopy(original)}
    for message in cells['neutral'][1:-1]:
        if message['role']=='assistant':message['content']=plan['neutral_text']
    metadata={c:{'applied_edits':0,'remaining_owner_errors':len(edits) if c=='preserved' else 0,
                 'edited_message_indices':[]} for c in cells}
    for step in range(1,5):
        for direction in ('newest','oldest'):
            name=f'{direction}{step}';ordered=list(reversed(edits)) if direction=='newest' else edits
            selected=ordered[:step];value=copy.deepcopy(original)
            for edit in selected:
                index=edit['message_index'];start,end=edit['span'];text=original[index]['content']
                value[index]['content']=text[:start]+edit['replacement']+text[end:]
            cells[name]=value;metadata[name]={'requested_edits':step,'applied_edits':len(selected),
              'remaining_owner_errors':len(edits)-len(selected),'edited_message_indices':[e['message_index'] for e in selected]}
    users=[m for m in original if m['role']!='assistant']
    for value in cells.values():
        if [m for m in value if m['role']!='assistant']!=users:raise ValueError('User facts/order/system changed')
    return cells,edits,metadata


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();cfg=read_config(args.config);source,output=artifact_output(args.source),artifact_output(args.output)
    if output.exists():raise FileExistsError('Choose a new artifact directory')
    previous=read(source/'summary.local.json');payload=read(source/'inputs.local.json')
    if not previous['completed'] or len(payload)!=46 or sha256(source/'inputs.local.json')!=previous['inputs_sha256']:
        raise ValueError('Completed immutable source required')
    plan_path=ROOT/'training/configs/role-contradiction-plan.json';plan=read(plan_path);inputs=[]
    for item in payload:
        cells,edits,metadata=conditions_for(item,plan)
        if cells['newest1']!=item['conditions']['owner_sentence'] or cells['user_only']!=item['conditions']['user_only']:
            raise ValueError('One-edit/user-only reference differs from preserved prior experiment')
        inputs.append({'situation':item['situation'],'conditions':cells,'eligible_edits':edits,'edit_metadata':metadata})
    adapter=ROOT/cfg['output_dir']/'adapter';receipt=read(adapter.parent/'result.json')
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors')!=receipt['adapter_sha256']:
        raise ValueError('Adapter changed')
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    from transformers import AutoTokenizer
    from peft import PeftModel
    tokenizer=AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    _,generation=suite();all_ids=[];audit=[]
    for item in inputs:
        ids={c:encode_ids(tokenizer,m) for c,m in item['conditions'].items()};all_ids.append(ids)
        if any(len(v)+generation['max_new_tokens']>generation['context_tokens'] for v in ids.values()):raise ValueError('No truncation allowed')
        audit.append({'situation_id':item['situation']['id'],'had_history':len(item['conditions']['preserved'])>2,
          'eligible_owner_errors':len(item['eligible_edits']),'is_library':item['situation']['id'].startswith('summary:'),
          'condition_metadata':item['edit_metadata'],'tokens':{c:len(v) for c,v in ids.items()},
          'token_hashes':{c:token_hash(v) for c,v in ids.items()},'unique_conditioned_inputs':len({tuple(v) for v in ids.values()})})
    if sum(a['had_history'] for a in audit)!=22 or sum(a['eligible_owner_errors']>0 for a in audit)!=12:
        raise ValueError('Unexpected intervention coverage')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'inputs.local.json',inputs);write_json(output/'token-audit.local.json',audit)
    setup_seed(generation['seed'])
    summary={'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),'conditions':plan['conditions'],
      'generation':generation,'results':[],'load_metadata':[],'actual_generate_calls':0,'equivalent_reuses':0,
      'plan_sha256':sha256(plan_path),'inputs_sha256':sha256(output/'inputs.local.json'),'source_summary_sha256':sha256(source/'summary.local.json'),
      'base_sha256':cfg['checkpoint_sha256'],'adapter_sha256':receipt['adapter_sha256'],'training_executed':False,'android_changed':False}
    try:
        for candidate in ('base','adapter'):
            model=load_base(cfg)
            if candidate=='adapter':model=PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            model.requires_grad_(False);model.eval()
            if not all(p.device.type=='cuda' for p in model.parameters()):raise RuntimeError('No CPU/disk offload')
            summary['load_metadata'].append({'candidate':candidate,'all_cuda':True,'all_frozen':all(not p.requires_grad for p in model.parameters()),
              'dtypes':dict(Counter(str(p.dtype) for p in model.parameters()))})
            for i,item in enumerate(inputs):
                responses={}
                for condition in plan['conditions']:
                    alias=next((c for c in responses if all_ids[i][c]==all_ids[i][condition]),None)
                    if alias:response=responses[alias];summary['equivalent_reuses']+=1
                    else:
                        response=response_diagnostic(infer(model,tokenizer,item['conditions'][condition],generation['seed'],generation['max_new_tokens'],contract_mode='constrained'))
                        summary['actual_generate_calls']+=1
                    responses[condition]=response;name=f'{condition}-{candidate}-{item["situation"]["id"].replace(":","-")}.local.json'
                    write_json(output/name,{'situation':item['situation'],'messages':item['conditions'][condition],
                      'response':response,'condition':condition,'candidate':candidate,'equivalent_input_reused':bool(alias),'alias_condition':alias})
                    summary['results'].append({'condition':condition,'candidate':candidate,'situation_id':item['situation']['id'],
                      'input_ids_sha256':token_hash(all_ids[i][condition]),'equivalent_input_reused':bool(alias),
                      **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}})
                    print(f'{len(summary["results"])}/1012 actual={summary["actual_generate_calls"]} {candidate} {condition} {item["situation"]["id"]} valid={response["json_valid"]} alias={alias}',flush=True)
            del model;clear_cuda()
        summary['completed']=len(summary['results'])==1012
    except Exception as error:
        summary['error_type']=type(error).__name__;raise
    finally:
        summary['finished_at']=datetime.now(timezone.utc).isoformat();write_json(output/'summary.local.json',summary)


if __name__=='__main__':main()
