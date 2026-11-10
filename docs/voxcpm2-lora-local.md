# VoxCPM2 LoRA · 사용자 PC에서 무료 비상업 실험

## 현재 상태

사용자가 알려준 GPU는 **RTX 4070 SUPER / VRAM 12GB**다. PC RAM·저장 공간·WSL 설치 여부는 미확인이다. 현재 Codex 실행기는 별도 Linux CPU 클라우드이고 PC 연결 권한/주소는 없다. 클라우드 GPU 임대·외부 음성 업로드·결제는 하지 않았다.

- 실험 브랜치 `experiment/voxcpm2-lora`, 기준은 기존 비교 PR #7의 `1cce44491804fd2e52ed1f9f7c3447d9a3b0f555`. 기존 Android/Sohee 코드는 수정하지 않는다.
- 공식 VoxCPM2 Python 학습/추론 API와 코드를 읽어 도구를 작성했다. 정확한 revision은 `experiments/voxcpm2-lora/lock.json`에 고정했다.
- 데이터 준비·중복/평가문장 분리·16kHz 변환·설정 생성은 합성 테스트 fixture로 검증했다. 실제 KSS 음성 수집·사람 청취·Python 원본 추론·학습은 아직 실행하지 않았다.
- 이전 GGUF/C++ 결과는 공식 Python 원본 모델의 품질 검증이 아니다. 기존 GGUF는 Python 학습용 checkpoint로 사용할 수 없다.
- **12GB 학습 성공을 보장하지 않는다.** LoRA는 학습할 파라미터를 줄이지만 기반 가중치·활성값·KV cache는 여전히 필요하다. upstream training=True는 기반 파라미터를 일괄 BF16으로 바꾸지 않으며 forward에는 BF16 autocast를 사용한다. 기본 배치 2 / rank 32 / LM+DiT를 그대로 실행하지 않는다.

## 무료 한국어 여성 데이터 선택

**KSS (Korean Single Speaker Speech Dataset)**: Kyubyong Park가 한국어 TTS 목적으로 공개한 여성 전문 성우 1명의 녹음·대본, 총 12,853개/약 12시간. 원본은 Kaggle, 사용할 공개 미러는 Bingsu/KSS_Dataset이다.

- 원본: https://www.kaggle.com/datasets/bryanpark/korean-single-speaker-speech-dataset
- 미러 설명·저작자 고지: https://huggingface.co/datasets/Bingsu/KSS_Dataset
- 조건: **CC BY-NC-SA 4.0**, 출처 표시·비상업·동일조건 적용. 비용은 없지만 무제한/퍼블릭도메인 데이터가 아니다.
- 현재 개인 전용 비상업 실험 범위에서 준비한다. 모델 자체 Apache-2.0가 데이터의 NC/SA 조건을 없애지 않는다. 학습 adapter의 공개·상업화는 별도 검토 전 진행하지 않는다.
- 배포 설명에 TTS 학습용 공개와 여성 성우 녹음이 명시돼 있다. 성우의 별도 서명 동의서를 확보·검토했다고 주장하지 않는다. 제한 없는 이용이나 특정 서비스 성우 모방을 보장하는 자료로 취급하지 않는다.
- 낭독 데이터이며 다정함·놀람 등 감정 라벨이 없다. 감정 라벨을 임의 생성하지 않는다. 첫 목표는 **원본 Python 경로 검증 + 한국어 여성 화자 적응 + 낭독체가 강해지는지 평가**다. 친구 같은 위로 말투 개선은 아직 가설이다.

## 로컬 설치 (Windows + WSL2 Ubuntu 권장)

아래는 사용자 PC에서 실행할 제안 recipe다. 여기서 원격으로 실행한 설치가 아니다. Windows NVIDIA 드라이버와 WSL GPU 지원을 먼저 확인한다. WSL이 없다면 관리자 PowerShell에서 `wsl --install -d Ubuntu-24.04` 후 재부팅/Ubuntu 초기 설정을 한다. WSL Ubuntu에서 `nvidia-smi`로 4070 SUPER가 보이는지 확인한다. GPU passthrough가 없으면 학습부터 시작하지 않는다.

