"""User-only versus one possessive edit, on preserved local conversation inputs."""
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


def conditions_for(item,plan):
    original=copy.deepcopy(item['conditions']['preserved'])
    row=item['situation']
    if original[0]['role']!='system' or original[-1]!={'role':'user','content':row['input']}:
        raise ValueError('Frozen system/current question required')
    user_only=[m for m in copy.deepcopy(original) if m['role']!='assistant']
    edited=copy.deepcopy(original);patch=None
    for index in range(len(original)-2,0,-1):
        message=original[index]
        if message['role']!='assistant':continue
        text=message['content']
        # Input intervention only, never output scoring. Exact reviewed source
        # shape excludes ambiguous quotes or rewriting an entire response.
        end=next((i+1 for i,c in enumerate(text) if c in '.!?'),len(text))
        sentence=text[:end]
        matches=list(re.finditer(r'(?<!\S)내(?= 고양이(?:네|예요)\.)',sentence))
        if not matches:continue
        if len(matches)!=1:raise ValueError('Ambiguous owner clause; do not auto-repair')
        span=matches[0].span();replacement=plan['owner_replacement'][row['register']]
        edited[index]['content']=text[:span[0]]+replacement+text[span[1]:]
        patch={'message_index':index,'span':list(span),'replacement':replacement,
               'sentence_end_before':end,'later_assistant_turns':sum(m['role']=='assistant' for m in original[index+1:-1])}
        break
    if [m for m in edited if m['role']!='assistant']!=user_only:
        raise ValueError('Single owner edit changed user/system content')
    return {'preserved':original,'user_only':user_only,'owner_sentence':edited},patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();cfg=read_config(args.config)
    source,output=artifact_output(args.source),artifact_output(args.output)
    if output.exists():raise FileExistsError('Choose a fresh artifact directory')
    prior=read(source/'summary.local.json');payload=read(source/'inputs.local.json')
    if not prior['completed'] or len(payload)!=46 or sha256(source/'inputs.local.json')!=prior['inputs_sha256']:
        raise ValueError('Completed immutable 46-situation source required')
    plan_path=ROOT/'training/configs/source-history-plan.json';plan=read(plan_path)
    inputs=[]
    for item in payload:
        conditions,patch=conditions_for(item,plan)
        inputs.append({'situation':item['situation'],'conditions':conditions,'owner_patch':patch})
    adapter=ROOT/cfg['output_dir']/'adapter';receipt=read(adapter.parent/'result.json')
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors')!=receipt['adapter_sha256']:
        raise ValueError('Preserved adapter changed')
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    from transformers import AutoTokenizer
    from peft import PeftModel
    tokenizer=AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    _,generation=suite();all_ids=[];audit=[]
    for item in inputs:
        ids={c:encode_ids(tokenizer,m) for c,m in item['conditions'].items()};all_ids.append(ids)
        if any(len(v)+generation['max_new_tokens']>generation['context_tokens'] for v in ids.values()):
            raise ValueError('No input truncation allowed')
        audit.append({'situation_id':item['situation']['id'],'had_history':len(item['conditions']['preserved'])>2,
          'is_library':item['situation']['id'].startswith('summary:'),'owner_edited':item['owner_patch'] is not None,
          'later_assistant_turns':item['owner_patch']['later_assistant_turns'] if item['owner_patch'] else None,
          'tokens':{c:len(v) for c,v in ids.items()},'token_hashes':{c:token_hash(v) for c,v in ids.items()},
          'user_only_identical':ids['user_only']==ids['preserved'],'owner_sentence_identical':ids['owner_sentence']==ids['preserved']})
    if sum(a['had_history'] for a in audit)!=22 or sum(a['owner_edited'] for a in audit)!=12:
        raise ValueError('Unexpected intervention coverage; review inputs before generation')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'inputs.local.json',inputs);write_json(output/'token-audit.local.json',audit)
    setup_seed(generation['seed'])
    summary={'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),'conditions':plan['conditions'],
      'generation':generation,'results':[],'load_metadata':[],'actual_generate_calls':0,'equivalent_reuses':0,
      'plan_sha256':sha256(plan_path),'inputs_sha256':sha256(output/'inputs.local.json'),
      'source_summary_sha256':sha256(source/'summary.local.json'),'base_sha256':cfg['checkpoint_sha256'],
      'adapter_sha256':receipt['adapter_sha256'],'training_executed':False,'android_changed':False}
    try:
        for candidate in ('base','adapter'):
            model=load_base(cfg)
            if candidate=='adapter':model=PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            model.requires_grad_(False);model.eval()
            if not all(p.device.type=='cuda' for p in model.parameters()):raise RuntimeError('No CPU/disk offload allowed')
            summary['load_metadata'].append({'candidate':candidate,'all_cuda':True,'all_frozen':all(not p.requires_grad for p in model.parameters()),
                'dtypes':dict(Counter(str(p.dtype) for p in model.parameters()))})
            for index,item in enumerate(inputs):
                responses={}
                for condition in plan['conditions']:
                    alias=next((c for c in responses if all_ids[index][c]==all_ids[index][condition]),None)
                    if alias:response=responses[alias];summary['equivalent_reuses']+=1
                    else:
                        response=response_diagnostic(infer(model,tokenizer,item['conditions'][condition],generation['seed'],generation['max_new_tokens'],contract_mode='constrained'))
                        summary['actual_generate_calls']+=1
                    responses[condition]=response
                    filename=f'{condition}-{candidate}-{item["situation"]["id"].replace(":","-")}.local.json'
                    write_json(output/filename,{'situation':item['situation'],'messages':item['conditions'][condition],
                      'response':response,'condition':condition,'candidate':candidate,'equivalent_input_reused':bool(alias),'alias_condition':alias})
                    summary['results'].append({'condition':condition,'candidate':candidate,'situation_id':item['situation']['id'],
                      'input_ids_sha256':token_hash(all_ids[index][condition]),'equivalent_input_reused':bool(alias),
                      **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}})
                    print(f'{len(summary["results"])}/276 actual={summary["actual_generate_calls"]} {candidate} {condition} {item["situation"]["id"]} valid={response["json_valid"]} alias={alias}',flush=True)
            del model;clear_cuda()
        summary['completed']=len(summary['results'])==276
    except Exception as error:
        summary['error_type']=type(error).__name__;raise
    finally:
        summary['finished_at']=datetime.now(timezone.utc).isoformat();write_json(output/'summary.local.json',summary)


if __name__=='__main__':main()
