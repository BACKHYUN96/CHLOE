#!/usr/bin/env python3
"""Offline Korean TTS comparison runner. Downloads are a separate, explicit preparation step."""
import argparse, array, hashlib, json, math, os, platform, re, subprocess, time, unicodedata, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'app/src/main/assets/tts-comparison-cases.json'
CUSTOM = 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'
DESIGN = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
VOX = 'openbmb/VoxCPM2'
COSY = 'FunAudioLLM/Fun-CosyVoice3-0.5B-2512'
COMMON = '친한 친구와 대화하듯 편안하고 다정하게 말해 주세요. 감정을 과장하지 말고 문장 흐름을 자연스럽게 유지해 주세요. 매 문장 앞에 과장된 들숨을 반복하지 마세요.'
VOICE = '자연스러운 한국어를 구사하는 성인 여성의 따뜻하고 맑은 목소리. 특정 인물을 모방하지 않는 편안한 중간 음역. '
RUNTIME = '4562731dc612cb87b4cd1eedac275a17d1078773'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(4*1024*1024):h.update(b)
    return h.hexdigest()


def cer(reference, hypothesis):
    def norm(s):return ''.join(c for c in unicodedata.normalize('NFC',s).lower() if unicodedata.category(c)[0] in 'LN')
    a,b=norm(reference),norm(hypothesis)
    if not a:raise ValueError('Empty normalized reference')
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return dict(edits=row[-1],reference_characters=len(a),cer=row[-1]/len(a),normalization='NFC lowercase letters/numbers; remove spaces/punctuation')


def stats(path):
    with wave.open(str(path),'rb') as f:
        if f.getnchannels()!=1 or f.getsampwidth()!=2 or f.getframerate() not in [16000,24000,48000]:raise ValueError('Expected mono PCM16 16/24/48 kHz')
        rate=f.getframerate(); samples=array.array('h',f.readframes(f.getnframes()))
    if not samples:raise ValueError('Empty PCM')
    if __import__('sys').byteorder!='little':samples.byteswap()
    rms=math.sqrt(sum(x*x for x in samples)/len(samples))
    if rms==0:raise ValueError('Silent PCM')
    return dict(sample_rate=rate,samples=len(samples),audio_seconds=len(samples)/rate,pcm_rms=rms,
                pcm_full_scale_samples=sum(abs(x)>=32767 for x in samples))


