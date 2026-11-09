#!/usr/bin/env python3
"""Optional local faster-whisper CER. No downloads or cloud transcription calls."""
import argparse,json,os,time
from pathlib import Path
from tts_comparison import cer,digest,atomic

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True,help='Already prepared local CTranslate2 Whisper directory')
    p.add_argument('--samples',type=Path,required=True,help='Folder containing comparison-manifest.json and WAVs')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--attach',action='store_true',help='Also attach auxiliary measurements to the local manifest; audio is unchanged')
    a=p.parse_args()
    if not a.model.is_dir() or not (a.model/'model.bin').is_file():p.error('Local model.bin required; this command never downloads models')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from faster_whisper import WhisperModel
    model=WhisperModel(str(a.model.resolve()),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    manifest=json.loads((a.samples/'comparison-manifest.json').read_text(encoding='utf-8'))
    report=dict(schema=1,asr_model_sha256=digest(a.model/'model.bin'),asr_compute_type='int8',language='ko',beam_size=5,
                auxiliary_only=True,human_naturalness_score=None,clips=[])
    root=a.samples.resolve()
    for clip in manifest['clips']:
        wav=(root/clip['file']).resolve()
        if wav.parent!=root or wav.suffix!='.wav':raise ValueError('Nonlocal WAV path rejected')
        if digest(wav)!=clip['wav_sha256']:raise ValueError('WAV changed')
        start=time.perf_counter();segments,_=model.transcribe(str(wav),language='ko',beam_size=5,vad_filter=False,condition_on_previous_text=False,temperature=0.0)
        text=''.join(segment.text for segment in segments)
        report['clips'].append(dict(wav_sha256=clip['wav_sha256'],case_id=clip['case_id'],model_id=clip['model_id'],seed=clip['seed'],hypothesis=text,measurement=cer(clip['text'],text),asr_ms=(time.perf_counter()-start)*1000))
        if a.attach:clip['asr_auxiliary']=report['clips'][-1]
        atomic(a.output,report)
        if a.attach:atomic(a.samples/'comparison-manifest.json',manifest)
    atomic(a.output,report)

if __name__=='__main__':main()
