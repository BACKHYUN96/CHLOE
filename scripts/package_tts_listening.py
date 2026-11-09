#!/usr/bin/env python3
"""Create a local listening ZIP. Never upload recordings or include model weights."""
import argparse, json, struct, zipfile
from pathlib import Path
from tts_comparison import ROOT, CUSTOM, DESIGN, VOX, COSY, digest

MODELS={'custom':CUSTOM,'design':DESIGN,'vox':VOX,'cosy':COSY}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=ROOT/'artifacts')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/CHLOE-TTS-comparison-listening-0.1.0-alpha7.zip')
    parser.add_argument('--reference-wav',type=Path,help='Optional owned synthetic reference, stored separately from test clips')
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; choose another filename')
    cases={r['id']:r['text'] for r in json.loads((ROOT/'app/src/main/assets/tts-comparison-cases.json').read_text())['cases']}
    files={};rows=[];checks=[]
    for prefix,condition,expected in [('tts-comparison-','controlled',60),('tts-optimized-','optimized',12)]:
        for name,model in MODELS.items():
            folder=args.artifacts/(prefix+name);report=json.loads((folder/'comparison-manifest.json').read_text())
            clips=report['clips']
            if len(clips)!=expected or report.get('failures') or report.get('initialization_error'):raise ValueError('Incomplete run: '+folder.name)
            keys=set()
            for row in clips:
                filename=row['file'];path=folder/filename
                if Path(filename).name!=filename or not filename.endswith('.wav') or filename in files:raise ValueError('Duplicate/nonflat WAV')
                if row['model_id']!=model or row['condition']!=condition or row['text']!=cases[row['case_id']] or row['seed'] not in [42,43,44]:raise ValueError('Wrong conditions')
                key=(row['case_id'],row['seed'])
                if key in keys:raise ValueError('Repeated case/seed')
                keys.add(key)
                sha=digest(path)
                if sha!=row['wav_sha256']:raise ValueError('Changed WAV')
                h=path.read_bytes()[:44]
                if h[:4]!=b'RIFF' or h[8:16]!=b'WAVEfmt ' or h[36:40]!=b'data' or struct.unpack_from('<I',h,16)[0]!=16 or struct.unpack_from('<HH',h,20)!=(1,1) or struct.unpack_from('<H',h,34)[0]!=16 or struct.unpack_from('<I',h,24)[0] not in [16000,24000,48000] or struct.unpack_from('<I',h,40)[0]+44!=path.stat().st_size:raise ValueError('Noncanonical PCM16 WAV')
                files[filename]=path;rows.append(row);checks.append(sha+'  '+filename)
    manifest=json.dumps(dict(schema=1,clips=rows,device_test=False,human_ratings=None),ensure_ascii=False,indent=2).encode()
    if len(manifest)>4_000_000 or sum(p.stat().st_size for p in files.values())>400_000_000:raise ValueError('Pack exceeds Android importer limits')
    readme='''CHLOE TTS Lab alpha7 · 오프라인 청취 묶음

PC Linux CPU 생성 결과: 공통 240개 + 별도 조정 48개. 폰 생성 결과가 아닙니다.
1. ZIP을 스마트폰 내부 저장소의 한 폴더에 압축 해제합니다.
2. alpha7 Performance APK → TTS Lab → PC 샘플 폴더 가져오기에서 그 폴더를 고릅니다.
3. A/B 블라인드 청취 → 문장 → 공통 조건/모델별 조정 → 무작위 A/B 선택.
4. A/B를 듣고 6항목 점수와 쉼·종결·감정 메모를 남긴 후 정답을 공개합니다.
5. 청취 평가 JSON을 내보낼 수 있습니다. 추론 모델 없이도 이 샘플들을 들을 수 있습니다.

모델 이름은 앱에서 공개 전 숨깁니다. manifest는 출처를 포함하므로 블라인드 평가 전에 읽지 않는 편이 좋습니다.
ko12/ko13은 길이 편차가 큰 사례입니다. 이상한 파일도 삭제·편집하지 않고 보존했습니다.
동일 seed의 모델은 동일 난수를 뜻하지 않습니다. 서로 다른 conditioning/runtime이며 CER은 보조 지표입니다.
WAV는 원본 속도·음높이·무음 그대로이며 리샘플링/볼륨 정규화를 하지 않았습니다.
실제 인물·통화 녹음·모델 가중치는 없습니다. reference 폴더가 있으면 이번 실험의 새 합성 참조입니다.
이 스크립트는 파일을 외부로 업로드하지 않습니다.
'''
    args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('comparison-manifest.json',manifest)
            archive.writestr('README.ko.txt',readme)
            for name,path in files.items():archive.write(path,name)
            if args.reference_wav:
                reference=json.loads((ROOT/'docs/validation/tts-comparison/synthetic-reference.json').read_text())
                if digest(args.reference_wav)!=reference['wav_sha256']:raise ValueError('Unexpected synthetic reference')
                archive.write(args.reference_wav,'reference/synthetic-reference.wav')
                archive.writestr('reference/synthetic-reference.json',json.dumps(reference,ensure_ascii=False,indent=2))
            archive.writestr('SHA256SUMS.txt','\n'.join(checks)+'\n')
        with zipfile.ZipFile(args.output) as archive:
            if archive.testzip() is not None:raise ValueError('ZIP CRC failed')
    except BaseException:
        args.output.unlink(missing_ok=True);raise
    print(json.dumps(dict(path=str(args.output),benchmark_wavs=len(rows),bytes=args.output.stat().st_size,sha256=digest(args.output)),ensure_ascii=False))

if __name__=='__main__':main()