def atomic(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True,choices=[CUSTOM,DESIGN,VOX,COSY]);p.add_argument('--models',required=True,type=Path)
    p.add_argument('--binary',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--condition',choices=['controlled','optimized'],default='controlled');p.add_argument('--instruction')
    p.add_argument('--case',action='append',help='Subset; omit for all 20 cases');p.add_argument('--seeds',nargs='+',type=int,default=[42,43,44])
    p.add_argument('--resume',action='store_true');p.add_argument('--timeout',type=int,default=240)
    p.add_argument('--cosy-config-only-init',action='store_true',help='Construct Qwen2 from local config before upstream strict full llm.pt loading; avoid duplicate pretrained weights')
    p.add_argument('--reference-wav',type=Path);p.add_argument('--reference-transcript');p.add_argument('--reference-rights-confirmed',action='store_true')
    p.add_argument('--asr-transcripts',type=Path,help='Optional local ASR output JSON keyed by WAV basename')
    args=p.parse_args()
    if not args.models.is_dir():p.error('Prepare a local model directory first; inference never downloads weights')
    cases=json.loads(CASES.read_text(encoding='utf-8'))['cases']
    if args.case:
        requested=set(args.case)
        if requested-{c['id'] for c in cases}:p.error('Unknown case id')
        cases=[c for c in cases if c['id'] in requested]
    if args.condition=='controlled' and args.instruction is not None:p.error('Custom instruction belongs to optimized condition')
    if any(s<0 or s>2147483647 for s in args.seeds) or len(set(args.seeds))!=len(args.seeds):p.error('Distinct nonnegative Int32 seeds required')
    instruction=args.instruction if args.instruction is not None else (VOICE if args.model in [DESIGN,VOX] else '')+COMMON
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:p.error('Use empty output or explicit --resume')
    args.output.mkdir(parents=True,exist_ok=True)
    manifest_file=args.output/'comparison-manifest.json'
    report=json.loads(manifest_file.read_text()) if args.resume and manifest_file.exists() else dict(schema=1,clips=[],failures=[],device_test=False,human_ratings=None)
    platform_id='windows-host' if platform.system()=='Windows' else 'macos-host' if platform.system()=='Darwin' else 'linux-host'
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
    pack={}; loaded=None; model_init_ms=None; python_calls=0
    if args.model in [CUSTOM,DESIGN]:
        if not args.binary or not args.binary.is_file():p.error('--binary must be the built pinned qwen CLI')
        packfile=args.models/('model-pack.json' if args.model==CUSTOM else 'design-pack.json')
        pack=json.loads(packfile.read_text());assert pack['model_id']==args.model and pack['runtime_commit']==RUNTIME
        for item in pack['files']:
            path=args.models/item['name'];assert path.stat().st_size==item['size'] and digest(path)==item['sha256']
    elif args.model==VOX and args.binary:
        pack=json.loads((args.models/'vox-pack.json').read_text())
        assert pack['model_id']==VOX
        for item in pack['files']:
            path=args.models/item['name'];assert path.stat().st_size==item['size'] and digest(path)==item['sha256']
    elif args.model==VOX:
        from voxcpm import VoxCPM
        loaded=VoxCPM.from_pretrained(str(args.models.resolve()),load_denoiser=False)
    else:
        if not args.reference_rights_confirmed or not args.reference_wav or not args.reference_transcript:p.error('CosyVoice3 requires explicitly authorized reference WAV and exact transcript')
        import torch
        torch.set_num_threads(4)
        from cosyvoice.cli.cosyvoice import AutoModel
        if args.cosy_config_only_init:
            import inspect
            from transformers import Qwen2Config, Qwen2ForCausalLM
            from cosyvoice.llm.llm import Qwen2Encoder
            from cosyvoice.cli.model import CosyVoice3Model
            code=inspect.getsource(CosyVoice3Model.load)
            if 'self.llm.load_state_dict' not in code or 'strict=True' not in code:raise RuntimeError('Complete strict LLM loading must be verified before config-only initialization')
            def initialize_from_config(self,pretrain_path):
                torch.nn.Module.__init__(self)
                config=Qwen2Config.from_pretrained(pretrain_path,local_files_only=True)
                self.model=Qwen2ForCausalLM(config)
            Qwen2Encoder.__init__=initialize_from_config
        pack=json.loads((args.models/'cosy-pack.json').read_text())
        for item in pack['files']:
            path=args.models/item['name'];assert path.stat().st_size==item['size'] and digest(path)==item['sha256']
        started=time.perf_counter()
        try:
            loaded=AutoModel(model_dir=str(args.models.resolve()),load_trt=False,load_vllm=False,fp16=False)
        except Exception as error:
            report['initialization_error']=dict(model_id=args.model,type=type(error).__name__,message=str(error))
            atomic(manifest_file,report)
            raise
        model_init_ms=(time.perf_counter()-started)*1000
    reference_sha=digest(args.reference_wav) if args.reference_wav else None
    if any(r['model_id']==args.model and r['condition']==args.condition and r.get('reference_audio_sha256')!=reference_sha for r in report['clips']):p.error('Reference changed; use a new output folder')
    transcriptions=json.loads(args.asr_transcripts.read_text()) if args.asr_transcripts else {}
    for c in cases:
        for seed in args.seeds:
            # A manifest can be shared by staged model runs. WAV names carry no model name.
            identity=f'{args.model}|{args.condition}|{c["id"]}|{seed}|{instruction}'+(f'|reference={reference_sha}' if reference_sha else '')
            key=hashlib.sha256(identity.encode()).hexdigest()[:24]
            wav=args.output/(key+'.wav')
            existing=next((r for r in report['clips'] if r['file']==wav.name),None)
            if existing:
                if digest(wav)!=existing['wav_sha256']:raise ValueError('Existing WAV changed')
                if existing.get('model_pack')!=pack:raise ValueError('Model pack changed; use a new output folder')
                continue
            base=dict(model_id=args.model,case_id=c['id'],text=c['text'],seed=seed,condition=args.condition,
                      instruction=instruction,platform=platform_id,file=wav.name,threads=4,
                      speaker='sohee' if args.model==CUSTOM else None,model_pack=pack,
                      reference_audio_sha256=reference_sha,
                      streaming_first_chunk_ms=None,first_output_ms=None,physical_speaker_first_sound_ms=None,
                      gpu_utilization=None,device_temperature_c=None,human_ratings=None)
            if loaded is not None:
                base.update(model_init_ms=model_init_ms,init_this_request_ms=model_init_ms if python_calls==0 else 0,model_reused=python_calls>0,generation_index=python_calls,config_only_initialization=args.cosy_config_only_init)
                python_calls+=1
            start=time.perf_counter()
            try:
                if args.model in [CUSTOM,DESIGN]:
                    talker='qwen-talker-1.7b-customvoice-f16-stable.gguf' if args.model==CUSTOM else 'qwen-talker-1.7b-voicedesign-f16-stable.gguf'
                    cmd=[str(args.binary.resolve()),'-m',str(args.models.resolve()),'--model-name',talker,'-t',c['text'],'-l','ko','--instruction',instruction,'--seed',str(seed),'-j','4','--max-tokens','1024','--temperature','0.9','--top-k','50','--top-p','1.0','--repetition-penalty','1.05','-o',str(wav.resolve())]
                    if args.model==CUSTOM:cmd+=['--speaker','sohee']
                    if platform.system()=='Linux' and Path('/usr/bin/time').is_file():cmd=['/usr/bin/time','-f','CHLOE_OS_METRICS %M %U %S',*cmd]
                    run=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=args.timeout)
                    log=run.stdout+run.stderr;(args.output/(key+'.log')).write_text(log,encoding='utf-8')
                    if run.returncode:raise RuntimeError(f'native exit {run.returncode}; see local log')
                    def timing(pattern):
                        m=re.search(pattern,log);return int(m.group(1)) if m else None
                    generation=timing(r'Total:\s+(\d+) ms')
                    base.update(model_init_ms=timing(r'All models loaded in (\d+) ms'),generation_ms=generation,
                        code_generation_ms=timing(r'Code generation:\s+(\d+) ms'),audio_decode_ms=timing(r'Vocoder decode:\s+(\d+) ms'),
                        native_binary_sha256=digest(args.binary),runtime_commit=RUNTIME,precision='f16-f32-cp-down',
                        sampling=dict(temperature=.9,top_k=50,top_p=1.0,repetition_penalty=1.05,max_audio_tokens=1024))
                    if 'maximum number of tokens' in log.lower():raise RuntimeError('Token cap reached')
                elif args.model==VOX and args.binary:
                    cmd=[str(args.binary.resolve()),str((args.models/'VoxCPM2-BaseLM-F16.gguf').resolve()),str((args.models/'VoxCPM2-Acoustic-F16.gguf').resolve()),f'({instruction}){c["text"]}',str(seed),str(wav.resolve())]
                    if platform.system()=='Linux' and Path('/usr/bin/time').is_file():cmd=['/usr/bin/time','-f','CHLOE_OS_METRICS %M %U %S',*cmd]
                    run=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=args.timeout)
                    log=run.stdout+run.stderr;(args.output/(key+'.log')).write_text(log,encoding='utf-8')
                    if run.returncode:raise RuntimeError(f'VoxCPM2 exit {run.returncode}; see local log')
                    match=re.search(r'CHLOE_METRICS (\{[^\n]+\})',log)
                    if not match:raise RuntimeError('Missing VoxCPM2 metrics')
                    base.update(json.loads(match.group(1)))
                    base.update(precision='F16 BaseLM + F16 Acoustic',runtime_commit='e0eca9d8f57ac8f5a5ad6191a8007b93436c1e71',native_binary_sha256=digest(args.binary),cfg_value=2.0,inference_timesteps=10,temperature=1.0,max_steps=200)
                elif args.model==VOX:
                    import soundfile as sf
                    result=loaded.generate(text=f'({instruction}){c["text"]}',cfg_value=2.0,inference_timesteps=10,seed=seed)
                    sf.write(wav,result,loaded.tts_model.sample_rate,subtype='PCM_16');base.update(generation_ms=(time.perf_counter()-start)*1000,cfg_value=2.0,inference_timesteps=10,precision='upstream-default-record-dtype-before-comparing')
                else:
                    import random,torch,numpy as np,soundfile as sf
                    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
                    if args.condition=='optimized':
                        chunks=list(loaded.inference_instruct2(c['text'],'You are a helpful assistant. '+instruction+'<|endofprompt|>',str(args.reference_wav),stream=False,text_frontend=False))
                    else:
                        chunks=list(loaded.inference_zero_shot(c['text'],'You are a helpful assistant.<|endofprompt|>'+args.reference_transcript,str(args.reference_wav),stream=False,text_frontend=False))
                    audio=torch.cat([r['tts_speech'] for r in chunks],dim=1).squeeze().cpu().numpy()
                    if not np.isfinite(audio).all() or not np.any(audio):raise RuntimeError('Nonfinite or silent CosyVoice PCM')
                    sf.write(wav,audio,loaded.sample_rate,subtype='PCM_16');base.update(generation_ms=(time.perf_counter()-start)*1000,precision='FP32 CPU requested',instruction_applied=args.condition=='optimized',text_frontend=False)
                if args.binary:
                    operating_system=re.search(r'CHLOE_OS_METRICS (\d+) ([\d.]+) ([\d.]+)',log)
                    if operating_system:base.update(peak_rss_kib=int(operating_system.group(1)),process_cpu_ms=(float(operating_system.group(2))+float(operating_system.group(3)))*1000,rss_method='Linux GNU time ru_maxrss; not Android PSS')
                base.update(stats(wav));base['process_wall_ms']=(time.perf_counter()-start)*1000
                base['rtf']=base['generation_ms']/(base['audio_seconds']*1000) if base.get('generation_ms') is not None else None
                base['wav_sha256']=digest(wav)
                if wav.name in transcriptions:base['asr_auxiliary']=cer(c['text'],transcriptions[wav.name])
                report['clips'].append(base);print(c['id'],seed,'ok',round(base['audio_seconds'],2),flush=True)
            except Exception as e:
                if isinstance(e,subprocess.TimeoutExpired):
                    def decoded(value):return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
                    (args.output/(key+'.log')).write_text(decoded(e.stdout)+decoded(e.stderr),encoding='utf-8')
                report['failures'].append(dict(model_id=args.model,case_id=c['id'],seed=seed,error=str(e)));wav.unlink(missing_ok=True);print(c['id'],seed,'FAILED',str(e),flush=True)
            atomic(manifest_file,report)
    atomic(manifest_file,report)

if __name__=='__main__':main()
