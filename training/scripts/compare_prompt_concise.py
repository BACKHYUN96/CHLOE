"""Bounded adaptive inference-only followup on the same frozen quality situations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from data_contract import ROOT
from llm_runtime import (artifact_output,clear_cuda,infer,load_base,read_config,
                         setup_seed,sha256,tokenizer_and_template,write_json)
from prompt_suite import concise_prompt,suite,trim_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    cfg = read_config(args.config)
    all_situations,generation = suite()
    situations = [s for s in all_situations if s['quality_review']]
    output = artifact_output(args.output)
    if output.exists():
        raise FileExistsError('Choose a new followup directory')
    adapter = artifact_output(cfg['output_dir'])/'adapter'
    receipt = json.loads((adapter.parent/'result.json').read_text(encoding='utf-8'))
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors') != receipt['adapter_sha256']:
        raise ValueError('Preserved adapter receipt mismatch')
    setup_seed(generation['seed'])
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'situations.local.json',situations)
    summary = {'phase':'concise','completed':False,'expected_results':92,'results':[],
               'started_at':datetime.now(timezone.utc).isoformat(),'generation':generation,
               'contract_mode':'constrained','training_executed':False,'android_changed':False,
               'base_sha256':cfg['checkpoint_sha256'],'adapter_sha256':receipt['adapter_sha256'],
               'plan_lf_sha256':sha256(ROOT/'training/configs/prompt-comparison-concise.json'),
               'base_plan_sha256':sha256(ROOT/'training/configs/prompt-comparison-plan.json')}
    try:
        from peft import PeftModel
        tokenizer,_ = tokenizer_and_template(cfg)
        for candidate in ('base','adapter'):
            model = load_base(cfg)
            if candidate == 'adapter':
                model = PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            history = []
            for row in situations:
                if row['reset']:
                    history = [tuple(pair) for pair in row['initial_history']]
                messages = [{'role':'system','content':concise_prompt(row['register'],row['mode'])}]
                for user,answer in history:
                    messages.extend([{'role':'user','content':user},{'role':'assistant','content':answer}])
                messages.append({'role':'user','content':row['input']})
                started = time.perf_counter()
                response = infer(model,tokenizer,messages,generation['seed'],generation['max_new_tokens'],contract_mode='constrained')
                summary['results'].append({'situation_id':row['id'],'variant':'concise','candidate':candidate,
                    'elapsed_seconds':time.perf_counter()-started,
                    **{k:v for k,v in response.items() if k not in ('raw','reply')}})
                name = f'concise-{candidate}-{row["id"].replace(":","-")}.local.json'
                write_json(output/name,{'situation':row,'messages':messages,'response':response})
                if row['sequence'] and response['json_valid']:
                    history = trim_history(history+[(row['input'],response['reply']['spoken_text'])])
                print(json.dumps({'n':len(summary['results']),'total':92,'candidate':candidate,
                                  'situation':row['id'],'valid':response['json_valid']},ensure_ascii=False),flush=True)
            del model
            clear_cuda()
        summary['completed'] = len(summary['results']) == 92
    except Exception as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output/'summary.local.json',summary)


if __name__ == '__main__':
    main()
