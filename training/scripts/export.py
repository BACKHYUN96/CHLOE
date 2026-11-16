"""Merge/convert only after a human-reviewed quality receipt; preserve all inputs."""
import argparse
import json
import subprocess
from pathlib import Path

from data_contract import ROOT
from llm_runtime import artifact_output, load_base, read_config, sha256, write_json


LLAMA_PIN='aa75ff3239f9cc675b081697deda9e1b112345c6'


def validate_quality_approval(approval, adapter_hash):
    if (approval.get('human_review_completed') is not True or approval.get('quality_gain_verified') is not True
            or not approval.get('reviewer') or approval.get('adapter_sha256') != adapter_hash):
        raise ValueError('Human-reviewed quality improvement and matching adapter required before merge/export')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--format',choices=['gguf'],required=True)
    parser.add_argument('--quality-approval',type=Path,required=True,
        help='Local JSON receipt: human_review_completed, quality_gain_verified, reviewer, adapter_sha256')
    parser.add_argument('--llama-cpp',type=Path,default=ROOT/'external/llama.cpp')
    parser.add_argument('--output',help='Fresh artifact directory; default output_dir-export')
    args=parser.parse_args()
    cfg=read_config(args.config)
    adapter=artifact_output(cfg['output_dir'])/'adapter'
    approval=json.loads(args.quality_approval.read_text(encoding='utf-8'))
    validate_quality_approval(approval, sha256(adapter/'adapter_model.safetensors'))
    checkout=args.llama_cpp.resolve()
    pin=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    if pin!=LLAMA_PIN or subprocess.check_output(['git','-C',str(checkout),'status','--porcelain'],text=True).strip():
        raise ValueError('Use a clean checkout of the Android-pinned llama.cpp')
    quantizer=checkout/'build/bin/llama-quantize'
    converter=checkout/'convert_hf_to_gguf.py'
    if not quantizer.is_file() or not converter.is_file():
        raise ValueError('Build the pinned quantizer and prepare converter dependencies first')
    out=artifact_output(args.output or cfg['output_dir']+'-export')
    out.mkdir(parents=True,exist_ok=False)
    report={'completed':False,'android_import_verified':False,'llama_cpp_pin':pin,
            'merge_device':'cpu','base_or_android_files_modified':False,'approval_sha256':sha256(args.quality_approval)}
    try:
        import sys
        from peft import PeftModel
        from transformers import AutoTokenizer
        from llm_runtime import local_path
        model=PeftModel.from_pretrained(load_base(cfg,quantized=False),adapter,is_trainable=False,local_files_only=True)
        merged=model.merge_and_unload(safe_merge=True)
        merged.save_pretrained(out/'merged',safe_serialization=True)
        AutoTokenizer.from_pretrained(local_path(cfg['base_dir']),local_files_only=True).save_pretrained(out/'merged')
        commands=[[sys.executable,str(converter),str(out/'merged'),'--outtype','f16','--outfile',str(out/'model-f16.gguf')],
                  [str(quantizer),str(out/'model-f16.gguf'),str(out/'model-Q4_K_M.gguf'),'Q4_K_M']]
        for index,command in enumerate(commands):
            with (out/f'convert-{index}.log').open('x') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        report['gguf_sha256']=sha256(out/'model-Q4_K_M.gguf')
        report['completed']=True
    except Exception as error:
        report['error_type']=type(error).__name__
        raise
    finally:
        write_json(out/'result.json',report)


if __name__=='__main__':
    main()
