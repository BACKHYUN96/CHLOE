"""One-factor inference diagnostics on immutable common messages; no training."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from data_contract import ROOT, diagnose_reply, validate_reply
from llm_runtime import (artifact_output, clear_cuda, contract_messages, decoding_schema, load_base,
                         read_config, setup_seed, sha256, stop_token_ids, write_json)
from prompt_suite import suite


def plan():
    return json.loads((ROOT/'training/configs/runtime-ablation-plan.json').read_text(encoding='utf-8'))


def token_hash(ids):
    return hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()


def verify_one_factor(conditions):
    baseline = conditions['baseline']
    for name, settings in conditions.items():
        if set(settings) != {'precision','template','decoder'}:
            raise ValueError('Unknown runtime factor')
        expected = 0 if name == 'baseline' else 1
        if sum(settings[k] != baseline[k] for k in baseline) != expected:
            raise ValueError('Each intervention must change exactly one factor')


def prepare_inputs(source):
    situations, generation = suite()
    chosen = [s for s in situations if s['quality_review']]
    payload = []
    for row in chosen:
        path = source/f'original-base-{row["id"].replace(":","-")}.local.json'
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved['situation'] != row:
            raise ValueError('Frozen source situation mismatch')
        payload.append({'situation':row,'messages':saved['messages'],'source_sha256':sha256(path)})
    return payload, generation


def encoded(tokenizer, messages, template, tensors=False):
    # The conditioned messages are exactly the same for decoder on and off.
    kwargs = {'return_tensors':'pt'} if tensors else {}
    return tokenizer.apply_chat_template(contract_messages(messages,'schema'),chat_template=template,
        tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=True,**kwargs)


def audit(tokenizer, official, training, payload):
    rows = []
    for item in payload:
        first = encoded(tokenizer,item['messages'],official)['input_ids']
        second = encoded(tokenizer,item['messages'],training)['input_ids']
        text = tokenizer.apply_chat_template(contract_messages(item['messages'],'schema'),chat_template=official,
                     tokenize=False,add_generation_prompt=True,enable_thinking=False)
        manual = tokenizer(text,add_special_tokens=False)['input_ids']
        if first != manual:
            raise ValueError('Direct template tokenization differs from no-extra-special-token encoding')
        rows.append({'situation_id':item['situation']['id'],'official_tokens':len(first),
          'training_tokens':len(second),'token_ids_identical':first==second,
          'official_ids_sha256':token_hash(first),'training_ids_sha256':token_hash(second),
          'manual_encoding_identical':True})
    return rows


def load_precision(cfg, precision):
    if precision == 'nf4':
        return load_base(cfg)
    if precision != 'bf16':
        raise ValueError('Unsupported precision')
    import torch
    from transformers import AutoConfig, Qwen3_5ForCausalLM
    base = ROOT/cfg['base_dir']
    if sha256(base/'model.safetensors-00001-of-00001.safetensors') != cfg['checkpoint_sha256']:
        raise ValueError('Original checkpoint hash mismatch')
    config = AutoConfig.from_pretrained(base,local_files_only=True,trust_remote_code=False).text_config
    model,info = Qwen3_5ForCausalLM.from_pretrained(base,config=config,dtype=torch.bfloat16,
      device_map={'':0},attn_implementation='eager',local_files_only=True,trust_remote_code=False,
      key_mapping={r'^model.language_model\.':'model.'},output_loading_info=True)
    if info['missing_keys'] or info.get('mismatched_keys') or info.get('error_msgs'):
        raise RuntimeError('Incomplete BF16 model load')
    if not all(p.device.type == 'cuda' for p in model.parameters()):
        raise RuntimeError('BF16 must run on the same GPU without offload')
    return model


def generate(model, tokenizer, messages, template, decoder, generation):
    import torch
    from transformers import set_seed
    set_seed(generation['seed'])
    value = encoded(tokenizer,messages,template,tensors=True).to('cuda')
    ids = value['input_ids'][0].tolist()
    if len(ids)+generation['max_new_tokens'] > generation['context_tokens']:
        raise ValueError('Frozen context budget exceeded; do not truncate input')
    stops = stop_token_ids(model,tokenizer)
    kwargs = {}
    if decoder == 'constrained':
        from json_decoding import processor
        kwargs['logits_processor'] = [processor(model,tokenizer,decoding_schema(),stops)]
    elif decoder != 'off':
        raise ValueError('Unknown decoder treatment')
    with torch.inference_mode():
        output = model.generate(**value,do_sample=False,max_new_tokens=generation['max_new_tokens'],
            use_cache=True,eos_token_id=stops,pad_token_id=tokenizer.eos_token_id,**kwargs)
    tokens = output[0,len(ids):]
    raw = tokenizer.decode(tokens,skip_special_tokens=True)
    ended = bool(len(tokens)) and int(tokens[-1]) in stops
    diagnostics = diagnose_reply(raw,ended,len(tokens),generation['max_new_tokens'])
    try:
        accepted = validate_reply(raw)
    except (ValueError,TypeError,KeyError):
        accepted = None
    try:
        obj = json.loads(raw)
        diagnostic_text = obj.get('spoken_text') if isinstance(obj,dict) else None
        if not isinstance(diagnostic_text,str):
            diagnostic_text = None
    except (ValueError,TypeError):
        diagnostic_text = None
    return {'raw':raw,'reply':accepted,'diagnostic_spoken_text':diagnostic_text,
      'diagnostic_text_is_app_accepted':bool(accepted is not None and diagnostics['contract_valid']),
      'diagnostics':diagnostics,'json_valid':diagnostics['contract_valid'],'eos_reached':ended,
      'tokens':len(tokens),'prompt_tokens':len(ids),'input_ids_sha256':token_hash(ids),
      'eos_token_ids':stops,'last_token_id':int(tokens[-1]) if len(tokens) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--source',required=True,help='Preserved v1 prompt comparison; exact original-base histories are shared')
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    cfg = read_config(args.config)
    settings = plan()
    verify_one_factor(settings['conditions'])
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    payload,generation = prepare_inputs(artifact_output(args.source))
    output = artifact_output(args.output)
    if output.exists():
        raise FileExistsError('Preserve prior results; select a new output directory')
    adapter = ROOT/cfg['output_dir']/'adapter'
    receipt = json.loads((adapter.parent/'result.json').read_text(encoding='utf-8'))
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors') != receipt['adapter_sha256']:
        raise ValueError('Adapter receipt/hash mismatch')
    from transformers import AutoTokenizer
    from trl.chat_template_utils import get_training_chat_template
    tokenizer = AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    official = tokenizer.chat_template
    training = get_training_chat_template(tokenizer)
    if tokenizer.chat_template != official:
        raise ValueError('TRL unexpectedly mutated the default inference template')
    token_audit = audit(tokenizer,official,training,payload)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'inputs.local.json',payload)
    write_json(output/'template-audit.local.json',{'cases':token_audit,'trl_does_not_mutate_tokenizer':True,
      'official_template_sha256':hashlib.sha256(str(official).encode()).hexdigest(),
      'training_template_sha256':hashlib.sha256(training.encode()).hexdigest()})
    write_json(output/'templates.local.json',{'official':official,'training':training})
    setup_seed(generation['seed'])
    summary = {'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),'results':[],
      'expected_logical_results':len(payload)*8,'generation':generation,'conditions':settings['conditions'],
      'plan_sha256':sha256(ROOT/'training/configs/runtime-ablation-plan.json'),
      'base_sha256':cfg['checkpoint_sha256'],'adapter_sha256':receipt['adapter_sha256'],
      'training_executed':False,'android_changed':False,'common_input_policy':settings['common_history'],
      'inputs_sha256':sha256(output/'inputs.local.json'),'actual_generate_calls':0,'equivalent_reuses':0,
      'load_metadata':[]}
    try:
        import torch
        from peft import PeftModel
        for precision in ('nf4','bf16'):
            for candidate in ('base','adapter'):
                model = load_precision(cfg,precision)
                if candidate == 'adapter':
                    model = PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
                model.requires_grad_(False)
                model.eval()
                if not all(p.device.type == 'cuda' for p in model.parameters()):
                    raise RuntimeError('Unexpected offload including adapter')
                summary['load_metadata'].append({'precision':precision,'candidate':candidate,
                  'parameter_dtypes':dict(Counter(str(p.dtype) for p in model.parameters())),
                  'lora_dtypes':dict(Counter(str(p.dtype) for name,p in model.named_parameters() if 'lora_' in name)),
                  'linear4bit_count':sum(type(m).__name__=='Linear4bit' for m in model.modules()),
                  'all_cuda':True,'all_frozen':all(not p.requires_grad for p in model.parameters())})
                for index,item in enumerate(payload):
                    conditions = ('baseline','training_template','decoder_off') if precision=='nf4' else ('bf16',)
                    baseline = None
                    for condition in conditions:
                        options = settings['conditions'][condition]
                        reuse = condition=='training_template' and token_audit[index]['token_ids_identical']
                        started = time.perf_counter()
                        if reuse:
                            response = baseline
                            summary['equivalent_reuses'] += 1
                        else:
                            response = generate(model,tokenizer,item['messages'],
                                training if options['template']=='training' else official,options['decoder'],generation)
                            summary['actual_generate_calls'] += 1
                        if condition == 'baseline':
                            baseline = response
                        expected_hash = token_audit[index]['training_ids_sha256' if options['template']=='training' else 'official_ids_sha256']
                        if response['input_ids_sha256'] != expected_hash:
                            raise ValueError('Actual model input differs from audited one-factor input')
                        name = f'{condition}-{candidate}-{item["situation"]["id"].replace(":","-")}.local.json'
                        write_json(output/name,{'situation':item['situation'],'messages':item['messages'],
                          'response':response,'condition':condition,'candidate':candidate,
                          'equivalent_input_reused':reuse,'input_source_sha256':item['source_sha256']})
                        row = {'situation_id':item['situation']['id'],'condition':condition,'candidate':candidate,
                          'equivalent_input_reused':reuse,'elapsed_seconds':time.perf_counter()-started,
                          **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}}
                        summary['results'].append(row)
                        print(json.dumps({'n':len(summary['results']),'total':len(payload)*8,
                          'actual_calls':summary['actual_generate_calls'],'condition':condition,
                          'candidate':candidate,'situation':item['situation']['id'],
                          'valid':response['json_valid'],'reused':reuse},ensure_ascii=False),flush=True)
                del model
                clear_cuda()
        summary['completed'] = len(summary['results']) == summary['expected_logical_results']
    except Exception as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output/'summary.local.json',summary)


if __name__ == '__main__':
    main()
