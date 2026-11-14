"""Name, animal and object transfer of first ownership recall; no training."""
import argparse
from collections import Counter
import copy
from datetime import datetime,timezone
import sys

from data_contract import ROOT
from compare_histories import encode_ids,read
from compare_text_paths import response_diagnostic
from llm_runtime import artifact_output,clear_cuda,infer,load_base,read_config,setup_seed,sha256,write_json
from prompt_suite import suite,system_prompt
from runtime_ablation import token_hash


def build_inputs(plan,references):
    rows=[]
    for fixture in plan['fixtures']:
        fact=lambda owner:fixture['fact'].format(owner=owner)
        forms={'deictic':fact('내'),'explicit_user':fact('사용자의'),
          'named_deictic':fixture['self']+' '+fact('내'),
          'named_explicit':fixture['self']+' '+fact(fixture['person']+'의'),
          'third_quoted':fixture['reporter']+' "'+fact('내')+'"라고 말했어.',
          'third_explicit':fact(fixture['person']+'의')}
        role_forms={'first_person':fact('내'),'second_person':fact('네'),
          'explicit_user':fact('사용자의'),'third_explicit':fact(fixture['person']+'의')}
        for register in plan['registers']:
            system={'role':'system','content':system_prompt('original',register)}
            for form in plan['main_forms']:
                for history in plan['history_formats']:
                    messages=[copy.deepcopy(system),{'role':'user','content':forms[form]}]
                    if history=='neutral':messages.append({'role':'assistant','content':plan['neutral']})
                    messages.append({'role':'user','content':fixture['question']})
                    rows.append({'id':f'user:{fixture["id"]}:{register}:{form}:{history}','block':'user',
                      'fixture_id':fixture['id'],'domain':fixture['domain'],'person':fixture['person'],
                      'register':register,'fact_id':form,'history_format':history,'source_role':'user',
                      'expected_owner':'third_party' if form.startswith('third_') else 'user','messages':messages})
            for form in plan['role_forms']:
                for role in plan['source_roles']:
                    target={'first_person':role,'second_person':'assistant' if role=='user' else 'user',
                            'explicit_user':'user','third_explicit':'third_party'}[form]
                    rows.append({'id':f'role:{fixture["id"]}:{register}:{form}:{role}','block':'role',
                      'fixture_id':fixture['id'],'domain':fixture['domain'],'person':fixture['person'],
                      'register':register,'fact_id':form,'source_role':role,'expected_owner':target,
                      'messages':[copy.deepcopy(system),{'role':'user','content':plan['role_preface']},
                        {'role':role,'content':role_forms[form]},{'role':'user','content':fixture['question']}]})
    previous={r['id']:r for r in references}
    for ident in plan['reference_ids']:
        row=copy.deepcopy(previous[ident]);row['prior_case_id']=ident;row['id']='reference:'+ident
        row.update(block='reference',fixture_id='old_minsu_bori',domain='reference',person='민수')
        rows.append(row)
    if len(rows)!=164 or len({r['id'] for r in rows})!=164:raise ValueError('Expected164 unique cases')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    cfg=read_config(args.config);source,output=artifact_output(args.source),artifact_output(args.output)
    if output.exists():raise FileExistsError('Preserve prior results; choose a new directory')
    prior=read(source/'summary.local.json')
    if not prior['completed'] or sha256(source/'inputs.local.json')!=prior['inputs_sha256']:
        raise ValueError('Completed immutable source required')
    plan_path=ROOT/'training/configs/ownership-transfer-plan.json';plan=read(plan_path)
    inputs=build_inputs(plan,read(source/'inputs.local.json'));_,generation=suite()
    adapter=ROOT/cfg['output_dir']/'adapter';receipt=read(adapter.parent/'result.json')
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors')!=receipt['adapter_sha256']:
        raise ValueError('Preserved adapter changed')
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    from transformers import AutoTokenizer
    from peft import PeftModel
    tokenizer=AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    audit=[]
    for row in inputs:
        ids=encode_ids(tokenizer,row['messages'])
        if len(ids)+generation['max_new_tokens']>generation['context_tokens']:raise ValueError('No truncation')
        audit.append({k:v for k,v in row.items() if k!='messages'}|{'prompt_tokens':len(ids),'input_ids_sha256':token_hash(ids)})
    if len({r['input_ids_sha256'] for r in audit})!=164:raise ValueError('Unexpected duplicate case inputs')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'inputs.local.json',inputs);write_json(output/'token-audit.local.json',audit)
    setup_seed(generation['seed'])
    summary={'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),'generation':generation,
      'plan_sha256':sha256(plan_path),'inputs_sha256':sha256(output/'inputs.local.json'),
      'source_summary_sha256':sha256(source/'summary.local.json'),'base_sha256':cfg['checkpoint_sha256'],
      'adapter_sha256':receipt['adapter_sha256'],'load_metadata':[],'results':[],'actual_generate_calls':0,
      'training_executed':False,'android_changed':False}
    try:
        for candidate in ('base','adapter'):
            model=load_base(cfg)
            if candidate=='adapter':model=PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            model.requires_grad_(False);model.eval()
            if not all(p.device.type=='cuda' for p in model.parameters()):raise RuntimeError('No offload')
            summary['load_metadata'].append({'candidate':candidate,'all_cuda':True,'all_frozen':all(not p.requires_grad for p in model.parameters()),
              'dtypes':dict(Counter(str(p.dtype) for p in model.parameters()))})
            for row in inputs:
                response=response_diagnostic(infer(model,tokenizer,row['messages'],generation['seed'],generation['max_new_tokens'],contract_mode='constrained'))
                summary['actual_generate_calls']+=1;filename=f'{candidate}-{row["id"].replace(":","-")}.local.json'
                write_json(output/filename,{'case':row,'response':response,'candidate':candidate})
                summary['results'].append({'candidate':candidate,'case_id':row['id'],
                  **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}})
                print(f'{summary["actual_generate_calls"]}/328 {candidate} {row["id"]} valid={response["json_valid"]}',flush=True)
            del model;clear_cuda()
        summary['completed']=len(summary['results'])==328
    except Exception as error:
        summary['error_type']=type(error).__name__;raise
    finally:
        summary['finished_at']=datetime.now(timezone.utc).isoformat();write_json(output/'summary.local.json',summary)


if __name__=='__main__':main()
