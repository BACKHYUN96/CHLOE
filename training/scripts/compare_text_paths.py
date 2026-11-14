"""Compare unmodified CHLOE wrapper with direct official text-only APIs locally."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from data_contract import ROOT, diagnose_reply, validate_reply
from llm_runtime import (artifact_output, clear_cuda, contract_messages, decoding_schema,
                         infer, load_base, read_config, setup_seed, sha256, write_json)
from runtime_ablation import token_hash


def jsonable(value):
    return json.loads(json.dumps(value,default=lambda v:sorted(v) if isinstance(v,set) else str(v)))


def state_fingerprint(model):
    # Includes bitsandbytes quantization state tensors; no model state is exported.
    import torch
    result = {}
    for name,tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        digest = hashlib.sha256()
        raw = value.reshape(-1).view(torch.uint8).numpy()
        for offset in range(0,len(raw),1024*1024):
            digest.update(raw[offset:offset+1024*1024].tobytes())
        result[name] = {'shape':list(value.shape),'dtype':str(value.dtype),'sha256':digest.hexdigest()}
    return result


def changed_fields(left,right):
    return {k:{'wrapper':left.get(k),'official':right.get(k)} for k in sorted(set(left)|set(right)) if left.get(k)!=right.get(k)}


def load_official(cfg):
    import torch
    from transformers import Qwen3_5ForCausalLM, BitsAndBytesConfig
    # Official loader extracts Qwen3_5TextConfig and applies installed native
    # PrefixChange conversion. No CHLOE config extraction or manual key mapping.
    return Qwen3_5ForCausalLM.from_pretrained(ROOT/cfg['base_dir'],
        dtype=torch.bfloat16,device_map={'':0},attn_implementation='eager',
        local_files_only=True,trust_remote_code=False,output_loading_info=True,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16))


def official_inputs(tokenizer,conditioned):
    text = tokenizer.apply_chat_template(conditioned,tokenize=False,
        add_generation_prompt=True,enable_thinking=False)
    return tokenizer(text,add_special_tokens=False,return_tensors='pt')


def official_generate(model,tokenizer,conditioned,generation):
    import torch
    from transformers import set_seed
    from json_decoding import processor
    set_seed(generation['seed'])
    inputs = official_inputs(tokenizer,conditioned).to('cuda')
    count = inputs['input_ids'].shape[-1]
    if count+generation['max_new_tokens']>generation['context_tokens']:
        raise ValueError('No context truncation allowed')
    configured = model.generation_config.eos_token_id
    stops = sorted(set((configured if isinstance(configured,list) else [configured])+[tokenizer.eos_token_id]))
    with torch.inference_mode():
        output = model.generate(**inputs,do_sample=False,max_new_tokens=generation['max_new_tokens'],
            use_cache=True,eos_token_id=stops,pad_token_id=tokenizer.eos_token_id,
            logits_processor=[processor(model,tokenizer,decoding_schema(),stops)])
    tokens = output[0,count:]
    raw = tokenizer.decode(tokens,skip_special_tokens=True)
    ended = bool(len(tokens)) and int(tokens[-1]) in stops
    try:
        reply = validate_reply(raw)
    except (ValueError,TypeError,KeyError):
        reply = None
    diagnostic = diagnose_reply(raw,ended,len(tokens),generation['max_new_tokens'])
    return {'raw':raw,'reply':reply,'tokens':len(tokens),'eos_reached':ended,
      'json_valid':diagnostic['contract_valid'],'diagnostics':diagnostic,
      'prompt_tokens':count,'eos_token_ids':stops,'last_token_id':int(tokens[-1])}


def capture_call(kwargs,output):
    return {'inputs':{k:{'shape':list(v.shape),'ids':v.detach().cpu().tolist()} for k,v in kwargs.items() if hasattr(v,'shape')},
      'kwargs':{k:([type(p).__module__+'.'+type(p).__name__ for p in v] if k=='logits_processor' else jsonable(v))
                for k,v in kwargs.items() if not hasattr(v,'shape')},
      'output_ids':output.detach().cpu().tolist()}


@contextmanager
def observe_generate(model,records):
    original = model.generate
    owned = 'generate' in model.__dict__
    previous = model.__dict__.get('generate')
    def observed(*args,**kwargs):
        if args:
            raise ValueError('Expected explicit named inputs')
        output = original(**kwargs)
        records.append(capture_call(kwargs,output))
        return output
    model.generate = observed
    try:
        yield
    finally:
        if owned:
            model.generate = previous
        else:
            del model.generate


def response_diagnostic(response):
    try:
        value = json.loads(response['raw'])
        text = value.get('spoken_text') if isinstance(value,dict) else None
    except (ValueError,TypeError):
        text = None
    return {**response,'diagnostic_spoken_text':text if isinstance(text,str) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    cfg = read_config(args.config)
    source,output = artifact_output(args.source),artifact_output(args.output)
    if output.exists():
        raise FileExistsError('Preserve existing results; select a new directory')
    previous = json.loads((source/'summary.local.json').read_text())
    payload = json.loads((source/'inputs.local.json').read_text())
    if not previous['completed'] or len(payload)!=46:
        raise ValueError('Completed frozen 46-situation source required')
    if previous['inputs_sha256'] != sha256(source/'inputs.local.json'):
        raise ValueError('Frozen messages changed')
    adapter = ROOT/cfg['output_dir']/'adapter'
    receipt = json.loads((adapter.parent/'result.json').read_text())
    if not receipt['completed'] or sha256(adapter/'adapter_model.safetensors') != receipt['adapter_sha256']:
        raise ValueError('Adapter changed')
    if sha256(ROOT/cfg['base_dir']/'model.safetensors-00001-of-00001.safetensors') != cfg['checkpoint_sha256']:
        raise ValueError('Checkpoint changed')
    sys.path.insert(0,str(ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'))
    from transformers import AutoTokenizer
    import torch
    from peft import PeftModel
    tokenizer = AutoTokenizer.from_pretrained(ROOT/cfg['base_dir'],local_files_only=True,trust_remote_code=False)
    conditioned = [contract_messages(item['messages'],'schema') for item in payload]
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'inputs.local.json',payload)
    write_json(output/'conditioned-inputs.local.json',conditioned)
    summary = {'completed':False,'started_at':datetime.now(timezone.utc).isoformat(),
      'plan_sha256':sha256(ROOT/'training/configs/text-path-plan.json'),'generation':previous['generation'],
      'conditions':{'wrapper':{},'official':{}},'results':[],'load_metadata':[],
      'expected_logical_results':184,'actual_generate_calls':0,'equivalent_reuses':0,
      'base_sha256':cfg['checkpoint_sha256'],'adapter_sha256':receipt['adapter_sha256'],
      'source_summary_sha256':sha256(source/'summary.local.json'),
      'inputs_sha256':sha256(output/'inputs.local.json'),'training_executed':False,'android_changed':False}
    setup_seed(previous['generation']['seed'])
    try:
        for candidate in ('base','adapter'):
            for path in ('wrapper','official'):
                if path=='wrapper':
                    model = load_base(cfg)
                    info = None
                else:
                    model,info = load_official(cfg)
                    if any(info.get(k) for k in ('missing_keys','mismatched_keys','error_msgs','unexpected_keys')):
                        raise RuntimeError('Official text-only load incomplete')
                if candidate=='adapter':
                    model = PeftModel.from_pretrained(model,adapter,is_trainable=False,local_files_only=True)
                model.requires_grad_(False)
                model.eval()
                if not all(p.device.type=='cuda' for p in model.parameters()):
                    raise RuntimeError('No offload allowed')
                metadata = {'path':path,'candidate':candidate,'class':type(model).__name__,
                  'config_class':type(model.config).__name__,'config':model.config.to_dict(),
                  'generation_config':model.generation_config.to_dict(),'official_loading_info':jsonable(info),
                  'all_cuda':True,'all_frozen':all(not p.requires_grad for p in model.parameters()),
                  'parameter_dtypes':dict(Counter(str(p.dtype) for p in model.parameters())),
                  'lora_dtypes':dict(Counter(str(p.dtype) for n,p in model.named_parameters() if 'lora_' in n)),
                  'embedding_head_tied':model.get_input_embeddings().weight.data_ptr()==model.get_output_embeddings().weight.data_ptr(),
                  'state':state_fingerprint(model)}
                write_json(output/f'{path}-{candidate}-load.local.json',metadata)
                summary['load_metadata'].append({k:v for k,v in metadata.items() if k not in ('config','generation_config','state')})
                for i,item in enumerate(payload):
                    name = f'{path}-{candidate}-{item["situation"]["id"].replace(":","-")}'
                    # Independent prefill check covers full-vocabulary last-token
                    # logits for every situation, not only greedy top-1.
                    inputs = official_inputs(tokenizer,conditioned[i]).to('cuda')
                    with torch.inference_mode():
                        logits = model(**inputs,use_cache=False,logits_to_keep=1).logits[0,-1].float().cpu()
                    if not torch.isfinite(logits).all():
                        raise RuntimeError('Non-finite prefill logits')
                    torch.save(logits,output/f'{name}.logits.local.pt')
                    observed = []
                    with observe_generate(model,observed):
                        if path=='wrapper':
                            response = infer(model,tokenizer,item['messages'],summary['generation']['seed'],
                                summary['generation']['max_new_tokens'],contract_mode='constrained')
                        else:
                            response = official_generate(model,tokenizer,conditioned[i],summary['generation'])
                    if len(observed)!=1:
                        raise RuntimeError('One actual generate call required')
                    input_ids = observed[0]['inputs']['input_ids']['ids'][0]
                    if input_ids != inputs['input_ids'][0].tolist():
                        raise RuntimeError('Actual generate input differs from prefill input')
                    response = response_diagnostic(response)
                    response['input_ids_sha256'] = token_hash(input_ids)
                    write_json(output/f'{name}.local.json',{'situation':item['situation'],
                        'messages':item['messages'],'response':response,'condition':path,'candidate':candidate,
                        'equivalent_input_reused':False,'observed':observed[0]})
                    summary['actual_generate_calls'] += 1
                    summary['results'].append({'condition':path,'candidate':candidate,'situation_id':item['situation']['id'],
                        **{k:v for k,v in response.items() if k not in ('raw','reply','diagnostic_spoken_text')}})
                    print(json.dumps({'n':summary['actual_generate_calls'],'total':184,'path':path,
                        'candidate':candidate,'situation':item['situation']['id'],'valid':response['json_valid']}),flush=True)
                del model,inputs,logits
                clear_cuda()
        summary['completed'] = len(summary['results'])==184
    except Exception as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output/'summary.local.json',summary)


if __name__=='__main__':
    main()
