"""Inference-only 2x2 prompt/model comparison; preserve weights and prior results."""
import argparse
from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path

from data_contract import ROOT
from llm_runtime import (artifact_output, clear_cuda, infer, load_base, read_config,
                         setup_seed, sha256, tokenizer_and_template, write_json)
from prompt_suite import messages_for, read_plan, suite, trim_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--grammar-deps', type=Path, default=ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114')
    args = parser.parse_args()
    if not args.grammar_deps.is_dir():
        parser.error('Use the existing isolated grammar dependency directory')
    sys.path.insert(0, str(args.grammar_deps.resolve()))
    cfg = read_config(args.config)
    situations, generation = suite()
    plan = read_plan()
    output = artifact_output(args.output)
    if output.exists():
        raise FileExistsError('Use a new comparison directory')
    adapter = artifact_output(cfg['output_dir'])/'adapter'
    training_receipt = json.loads((adapter.parent/'result.json').read_text(encoding='utf-8'))
    adapter_hash = sha256(adapter/'adapter_model.safetensors')
    if not training_receipt['completed'] or adapter_hash != training_receipt['adapter_sha256']:
        raise ValueError('Preserved trained adapter does not match its receipt')
    setup_seed(generation['seed'])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'situations.local.json', situations)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'completed': False,
              'expected_results': len(situations)*2*len(plan['variants']), 'results': [],
              'generation': generation, 'contract_mode': 'constrained',
              'plan_lf_sha256': sha256(ROOT/'training/configs/prompt-comparison-plan.json'),
              'base_sha256': cfg['checkpoint_sha256'], 'adapter_sha256': adapter_hash,
              'training_executed': False, 'android_changed': False, 'human_review_completed': False,
              'gpt_review_completed': False, 'deployment_approved': False}
    try:
        from peft import PeftModel
        tokenizer, _ = tokenizer_and_template(cfg)
        for candidate in ('base','adapter'):
            model = load_base(cfg)
            if candidate == 'adapter':
                model = PeftModel.from_pretrained(model, adapter, is_trainable=False, local_files_only=True)
            for variant in plan['variants']:
                history = []
                for row in situations:
                    if row['reset']:
                        history = [tuple(pair) for pair in row['initial_history']]
                    messages = messages_for(row, variant, history)
                    started = time.perf_counter()
                    response = infer(model, tokenizer, messages, generation['seed'], generation['max_new_tokens'],
                                     contract_mode='constrained')
                    result = {'situation_id': row['id'], 'candidate': candidate, 'variant': variant,
                              'elapsed_seconds': time.perf_counter()-started,
                              **{k:v for k,v in response.items() if k not in ('raw','reply')}}
                    filename = f'{variant}-{candidate}-{row["id"].replace(":","-")}.local.json'
                    write_json(output/filename, {'situation': row, 'messages': messages, 'response': response})
                    report['results'].append(result)
                    if row['sequence'] and response['json_valid']:
                        history = trim_history(history+[(row['input'], response['reply']['spoken_text'])])
                    print(json.dumps({'n':len(report['results']), 'total':report['expected_results'],
                                      'situation':row['id'], 'candidate':candidate, 'variant':variant,
                                      'valid':response['json_valid'], 'tokens':response['tokens']}, ensure_ascii=False), flush=True)
            del model
            clear_cuda()
        report['completed'] = len(report['results']) == report['expected_results']
    except Exception as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output/'summary.local.json', report)


if __name__ == '__main__':
    main()