RAM은 32GB 이상, Linux 파일시스템 여유 공간은 **60GB 이상을 준비 예산**으로 권장한다. 최소 요구량 실측이 아니다. WSL의 Linux 홈 아래에 프로젝트와 가중치를 두고 모델/원음/adapter를 Git에 추가하지 않는다.

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential git ffmpeg libsndfile1
# CHLOE가 없다면 먼저 clone. 이 브랜치는 기존 모델 비교 PR 위에 있다.
git clone --recursive -b experiment/voxcpm2-lora https://github.com/BACKHYUN96/CHLOE.git
cd CHLOE
python3 -m venv .venv-vox
source .venv-vox/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r scripts/voxcpm2-local-requirements.txt
mkdir -p artifacts/voxcpm2-local
# 고정 공식 코드. 자동 최신 업데이트는 하지 않는다.
git clone https://github.com/OpenBMB/VoxCPM.git artifacts/voxcpm2-local/upstream
git -C artifacts/voxcpm2-local/upstream checkout --detach 300e4260b509066151d623dc9c0aa922cf82232b
python -m pip install -e artifacts/voxcpm2-local/upstream
python -m pip freeze > artifacts/voxcpm2-local/installed-freeze.txt
python scripts/voxcpm2_lab.py probe --output artifacts/voxcpm2-local/pc-probe.json
```

CUDA wheel/드라이버 호환성과 upstream 의존성 전체는 PC에서 검증해야 한다. 고정 requirements는 준비안이며 설치 성공을 의미하지 않는다. torchcodec가 FFmpeg 공유 라이브러리를 찾지 못하면 그 오류부터 해결한다. GPU 드라이버 설치/업데이트는 PC 상태를 확인한 후 진행한다.

## 모델과 데이터 다운로드 (준비 때만 인터넷 사용)

공식 Python 원본 모델은 talker GGUF와 다르다. 필요한 파일만 고정 revision으로 받는다. denoiser 추가 모델은 받지 않는다.

```bash
hf download openbmb/VoxCPM2 --revision 7936080b41163874f38610f46f438e2c0757f9fd \
  --include model.safetensors audiovae.pth config.json tokenizer.json tokenizer_config.json special_tokens_map.json README.md \
  --local-dir artifacts/voxcpm2-local/model
# KSS 조건을 읽은 뒤, PC에서만 스트리밍으로 짧은 pilot subset 준비
python scripts/voxcpm2_lab.py prepare-kss --accept-noncommercial-kss \
  --output artifacts/voxcpm2-local/kss-pilot --train-minutes 10 --val-minutes 2
```

다운로드 비용은 없으며 네트워크/저장 공간 사용은 있다. HF streaming이 선택량보다 큰 parquet 범위를 읽을 수 있으므로 네트워크 사용량을 12분 WAV 크기라고 보장하지 않는다. 출력 폴더가 있으면 덮어쓰지 않고 중단한다.

원본 WAV와 16kHz PCM 사본을 모두 보관한다. 음높이·속도 변경·무음 절삭·볼륨 정규화를 하지 않는다. VoxCPM2 encoder 입력은 16kHz, decoder 출력은 48kHz다. 짧은 1.5~5초 녹음만 고르고 무음/비유한값/과한 clipping을 거부한다. 대본은 expanded_script를 사용한다. 문장 정규화 hash로 train/validation을 분리하고 동일 대본·원음 중복과 기존 20문장/사용자 위로 대사 누출을 막는다. train의 고정 참조 1개를 약 40%에 붙이며 validation에서도 train 참조만 쓴다. source revision·SHA·선택 수·길이·출처는 dataset-report.json/ATTRIBUTION.txt에 남긴다.

## 반드시 원본부터 확인

```bash
python scripts/voxcpm2_compare.py --source artifacts/voxcpm2-local/upstream \
  --model artifacts/voxcpm2-local/model --data artifacts/voxcpm2-local/kss-pilot \
  --output artifacts/voxcpm2-local/baseline
