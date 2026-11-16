"""Frozen history intervention on unchanged local model/adapter; no training."""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
import sys

from data_contract import ROOT
from llm_runtime import (artifact_output,clear_cuda,contract_messages,infer,load_base,
                         read_config,setup_seed,sha256,write_json)
from compare_text_paths import response_diagnostic
from prompt_suite import suite
from runtime_ablation import token_hash


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def history_conditions(item,plan,questions):
    original = copy.deepcopy(item['messages'])
    if original[0]['role']!='system' or original[-1] != {'role':'user','content':item['situation']['input']}:
        raise ValueError('Expected frozen system/current question')
    fixed = copy.deepcopy(original)
    register = item['situation']['register']
    inverse = {v:k for k,v in questions.items()}
    for index in range(1,len(original)-1,2):
        user,answer = original[index:index+2]
        if user['role']!='user' or answer['role']!='assistant':
            raise ValueError('Expected complete historical turn pairs')
        if user['content']==plan['library_history']['user']:
            text = plan['library_history'][register]
        else:
            case = inverse.get(user['content'])
            if case not in plan['canonical_assistant']:
                raise ValueError('No reviewed canonical history reply for past user turn')
            if item['situation']['mode']=='follow_user' and case in ('conv41','conv42'):
                register = 'polite' if case=='conv41' else 'casual'
            text = plan['canonical_assistant'][case][register]
        fixed[index+1]['content'] = text
    if [m for m in fixed if m['role']!='assistant'] != [m for m in original if m['role']!='assistant']:
        raise ValueError('Repair must not change system or user turns')
    return {'preserved':original,'repaired':fixed,'no_history':[copy.deepcopy(original[0]),copy.deepcopy(original[-1])]}


def encode_ids(tokenizer,messages):
    return tokenizer.apply_chat_template(contract_messages(messages,'schema'),tokenize=True,
        add_generation_prompt=True,enable_thinking=False,return_dict=True)['input_ids']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    cfg = read_config(args.config)
    source,output = artifact_output(args.source),artifact_output(args.output)
    if output.exists():raise FileExistsError('Preserve earlier results; select a new output directory')
    previous = read(source/'summary.local.json')
    payload = read(source/'inputs.local.json')
    if not previous['completed'] or len(payload)!=46 or sha256(source/'inputs.local.json')!=previous['inputs_sha256']:
        raise ValueError('Frozen 46-situation source required')
    plan_path = ROOT/'training/configs/history-comparison-plan.json'
    plan = read(plan_path)
    situations,generation = suite()
    questions = {s['case_id']:s['input'] for s in situations}
    inputs = [{'situation':item['situation'],'conditions':history_conditions(item,plan,questions)} for item in payload]
    adapter = ROOT/cfg['output_dir']/'adapter'
    receipt = read(adapter.parent/'result.json')
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors')!=receipt['adapter_sha256']:
        raise ValueError('Preserved adapter changed')
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    from transformers import AutoTokenizer
    from peft import PeftModel
    tokenizer = AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    token_audit,all_token_ids = [],[]
    for item in inputs:
        tokenized = {c:encode_ids(tokenizer,m) for c,m in item['conditions'].items()}
        all_token_ids.append(tokenized)
        for ids in tokenized.values():
            if len(ids)+generation['max_new_tokens']>generation['context_tokens']:
                raise ValueError('Do not truncate intervention histories')
        token_audit.append({'situation_id':item['situation']['id'],
          'has_preserved_history':len(item['conditions']['preserved'])>2,
          'tokens':{c:len(ids) for c,ids in tokenized.items()},
          'token_hashes':{c:token_hash(ids) for c,ids in tokenized.items()},
          'repaired_equals_preserved':tokenized['repaired']==tokenized['preserved'],
          'no_history_equals_preserved':tokenized['no_history']==tokenized['preserved']})
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'inputs.local.json',inputs)
    write_json(output/'token-audit.local.json',token_audit)
    setup_seed(generation['seed'])
    summary = {'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),
      'conditions':plan['conditions'],'generation':generation,'results':[],'load_metadata':[],
      'expected_logical_results':276,'actual_generate_calls':0,'equivalent_reuses':0,
      'base_sha256':cfg['checkpoint_sha256'],'adapter_sha256':receipt['adapter_sha256'],
      'plan_sha256':sha256(plan_path),'inputs_sha256':sha256(output/'inputs.local.json'),
      'source_summary_sha256':sha256(source/'summary.local.json'),
      'training_executed':False,'android_changed':False}
    try:
        for candidate in ('base','adapter'):
            model = load_base(cfg)
            if candidate=='adapter':model = PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            model.requires_grad_(False);model.eval()
            if not all(p.device.type=='cuda' for p in model.parameters()):raise RuntimeError('No offload allowed')
            summary['load_metadata'].append({'candidate':candidate,'all_cuda':True,
              'all_frozen':all(not p.requires_grad for p in model.parameters()),
              'dtypes':dict(Counter(str(p.dtype) for p in model.parameters()))})
            for index,item in enumerate(inputs):
                responses = {}
                for condition in plan['conditions']:
                    messages = item['conditions'][condition]
                    signature = token_audit[index]['token_hashes'][condition]
                    # Exact token equivalence only within this situation/model.
                    alias = next((c for c in responses if all_token_ids[index][c]==all_token_ids[index][condition]),None)
                    if alias:
                        response = responses[alias]
                        summary['equivalent_reuses'] += 1
                    else:
                        response = response_diagnostic(infer(model,tokenizer,messages,generation['seed'],
                            generation['max_new_tokens'],contract_mode='constrained'))
                        summary['actual_generate_calls'] += 1
                    responses[condition] = response
                    name = f'{condition}-{candidate}-{item["situation"]["id"].replace(":","-")}.local.json'
                    write_json(output/name,{'situation':item['situation'],'messages':messages,'response':response,
                      'condition':condition,'candidate':candidate,'equivalent_input_reused':bool(alias),'alias_condition':alias})
                    summary['results'].append({'condition':condition,'candidate':candidate,'situation_id':item['situation']['id'],
                      'input_ids_sha256':signature,'has_preserved_history':token_audit[index]['has_preserved_history'],
                      'equivalent_input_reused':bool(alias),
                      **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}})
                    print(json.dumps({'n':len(summary['results']),'total':276,'actual_calls':summary['actual_generate_calls'],
                      'candidate':candidate,'condition':condition,'situation':item['situation']['id'],
                      'valid':response['json_valid'],'alias':alias}),flush=True)
            del model
            clear_cuda()
        summary['completed'] = len(summary['results'])==276
    except Exception as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output/'summary.local.json',summary)


if __name__=='__main__':main()
