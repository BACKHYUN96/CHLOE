#!/usr/bin/env python3
"""Local-PC VoxCPM2 experiment. No paid APIs, uploads or automatic training."""
import argparse, hashlib, io, json, math, os, shutil, subprocess, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'experiments/voxcpm2-lora/lock.json'

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFC', text).lower() if c.isalnum())

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def probe(output):
    result={'platform':sys.platform,'python':sys.version.split()[0],'disk_free_gib':round(shutil.disk_usage(Path.cwd()).free/2**30,2),'gpu':None,'training_executed':False}
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,timeout=15)
        result['gpu']=p.stdout.strip() if p.returncode==0 else None
        result['gpu_probe_error']=None if p.returncode==0 else p.stderr.strip()
    except (OSError,subprocess.TimeoutExpired) as e:result['gpu_probe_error']=str(e)
    try:
        import torch
        result.update(torch=torch.__version__,cuda_available=torch.cuda.is_available(),torch_cuda=torch.version.cuda)
        if torch.cuda.is_available():result['free_vram_bytes'],result['total_vram_bytes']=torch.cuda.mem_get_info()
    except ImportError:result['torch']=None;result['cuda_available']=False
    if output:write_json(output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

def heldout_texts():
    rows=json.loads((ROOT/'app/src/main/assets/tts-comparison-cases.json').read_text(encoding='utf-8'))['cases']
    extra=['오늘도 수고했어.','힘들거나 슬플 때 내가 항상 네 곁에서 이야기 들어줄게.','반가워요. 편하게 이야기해 주세요. 저는 여기서 듣고 있을게요.']
    return {normalized(r['text']) for r in rows}|{normalized(t) for t in extra}

def split_for(text):
    # Group by normalized transcript, not row order, to prevent duplicate-text leakage.
    return 'val' if int(hashlib.sha256(normalized(text).encode()).hexdigest()[:8],16)%10==0 else 'train'

def pcm16k(encoded):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    audio,rate=sf.read(io.BytesIO(encoded),dtype='float32',always_2d=True)
    if audio.shape[1]!=1:raise ValueError('Require original mono recording; do not mix channels')
    audio=audio[:,0]
    if not np.isfinite(audio).all() or not len(audio) or np.max(np.abs(audio))==0:raise ValueError('Invalid/silent recording')
    seconds=len(audio)/rate
    if not 1.5<=seconds<=5.0:raise ValueError('Outside short-clip pilot range')
    clipped=int(np.count_nonzero(np.abs(audio)>=.999))
    if clipped>len(audio)*.001:raise ValueError('Clipping threshold exceeded')
    common=math.gcd(rate,16000)
    converted=resample_poly(audio,16000//common,rate//common).astype('float32')
    if not np.isfinite(converted).all() or np.max(np.abs(converted))>=1:raise ValueError('Resampling would clip; reject instead of normalizing')
    return converted,dict(original_sample_rate=rate,seconds=seconds,clipped_samples=clipped)

def prepare_rows(rows,output,train_seconds,val_seconds):
    import soundfile as sf
    if output.exists():raise ValueError('Choose a new output directory; no overwrite')
    stage=output.with_name(output.name+'.partial')
    if stage.exists():raise ValueError('Staging directory exists; inspect it first')
    stage.mkdir(parents=True);(stage/'original').mkdir();(stage/'audio16k').mkdir()
    totals={'train':0.,'val':0.};selected={'train':[],'val':[]};seen=set();hashes=set();rejected=0;targets={'train':train_seconds,'val':val_seconds}
    excluded=heldout_texts()
    try:
        for index,row in enumerate(rows):
            text=str(row.get('expanded_script','')).strip();key=normalized(text)
            if not key or key in seen or key in excluded:continue
            split=split_for(text)
            if totals[split]>=targets[split]:continue
            raw=row['audio'].get('bytes')
            if not raw:raise ValueError('Dataset must return embedded original audio bytes with decode=False')
            source_sha=hashlib.sha256(raw).hexdigest()
            if source_sha in hashes:continue
            try:audio,metrics=pcm16k(raw)
            except ValueError:rejected+=1;continue
            seen.add(key);hashes.add(source_sha);stem=f'kss-{index:05d}'
            (stage/'original'/f'{stem}.wav').write_bytes(raw)
            dest=stage/'audio16k'/f'{stem}.wav';sf.write(dest,audio,16000,subtype='PCM_16')
            item=dict(audio=str((output/'audio16k'/dest.name).resolve()),text=text,source_sha256=source_sha,prepared_sha256=digest(dest),**metrics)
            selected[split].append(item);totals[split]+=len(audio)/16000
            if all(totals[k]>=targets[k] for k in totals):break
        if not all(totals[k]>=targets[k] for k in totals):raise ValueError('Dataset exhausted before requested train/val durations')
        reference=selected['train'][0]['audio']
        for split,items in selected.items():
            with (stage/f'{split}.jsonl').open('w',encoding='utf-8') as f:
                for i,item in enumerate(items):
                    record={'audio':item['audio'],'text':item['text']}
                    if i%5<2 and item['audio']!=reference:record['ref_audio']=reference
                    f.write(json.dumps(record,ensure_ascii=False)+'\n')
        lock=json.loads(LOCK.read_text());report=dict(source=lock,seconds=totals,clips={k:len(v) for k,v in selected.items()},rejected_audio=rejected,reference_audio=reference,reference_text=selected['train'][0]['text'],items=selected,annotation='neutral/read speech; no invented emotion labels',uploaded=False)
        write_json(stage/'dataset-report.json',report)
        (stage/'ATTRIBUTION.txt').write_text('Kyubyong Park, KSS Dataset, 2018.\n'+lock['dataset_original']+'\nMirror: '+lock['dataset_id']+' @ '+lock['dataset_revision']+'\nCC BY-NC-SA 4.0 https://creativecommons.org/licenses/by-nc-sa/4.0/\nChanges: selected short subset, mono 16kHz PCM resampling; original WAV preserved.\nPrivate noncommercial experiment. No separate performer consent form reviewed.\n',encoding='utf-8')
        stage.rename(output);return report
    except BaseException:
        shutil.rmtree(stage);raise

def prepare(args):
    if not args.accept_noncommercial_kss:raise ValueError('Read KSS conditions first and explicitly pass --accept-noncommercial-kss')
    from datasets import load_dataset,Audio
    lock=json.loads(LOCK.read_text())
    rows=load_dataset(lock['dataset_id'],revision=lock['dataset_revision'],split='train',streaming=True).cast_column('audio',Audio(decode=False))
    result=prepare_rows(rows,args.output.resolve(),args.train_minutes*60,args.val_minutes*60)
    print(json.dumps({'clips':result['clips'],'seconds':result['seconds']},ensure_ascii=False))

def check_source(source):
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=json.loads(LOCK.read_text())['upstream_commit']:raise ValueError('Upstream commit mismatch')

def configuration(model,data,output,steps):
    report=json.loads((data/'dataset-report.json').read_text(encoding='utf-8'))
    if report['source']['dataset_revision']!=json.loads(LOCK.read_text())['dataset_revision']:raise ValueError('Unexpected dataset revision')
    return dict(pretrained_path=str(model.resolve()),train_manifest=str((data/'train.jsonl').resolve()),val_manifest=str((data/'val.jsonl').resolve()) if steps>1 else '',sample_rate=16000,out_sample_rate=48000,batch_size=1,grad_accum_steps=4 if steps>1 else 1,num_workers=0,preprocessing_num_workers=1,num_iters=steps,max_steps=steps,log_interval=1,valid_interval=max(1,steps),save_interval=max(1,min(100,steps)),learning_rate=1e-4,weight_decay=.01,warmup_steps=min(20,max(1,steps//10)),max_batch_tokens=512,max_grad_norm=1.0,save_path=str((output/'checkpoints').resolve()),tensorboard=str((output/'logs').resolve()),lambdas={'loss/diff':1.,'loss/stop':1.},lora={'enable_lm':True,'enable_dit':False,'enable_proj':False,'r':8,'alpha':8,'dropout':0.0})

def plan(args):
    import yaml
    check_source(args.source)
    if args.output.exists():raise ValueError('Use a new run directory; upstream otherwise auto-resumes')
    config=configuration(args.model,args.data,args.output,args.steps)
    args.output.mkdir(parents=True)
    (args.output/'train.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding='utf-8')
    write_json(args.output/'run-plan.json',dict(lock=json.loads(LOCK.read_text()),training_executed=False,fit_in_12gb_verified=False,steps=args.steps,config_sha256=digest(args.output/'train.yaml'),quality_claim=None))
    print('Plan only. Run on the local GPU after baseline checks:')
    print(f'{sys.executable} {Path(__file__).resolve()} train --source "{args.source.resolve()}" --run "{args.output.resolve()}"')

def train(args):
    import torch,yaml
    check_source(args.source)
    if not torch.cuda.is_available():raise ValueError('No local CUDA GPU; training was not started')
    plan=json.loads((args.run/'run-plan.json').read_text())
    if digest(args.run/'train.yaml')!=plan['config_sha256']:raise ValueError('Config changed; create a new run plan')
    config=yaml.safe_load((args.run/'train.yaml').read_text())
    model=Path(config['pretrained_path'])
    if not (model/'model.safetensors').is_file() or not (model/'audiovae.pth').is_file():raise ValueError('Official Python checkpoint required; GGUF cannot be trained by this recipe')
    environment=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',WANDB_MODE='disabled',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
    info=dict(started=True,completed=False,cuda_gpu=torch.cuda.get_device_name(),torch=torch.__version__,seed=42)
    write_json(args.run/'execution.json',info)
    with (args.run/'train-console.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,str(args.source.resolve()/'scripts/train_voxcpm_finetune.py'),'--config_path',str((args.run/'train.yaml').resolve())],env=environment,stdout=log,stderr=subprocess.STDOUT)
    checkpoint=Path(config['save_path'])/f"step_{config['num_iters']:07d}"
    valid=(checkpoint/'lora_config.json').is_file() and any((checkpoint/name).is_file() for name in ['lora_weights.safetensors','lora_weights.ckpt'])
    info.update(returncode=result.returncode,completed=result.returncode==0 and valid,checkpoint_present=valid);write_json(args.run/'execution.json',info)
    if result.returncode or not valid:raise RuntimeError('Training failed or checkpoint missing; inspect train-console.log. OOM is not a successful run.')
    print('Trainer exited successfully; checkpoints and listening quality still require review.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('probe');p.add_argument('--output',type=Path)
    p=sub.add_parser('prepare-kss');p.add_argument('--output',type=Path,required=True);p.add_argument('--train-minutes',type=float,default=10);p.add_argument('--val-minutes',type=float,default=2);p.add_argument('--accept-noncommercial-kss',action='store_true')
    p=sub.add_parser('plan');p.add_argument('--source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=1)
    p=sub.add_parser('train');p.add_argument('--source',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='probe':probe(a.output)
    elif a.command=='prepare-kss':
        if not 0<a.train_minutes<=120 or not 0<a.val_minutes<=30:parser.error('Invalid duration budget')
        prepare(a)
    elif a.command=='plan':
        if not 1<=a.steps<=10000:parser.error('Invalid step budget')
        plan(a)
    else:train(a)

if __name__=='__main__':main()