```

기본 4문장 × seed 42/43/44로 공식 Python 원본을 먼저 생성한다. 참조는 KSS train 녹음이다. 불필요한 긴 description을 넣지 않고 normalize/denoise/자동 retry를 끈다. WAV를 직접 들어 발음·반복·긴 쉼이 정상인지 확인한다. 원본이 이상하면 학습으로 덮지 말고 원인을 먼저 조사한다. 이 도구는 CUDA가 없으면 실행을 거부하며 유료/원격 서버로 대체하지 않는다.

## 12GB용 후보: 1 optimizer step → 짧은 pilot

```bash
python scripts/voxcpm2_lab.py plan --source artifacts/voxcpm2-local/upstream \
  --model artifacts/voxcpm2-local/model --data artifacts/voxcpm2-local/kss-pilot \
  --output artifacts/voxcpm2-local/smoke --steps 1
python scripts/voxcpm2_lab.py train --source artifacts/voxcpm2-local/upstream \
  --run artifacts/voxcpm2-local/smoke
```

1-step은 accumulation 1·validation 생략으로 첫 optimizer update만 검증한다. pilot 설정은 **batch 1, accumulation 4, LM-only LoRA rank 8, DiT/프로젝션 동결, max_batch_tokens 512**. 공식 설정과 다른 실험 후보이며 최고의 음질 설정으로 확정한 것이 아니다. 음성 모델 가중치를 저비트로 바꾸지 않는다. LM-only라 감정/운율 개선 폭이 제한될 수 있다. 원본 config와 runtime commit을 고정한다. run-plan.json은 실행 전 계획, execution.json과 train-console.log는 실제 실행 상태다.

첫 step도 OOM이면 종료하고 로그를 확인한다. rank/문장 길이를 줄이는 것만으로 기반 가중치 메모리 문제가 해결된다고 가정하지 않는다. 자동 QLoRA/CPU offload/gradient checkpointing을 지원한다고 보고하지 않는다. 기존 config를 고쳐 같은 폴더에서 재실행하면 upstream이 checkpoint를 자동 재개하므로, 다른 설정은 반드시 **새 run 폴더**를 사용한다.

첫 step 성공과 메모리 확인 후 `plan ... --output artifacts/voxcpm2-local/pilot-400 --steps 400`으로 새 계획을 만든다. 아직 400-step 품질 개선은 미검증이다. 100/200/300/400 checkpoint를 비교하고 validation loss만으로 최종 모델을 고르지 않는다.

## 학습 전후 비교

```bash
python scripts/voxcpm2_compare.py --source artifacts/voxcpm2-local/upstream \
  --model artifacts/voxcpm2-local/model --data artifacts/voxcpm2-local/kss-pilot \
  --checkpoint artifacts/voxcpm2-local/pilot-400/checkpoints/step_0000400 \
  --all-cases --output artifacts/voxcpm2-local/comparison-400
```

checkpoint 폴더명은 trainer가 실제 생성한 것을 확인하고 대입한다. lora_config.json 및 lora_weights 파일이 있는 디렉터리를 지정한다. 같은 객체에서 adapter off/on, 같은 KSS 참조·문장·seed로 비교해 두 개의 큰 모델을 동시에 올리지 않는다. load_lora에서 누락/건너뛴 키가 있으면 성공으로 처리하지 않는다. 결과는 comparison.json과 개별 WAV이며 GPU peak allocated/reserved, 시간/RTF/오류를 기록한다. 출력 파일명은 UUID지만 mapping JSON에는 조건이 있으므로 평가 전에 보지 않는 편이 좋다.

기존 Android TTS Lab은 서로 다른 model_id끼리만 블라인드 비교한다. **같은 VoxCPM2의 adapter off/on을 서로 다른 모델 ID로 위장해 가져오지 않는다.** 이번 파일은 PC에서 같은 볼륨으로 조건을 가리고 청취해 여섯 항목을 평가한다. Android adapter 통합과 동일 모델 A/B UI는 이번 범위에 없다.

채택 조건: 학습에 없던 문장에서 발음·종결·리듬·따뜻함이 반복해서 좋아지고, 과한 낭독체/원문 반복/음색 붕괴가 없어야 한다. 아직 청취 점수·성능·학습 완료 체크포인트·업데이트 APK는 없다. 기존 Sohee 및 alpha7 APK는 그대로다.
