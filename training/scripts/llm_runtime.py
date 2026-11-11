"""Shared verified Qwen3.5 text-only QLoRA path. All model inputs remain local."""
import gc
import hashlib
import json
import os
from pathlib import Path

from data_contract import ROOT, load_records, validate_reply

os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

MODEL = 'Qwen/Qwen3.5-2B'
REVISION = '15852e8c16360a2fea060d615a32b45270f8a8fc'
CHECKPOINT_SHA = 'aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    # Serialize before creating a file; invalid evidence must not leave partial JSON.
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with Path(path).open('x', encoding='utf-8') as handle:
        handle.write(text)


def local_path(value):
    return (ROOT / value).resolve()


def artifact_output(value):
    path = local_path(value)
    path.relative_to((ROOT/'artifacts/llm-training').resolve())
    if path == (ROOT/'artifacts/llm-training').resolve():
        raise ValueError('Choose an artifact child directory')
    return path


def read_config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    if (cfg['model_id'], cfg['revision'], cfg['checkpoint_sha256']) != (MODEL, REVISION, CHECKPOINT_SHA):
        raise ValueError('This smoke path only supports the verified pinned Qwen3.5-2B')
    if not 1 <= cfg['max_steps'] <= 10 or cfg['microbatch'] != 1 or cfg['lora_rank'] != 8:
        raise ValueError('Smoke limits: at most 10 steps, microbatch1, rank8')
    if cfg['cpu_offload'] or not cfg['gradient_checkpointing']:
        raise ValueError('Smoke requires checkpointing and no CPU offload')
    return cfg


def setup_seed(seed):
    import torch
    from transformers import set_seed
    set_seed(seed)
    torch.set_num_threads(8)
    torch.backends.cuda.matmul.allow_tf32 = False
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('Verified CUDA/BF16 environment required')


def load_base(cfg, quantized=True):
    import torch
    from transformers import AutoConfig, BitsAndBytesConfig, Qwen3_5ForCausalLM
    base = local_path(cfg['base_dir'])
    if sha256(base/'model.safetensors-00001-of-00001.safetensors') != CHECKPOINT_SHA:
        raise ValueError('Original checkpoint hash mismatch')
    config = AutoConfig.from_pretrained(base, local_files_only=True, trust_remote_code=False).text_config
    kwargs = {}
    if quantized:
        kwargs['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model, info = Qwen3_5ForCausalLM.from_pretrained(base, config=config, dtype=torch.bfloat16,
        device_map={'':0 if quantized else 'cpu'}, attn_implementation='eager',
        local_files_only=True, trust_remote_code=False,
        key_mapping={r'^model.language_model\.':'model.'}, output_loading_info=True, **kwargs)
    if info['missing_keys'] or info.get('mismatched_keys') or info.get('error_msgs'):
        raise RuntimeError('Checkpoint load was incomplete')
    if quantized and not all(p.device.type == 'cuda' for p in model.parameters()):
        raise RuntimeError('Unexpected CPU/disk offload')
    return model


def tokenizer_and_template(cfg):
    from transformers import AutoTokenizer
    from trl.chat_template_utils import get_training_chat_template
    tokenizer = AutoTokenizer.from_pretrained(local_path(cfg['base_dir']), local_files_only=True, trust_remote_code=False)
    template = get_training_chat_template(tokenizer)
    if template is None or 'generation' not in template:
        raise RuntimeError('Verified Qwen3.5 assistant-mask training template required')
    return tokenizer, template


def encode_record(tokenizer, template, row, context):
    value = tokenizer.apply_chat_template(row['messages'], chat_template=template, tokenize=True,
        add_generation_prompt=False, enable_thinking=False, return_dict=True, return_assistant_tokens_mask=True)
    ids, mask = value['input_ids'], value['assistant_masks']
    if len(ids) > context or len(mask) != len(ids) or not any(mask):
        raise ValueError('Overlong/incomplete sample or empty assistant supervision; no truncation allowed')
    supervised = tokenizer.decode([token for token, keep in zip(ids, mask) if keep])
    if row['messages'][-1]['content'] not in supervised or '<think>' in supervised:
        raise ValueError('Complete assistant JSON must be supervised without reasoning')
    if any(message['content'] in supervised for message in row['messages'][:-1]):
        raise ValueError('System/user content leaked into labels')
    return {'input_ids':ids, 'labels':[token if keep else -100 for token, keep in zip(ids, mask)]}


def batch_tensor(encoded):
    import torch
    ids = torch.tensor([encoded['input_ids']], device='cuda')
    return {'input_ids':ids, 'attention_mask':torch.ones_like(ids),
            'labels':torch.tensor([encoded['labels']], device='cuda')}


def attach_lora(model, cfg):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    targets = [name for name, module in model.named_modules()
               if '.self_attn.' in name and name.endswith(('.q_proj','.v_proj'))]
    if len(targets) != 12:
        raise RuntimeError('Unexpected full-attention LoRA targets; inspect this runtime')
    # The pinned PEFT API accepts the activation_* spelling (gradient_* is deprecated).
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            activation_checkpointing_kwargs={'use_reentrant':False})
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=cfg['lora_rank'],lora_alpha=cfg['lora_alpha'],
        lora_dropout=0.0,target_modules=targets,bias='none',task_type='CAUSAL_LM'))
    return model, targets


def stop_token_ids(model, tokenizer):
    # This pinned text config uses endoftext, while the chat tokenizer uses
    # im_end. Both are legitimate EOG tokens; checking only tokenizer EOS lied
    # about short, normally terminated generations in the initial probe.
    configured = model.generation_config.eos_token_id
    values = configured if isinstance(configured,list) else [configured]
    return sorted({item for item in values+[tokenizer.eos_token_id] if item is not None})


def infer(model, tokenizer, messages, seed, max_tokens):
    import torch
    from transformers import set_seed
    set_seed(seed)
    model.eval()
    value = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
        enable_thinking=False, return_dict=True, return_tensors='pt').to('cuda')
    if value['input_ids'].shape[-1] + max_tokens > 2048:
        raise ValueError('Generation would exceed the frozen app-context budget')
    eos_ids = stop_token_ids(model,tokenizer)
    with torch.inference_mode():
        output = model.generate(**value, do_sample=False, max_new_tokens=max_tokens, use_cache=True,
                                eos_token_id=eos_ids,pad_token_id=tokenizer.eos_token_id)
    generated = output[0,value['input_ids'].shape[-1]:]
    raw = tokenizer.decode(generated, skip_special_tokens=True)
    # The nothink template pre-fills the empty think block; raw is assistant content.
    try:
        reply = validate_reply(raw)
    except (ValueError,TypeError,KeyError):
        reply = None
    ended = int(generated[-1]) in eos_ids
    return {'raw':raw,'reply':reply,'tokens':len(generated), 'eos_reached':ended,
            'json_valid':reply is not None and ended,'last_token_id':int(generated[-1]),'eos_token_ids':eos_ids}


def clear_cuda():
    import torch
    gc.collect()
    torch.cuda.empty_cache()
