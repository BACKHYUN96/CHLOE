#!/usr/bin/env python3
"""Matched local Python baseline/LoRA WAVs. Source, reference and seeds are fixed."""
import argparse,json,os,time,uuid
from pathlib import Path
from voxcpm2_lab import ROOT,LOCK,check_source,digest,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--all-cases',action='store_true')
    a=p.parse_args();check_source(a.source)
    if not (a.model/'model.safetensors').is_file() or not (a.model/'audiovae.pth').is_file():p.error('Prepare official Python model files first')
    if a.output.exists():p.error('Use a new output directory')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',WANDB_MODE='disabled')
    import numpy as np,soundfile as sf,torch
    if not torch.cuda.is_available():p.error('Run on the local CUDA PC; no cloud fallback')
    sys_path=str(a.source.resolve()/'src');__import__('sys').path.insert(0,sys_path)
    from voxcpm import VoxCPM
    from voxcpm.model.voxcpm2 import LoRAConfig
    data=json.loads((a.data/'dataset-report.json').read_text(encoding='utf-8'))
    reference=data['reference_audio']
    if not Path(reference).is_file():p.error('Prepared local reference WAV missing')
    rows=json.loads((ROOT/'app/src/main/assets/tts-comparison-cases.json').read_text(encoding='utf-8'))['cases']
    if not a.all_cases:rows=[r for r in rows if r['id'] in ['ko01','ko06','ko07','ko12']]
    report=dict(lock=json.loads(LOCK.read_text()),platform='local-pc-cuda',reference_sha256=digest(reference),settings=dict(cfg_value=2.0,inference_timesteps=10,max_len=200,normalize=False,denoise=False,retry_badcase=False,seeds=[42,43,44]),model_files_sha256={name:digest(a.model/name) for name in ['config.json','model.safetensors','audiovae.pth']},clips=[],failures=[],human_ratings=None,quality_improvement=None)
    kwargs={}
    if a.checkpoint:
        saved=json.loads((a.checkpoint/'lora_config.json').read_text());kwargs['lora_config']=LoRAConfig(**saved['lora_config'])
        report['adapter_files']={f.name:digest(f) for f in a.checkpoint.iterdir() if f.is_file() and f.name.startswith('lora_')}
    a.output.mkdir(parents=True)
    try:
        start=time.perf_counter()
        model=VoxCPM.from_pretrained(str(a.model.resolve()),load_denoiser=False,local_files_only=True,optimize=False,device='cuda',**kwargs)
        report['model_init_ms']=(time.perf_counter()-start)*1000
        if a.checkpoint:
            loaded,skipped=model.load_lora(str(a.checkpoint.resolve()))
            if not loaded or skipped:raise ValueError('Adapter load incomplete; cannot claim a trained comparison')
        for adapted in ([False,True] if a.checkpoint else [False]):
            if a.checkpoint:model.set_lora_enabled(adapted)
            for row in rows:
                for seed in [42,43,44]:
                    identity=dict(case_id=row['id'],text=row['text'],seed=seed,adapter_enabled=adapted)
                    filename=uuid.uuid4().hex+'.wav'
                    try:
                        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter()
                        wave=model.generate(text=row['text'],reference_wav_path=reference,cfg_value=2.0,inference_timesteps=10,max_len=200,normalize=False,denoise=False,retry_badcase=False,seed=seed)
                        torch.cuda.synchronize();elapsed=(time.perf_counter()-start)*1000
                        if not np.isfinite(wave).all() or not np.any(wave):raise ValueError('Invalid PCM')
                        sf.write(a.output/filename,wave,model.tts_model.sample_rate,subtype='PCM_16')
                        seconds=len(wave)/model.tts_model.sample_rate
                        report['clips'].append(dict(identity,file=filename,wav_sha256=digest(a.output/filename),generation_ms=elapsed,audio_seconds=seconds,rtf=elapsed/(seconds*1000),peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),human_ratings=None))
                    except Exception as e:
                        (a.output/filename).unlink(missing_ok=True);report['failures'].append(dict(identity,error=str(e)))
                        if isinstance(e,torch.cuda.OutOfMemoryError):raise
                    finally:write_json(a.output/'comparison.json',report)
    except Exception as e:
        report['fatal_error']=str(e);write_json(a.output/'comparison.json',report);raise
    print('Local WAVs ready. No human quality improvement has been established.')

if __name__=='__main__':main()
