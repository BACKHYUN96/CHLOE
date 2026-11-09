#!/usr/bin/env python3
"""Generate 12 original Korean sentences in paired styles; human listening remains required."""
import argparse
import csv
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import wave
from compare_breath_styles import RUNTIME, TALKER, TOKENIZER, SAMPLING, audio_stats, digest

BREATH = '호흡은 필요한 의미 경계에서만 자연스럽게 사용하고, 매 문장 앞의 과장된 들숨은 반복하지 마세요.'
GROUPS = [
 ('daily', '일상', '친한 친구에게 이야기하듯 편안하고 담백하게 말해 주세요. 감정을 과장하지 말고 부드러운 대화 리듬을 유지해 주세요.', [
  '응, 좋아. 오늘은 뭐 하고 싶어?', '오늘 하루는 어땠어? 무슨 일 있었어?', '나는 괜찮아. 우리 조금만 더 이야기하자.']),
 ('surprise', '놀람과 호기심', '친한 친구의 뜻밖의 이야기에 가볍게 놀라며 호기심 있게 반응해 주세요. 질문의 억양은 살리되 소리를 지르거나 연극처럼 과장하지 마세요.', [
  '어, 진짜? 그래서 어떻게 됐어?', '와, 그걸 벌써 끝냈어? 생각보다 훨씬 빠른데?', '잠깐, 그럼 네가 직접 만든 거야? 어떻게 했어?']),
 ('empathy', '공감', '상대의 이야기를 받아주듯 따뜻하고 조심스럽게 말해 주세요. 의미 사이에 여유를 주되, 울먹이거나 지나치게 처지는 말투는 피해주세요.', [
  '아, 많이 힘들었겠다. 천천히 이야기해도 괜찮아.', '오늘은 좀 쉬어도 돼. 지금까지 충분히 애썼잖아.', '그랬구나. 괜찮다면 무슨 일이 있었는지 들려줄래?']),
 ('explanation', '설명', '상대가 따라 하기 쉽도록 차분하고 또렷하게 설명해 주세요. 단계와 핵심 단어를 자연스럽게 구분하고, 안내 방송처럼 딱딱하게 읽지 마세요.', [
  '먼저 앱을 열고, 아래쪽 설정을 눌러 주세요.', '두 파일을 차례로 들어보세요. 더 편안하게 들리는 쪽을 골라 주시면 돼요.', '생성 시간은 소리를 만드는 데 걸린 시간이에요. 오디오 길이와 비교하면 속도를 알 수 있어요.'])]


def plan():
    cases = []
    for group, label, direction, texts in GROUPS:
        for n, text in enumerate(texts, 1):
            cases.append(dict(id=f'{group}_{n:02}', group=label, text=text, instructions={
                'A': '차분하고 다정하게, ' + BREATH,
                'B': direction + ' ' + BREATH}))
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('artifacts/situation-study-01'))
    a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()): p.error('Choose an empty output folder')
    cases=plan()
    assert len(cases)==12
    assert all(len(c['text'])<=240 and all(len(i)<=240 for i in c['instructions'].values()) for c in cases)
    manifest=json.loads((a.models/'model-pack.json').read_text())
    if manifest['model_id']!='Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice' or manifest['runtime_commit']!=RUNTIME:
        p.error('Expected pinned 1.7B CustomVoice pack')
    if {f['name'] for f in manifest['files']}!={TALKER,TOKENIZER}: p.error('Unexpected model files')
    for f in manifest['files']:
        path=a.models/f['name']
        if path.stat().st_size!=f['size'] or digest(path)!=f['sha256']: p.error('Model integrity mismatch')
    a.output.mkdir(parents=True,exist_ok=True)
    report=dict(study='situation-study-01', device_test=False, perceptual_evaluation='pending',
        model_pack=manifest, source_runtime=RUNTIME, native_binary_sha256=digest(a.binary),
        host=platform.platform(), seed=42, threads=4, sampling=SAMPLING, untouched_pcm=True,
        common_breath_instruction=BREATH, cases=cases, clips=[])
    for c in cases:
        for style,instruction in c['instructions'].items():
            clip_id=c['id']+'_'+style
            wav=a.output/(clip_id+'.wav')
            cmd=[str(a.binary.resolve()),'-m',str(a.models.resolve()),'--model-name',TALKER,
                 '--speaker','sohee','-l','ko','--seed','42','-j','4','--max-tokens','1024',
                 '--temperature','0.9','--top-k','50','--top-p','1.0','--repetition-penalty','1.05',
                 '-t',c['text'],'--instruction',instruction,'-o',str(wav.resolve())]
            item=dict(clip_id=clip_id,case_id=c['id'],style=style,status='runtime_error')
            start=time.perf_counter()
            try:
                run=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=240)
                log=run.stdout+run.stderr
                (a.output/(clip_id+'.log')).write_text(log,encoding='utf-8')
                item.update(exit_code=run.returncode,process_wall_ms=(time.perf_counter()-start)*1000)
                if run.returncode==0:
                    item.update(audio_stats(wav))
                    for key,label in [('native_total_ms','Total'),('code_generation_ms','Code generation'),('decode_ms','Vocoder decode')]:
                        m=re.search(rf'{label}:\s+(\d+) ms',log)
                        if m:item[key]=int(m[1])
                    item['status']='generated_unrated' if item['pcm_rms']>0 and item['samples']<1024*1920 else 'failed_audio'
                    if 'native_total_ms' in item:item['rtf']=item['native_total_ms']/(item['audio_seconds']*1000)
                    item['wav_sha256']=digest(wav)
                    m=re.search(r'RSS peak:\s+(.+)',log)
                    if m:item['rss_peak_display']=m[1].strip()
            except (subprocess.TimeoutExpired,OSError,ValueError,EOFError,wave.Error) as e:
                item['error']=type(e).__name__
            report['clips'].append(item)
            (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(clip_id,item['status'],flush=True)
    with (a.output/'listening.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['clip_id','발음1-5','억양1-5','리듬1-5','감정적절성1-5','문두들숨0없음1약함2뚜렷','단어누락추가','첫음절손상','메모'])
        for c in report['clips']:w.writerow([c['clip_id']]+['']*8)
    raise SystemExit(0 if all(c['status']=='generated_unrated' for c in report['clips']) else 1)

if __name__=='__main__':main()
