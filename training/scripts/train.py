"""Run at most ten reviewed text-only Qwen3.5 QLoRA steps in a fresh directory."""
import argparse
import math
import random
import time
from collections import Counter

from llm_runtime import (artifact_output, attach_lora, batch_tensor, clear_cuda, encode_record,
    infer, load_base, load_records, local_path, read_config, setup_seed, sha256, tokenizer_and_template, write_json)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    args = parser.parse_args()
    cfg = read_config(args.config)
    rows = load_records(local_path(cfg['data']))
    counts = Counter(row['split'] for row in rows)
    if any(not counts[split] for split in ('train','validation','test')):
        raise ValueError('Separate reviewed train/validation/test conversations required')
    out = artifact_output(cfg['output_dir'])
    out.mkdir(parents=True,exist_ok=False)
    report = {'config':cfg,'data_sha256':sha256(local_path(cfg['data'])),'split_counts':dict(counts),
              'completed':False,'steps':[],'cpu_offload':False,'kernel_path':'reference PyTorch; no hub kernels',
              'quality_improvement_verified':False,'adapter_reloaded':False}
    try:
        import torch
        from peft import PeftModel
        setup_seed(cfg['seed'])
        tokenizer, template = tokenizer_and_template(cfg)
        encoded = {row['id']:encode_record(tokenizer,template,row,cfg['context_tokens']) for row in rows}
        report['token_masks'] = [{'id':row['id'],'tokens':len(encoded[row['id']]['input_ids']),
            'supervised_tokens':sum(x != -100 for x in encoded[row['id']]['labels'])} for row in rows]
        model, report['targets'] = attach_lora(load_base(cfg),cfg)
        params = [p for p in model.parameters() if p.requires_grad]
        report['trainable_parameters'] = sum(p.numel() for p in params)
        optimizer = torch.optim.AdamW(params,lr=cfg['learning_rate'])
        training = [row for row in rows if row['split']=='train']
        random.Random(cfg['seed']).shuffle(training)
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        model.train()
        for step in range(cfg['max_steps']):
            optimizer.zero_grad(set_to_none=True)
            row = training[step % len(training)]
            batch = batch_tensor(encoded[row['id']])
            with torch.autocast('cuda',dtype=torch.bfloat16):
                loss = model(**batch,use_cache=False).loss
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(params,1.0,error_if_nonfinite=True)
            if not math.isfinite(float(norm)) or float(norm)==0:
                raise RuntimeError('LoRA gradients must be finite and nonzero')
            optimizer.step()
            item = {'step':step+1,'loss':float(loss.detach()),'gradient_norm':float(norm)}
            report['steps'].append(item)
            print(item,flush=True)
        torch.cuda.synchronize()
        report['training_seconds'] = time.perf_counter()-started
        report['peak_gpu_allocated_bytes'] = torch.cuda.max_memory_allocated()
        report['peak_gpu_reserved_bytes'] = torch.cuda.max_memory_reserved()
        model.eval()
        heldout = {}
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
            for split in ('validation','test'):
                losses = [float(model(**batch_tensor(encoded[row['id']]),use_cache=False).loss)
                          for row in rows if row['split']==split]
                if not all(math.isfinite(value) for value in losses):
                    raise RuntimeError('Non-finite held-out loss')
                heldout[split] = sum(losses)/len(losses)
        report['heldout_loss'] = heldout
        adapter = out/'adapter'
        model.save_pretrained(adapter,safe_serialization=True)
        report['adapter_sha256'] = sha256(adapter/'adapter_model.safetensors')
        # Ensure reload uses a new base/model object, rather than the in-memory adapter.
        del model,optimizer,params,loss,batch
        clear_cuda()
        reloaded = PeftModel.from_pretrained(load_base(cfg),adapter,is_trainable=False,local_files_only=True)
        row = next(row for row in rows if row['split']=='test')
        result = infer(reloaded,tokenizer,row['messages'][:-1],cfg['seed'],cfg['max_new_tokens'])
        write_json(out/'reload-inference.local.json',result)
        report['reload_inference'] = {key:value for key,value in result.items() if key not in ('raw','reply')}
        report['adapter_reloaded'] = True
        report['reload_inference_contract_passed'] = result['json_valid']
        report['training_mechanics_completed'] = True
        report['completed'] = True
    except Exception as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        write_json(out/'result.json',report)


if __name__=='__main__':
    main()
