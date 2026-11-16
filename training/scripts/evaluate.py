"""Compare frozen inputs under identical generation settings; human scores stay null."""
import argparse
import json
import random
import sys
from pathlib import Path

from data_contract import ROOT, persona
from llm_runtime import (artifact_output, clear_cuda, infer, load_base, local_path,
                         read_config, setup_seed, sha256, tokenizer_and_template, write_json)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--compare-base',action='store_true')
    parser.add_argument('--limit',type=int,help='Partial execution only; never report full-suite completion')
    parser.add_argument('--register',choices=['casual','polite','both'],default='both')
    parser.add_argument('--contract-mode',choices=['legacy','schema','constrained'],default='constrained',
                        help='schema binds actual app keys/enums; legacy reproduces the old omission')
    parser.add_argument('--grammar-deps',type=Path,default=ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114')
    parser.add_argument('--include-heldout',action='store_true',help='Also retest the previously failing approved test prompt')
    parser.add_argument('--case-ids',nargs='+',help='Select existing frozen case IDs for focused regression')
    parser.add_argument('--output',help='Fresh artifact directory; default output_dir-evaluation')
    args = parser.parse_args()
    cfg = read_config(args.config)
    if args.contract_mode=='constrained':
        if not args.grammar_deps.is_dir():
            parser.error('Install training/requirements.contract.txt into the separate --grammar-deps folder first')
        sys.path.insert(0,str(args.grammar_deps.resolve()))
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    setup_seed(cfg['seed'])
    plan = json.loads((ROOT/'training/configs/evaluation-plan.json').read_text(encoding='utf-8'))
    for path, expected in plan['sources'].items():
        from hashlib import sha256 as hash_bytes
        if hash_bytes((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != expected['lf_normalized_sha256']:
            raise ValueError('Frozen evaluation/persona source changed')
    original = json.loads((ROOT/'app/src/main/assets/conversation-cases.json').read_text(encoding='utf-8'))['cases']
    cases = original + [dict(row,group=row['category']) for row in plan['supplemental_cases']]
    if args.include_heldout:
        from data_contract import load_records
        cases += [{'id':'heldout-'+row['id'],'group':'heldout','input':row['messages'][1]['content']}
                  for row in load_records(local_path(cfg['data'])) if row['split']=='test']
    if args.case_ids and not set(args.case_ids)<={row['id'] for row in cases}:
        parser.error('Unknown case ID')
    selected=[row for row in cases if not args.case_ids or row['id'] in args.case_ids]
    selected=selected[:args.limit] if args.limit else selected
    registers = ['casual','polite'] if args.register=='both' else [args.register]
    out = artifact_output(args.output or cfg['output_dir']+'-evaluation')
    out.mkdir(parents=True,exist_ok=False)
    adapter = artifact_output(cfg['output_dir'])/'adapter'
    training_result = json.loads((adapter.parent/'result.json').read_text(encoding='utf-8'))
    if not training_result['completed'] or sha256(adapter/'adapter_model.safetensors') != training_result['adapter_sha256']:
        raise ValueError('Completed training receipt and matching adapter required')
    tokenizer, _ = tokenizer_and_template(cfg)
    candidates = ['base','adapter'] if args.compare_base else ['adapter']
    mapping = candidates.copy()
    random.Random(cfg['seed']).shuffle(mapping)
    labels = {name:chr(ord('A')+index) for index,name in enumerate(mapping)}
    write_json(out/'blind-mapping.local.json',labels)
    summary = {'completed':False,'full_suite_completed':False,'case_count':len(selected),
        'registers':registers,'candidates':candidates,'generation':plan['generation'],
        'human_scores':plan['human_dimensions'],'human_review_completed':False,
        'quality_improvement_verified':False,'contract_mode':args.contract_mode,
        'adapter_sha256':training_result['adapter_sha256'],
        'schema_sha256':sha256(ROOT/'app/src/main/assets/conversation-schema.json'),
        'expected_case_count':len(cases),'include_heldout':args.include_heldout,'results':[]}
    try:
        from peft import PeftModel
        for candidate in candidates:
            model = load_base(cfg)
            if candidate=='adapter':
                model = PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
            for register in registers:
                history=[]
                for case in selected:
                    if case['group']!='context' or case['id']=='conv41':
                        history=[]
                    messages=[{'role':'system','content':persona(register=='polite')}]
                    for user,answer in history:
                        messages.extend([{'role':'user','content':user},{'role':'assistant','content':answer}])
                    messages.append({'role':'user','content':case['input']})
                    result=infer(model,tokenizer,messages,plan['generation']['seed'],plan['generation']['max_new_tokens'],
                                 contract_mode=args.contract_mode)
                    item={'id':case['id'],'register':register,'candidate':candidate,
                          **{k:v for k,v in result.items() if k not in ('raw','reply')}}
                    summary['results'].append(item)
                    write_json(out/f"{labels[candidate]}-{register}-{case['id']}.local.json",result)
                    if result['json_valid'] and case['group']=='context':
                        history.append((case['input'],result['reply']['spoken_text']))
                        while len(history)>4 or sum(len((u+a).encode('utf-16-le'))//2 for u,a in history)>1200:
                            history.pop(0)
                    print(item,flush=True)
            del model
            clear_cuda()
        summary['completed']=True
        summary['full_suite_completed']=(len(selected)==len(cases) and len(registers)==2 and len(candidates)==2)
    except Exception as error:
        summary['error_type']=type(error).__name__
        raise
    finally:
        write_json(out/'summary.json',summary)


if __name__=='__main__':
    main()
