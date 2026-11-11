# 로컬 Codex 작업 지시: CHLOE 한국어 대화 LLM 학습

이 문서를 로컬 Codex에게 읽히고 실제 PC에서 진행한다. 현재 자료는 **학습 인수인계/사전 점검**이다. GPU 학습·Qwen3.5 QLoRA·Android 변환을 클라우드에서 성공시켰다는 결과가 아니다. 실행 가능한 trainer는 로컬 호환성 조사 후 구현하는 작업이다.

## 목표와 보존 범위

- Windows PC / RTX 4070 SUPER 12GB. RAM·여유 저장 공간·WSL2·드라이버는 현장에서 확인한다.
- 우선 Qwen3.5-2B 원본으로 소규모 대화 SFT/QLoRA 가능성을 검증한다. 4B는 2B smoke 성공 및 메모리 예산 확인 후 별도 비교한다. 12GB 성공을 보장하지 않는다.
- 학습 대상은 반말/존댓말 일관성, 자연스러운 친구·비서 응답, 자기소개, 내부 규칙을 대사로 읊지 않는 행동이다. TTS 억양 학습과 다르다. 학습이 prefill 속도를 해결한다고 주장하지 않는다.
- 기존 Android 앱, Sohee TTS, GGUF, 사용자 파일을 변경/삭제하지 않는다. 학습 모델은 별도 파일로 비교한다.
- 이전 음성 학습은 docs/voxcpm2-lora-local.md와 scripts/voxcpm2_lab.py 참조. 이번 LLM 학습과 데이터/가상환경을 공유하지 않는다.

## 로컬 Codex에게 맡기는 정확한 작업

1. 루트 AGENTS.md와 이 문서, docs/conversation-engine.md를 읽고 git status 및 원격 main/관련 PR 상태 확인. 사용자 변경 보존. `experiment/local-llm-training` 같은 새 브랜치로 진행한다. 이 문서가 main에 없으면 배포된 docs/local-codex-training 브랜치에서 시작한다. 자동 병합하지 않는다.
2. 아래 preflight를 실행한다. GPU가 WSL에서 보이고 CUDA PyTorch가 사용 가능한지 직접 확인한다. 보고서에 날짜/환경/명령/반환 코드 기록. 비밀번호나 토큰을 채팅·로그에 남기지 않는다. 관리자 작업/재부팅은 사용자에게 안내한다. WSL 안에 Linux NVIDIA 디스플레이 드라이버를 설치하지 않는다.
3. 공식 모델 카드와 학습 도구를 직접 읽는다: https://huggingface.co/Qwen/Qwen3.5-2B , https://github.com/huggingface/transformers , https://github.com/huggingface/peft , https://github.com/huggingface/trl , https://github.com/ggml-org/llama.cpp . Qwen3.5 dense/hybrid architecture 학습 지원, text-only 경로, chat template/thinking=false, assistant-only loss와 QLoRA 지원을 검증한다. Qwen3와 Qwen3.5를 혼동하지 않는다.
4. Transformers/PEFT/TRL/bitsandbytes/PyTorch 및 CUDA 조합을 실제 import/모델 로드/forward로 검증하고 requirements lock과 모델 revision/SHA/license를 기록한다. 최신 버전 무조건 설치나 기존 환경 덮어쓰기를 하지 않는다. 모델 코드의 remote-code 실행이 필요하면 출처를 검토한다. 아래 venv만 사용한다.
5. 원본 GGUF를 학습하지 않는다. 원본 checkpoint + tokenizer를 준비하고 소량의 권리 확인된 한국어 대화 데이터를 사용한다. 통화녹음/개인 대화/외부 성우 음성은 자동 수집·업로드하지 않는다. 합성 대화는 합성이라고 표시하고 사람이 검토한다. 승인되지 않은 샘플을 좋은 답변으로 확정하지 않는다.
6. 평가 질문을 먼저 고정하고 train/validation/test를 대화 단위로 분리한다. 질문을 조금만 바꾼 중복도 분리한다. 실제 개인정보 대신 가상 이름 사용. 아래 데이터 계약을 따른다.
7. `training/scripts/train.py`, `evaluate.py`, `export.py`와 고정 requirements를 실제 선택한 API에 맞춰 구현한다. 목표 명령은 아래 계약을 따른다. 처음에는 최대 10 step / microbatch1 / gradient checkpointing / 짧은 context512 / LoRA rank8 정도를 후보로 삼는다. target module은 모델의 실제 named_modules를 검사해서 선택하며 전체 linear 일괄 적용하지 않는다. OOM이면 batch/context/target 범위를 줄이고, 묵시적인 CPU offload나 모델 변경은 결과에 기록한다.
8. loss가 유한하고 adapter가 저장되며 재로드 후 추론 가능함을 확인한다. trainable parameter 수·학습 시간·최대 GPU allocated/reserved·오류를 기록. 10 step 성공은 말투 개선 증거가 아니다. 필요 없는 대형 모델을 동시에 받지 않는다.
9. 원본/adapter에 동일 평가 입력·생성 조건·seed를 적용한다. 한국어 자연스러움, 말투 일관성, 자기소개, 과잉 공감, 지시문 노출, 문맥 기억, 정직성, JSON 유효성을 따로 평가한다. style enum/tts_instruction 빈 문자열 등 현재 앱 계약과 비교한다. 자동 점수만으로 승격하지 않는다. 질문 50개 이상을 고정하고 사람 검토를 남긴다.
10. 품질 이득이 있을 때만 더 긴 학습을 진행한다. adapter를 기반 모델과 merge하는 과정은 새 디렉터리에서 수행하고 GGUF 변환→Q4_K_M 후 다시 평가한다. llama.cpp Qwen3.5 지원과 CHLOE pinned runtime 호환성을 확인한다. 모바일 모델 importer는 현재 크기/SHA allowlist가 있으므로 새 모델을 그대로 가져올 수 있다고 가정하지 않는다. 새 모델 ID/해시 등록은 별도 Android PR로 준비한다.
11. docs/validation/local-llm-training-report.md를 작성해 재현 명령/버전/학습 여부/비교/남은 작업을 기록하고 코드·비민감 보고서만 PR 생성. main 자동 병합 없음. 실패 결과도 성공으로 표시하지 않는다.

## PC에서 시작하는 명령

PowerShell (아직 clone하지 않았다면; 기존 폴더 덮어쓰기 금지):

```powershell
git clone --branch docs/local-codex-training https://github.com/BACKHYUN96/CHLOE.git CHLOE-training
cd CHLOE-training
wsl --status
wsl --list --verbose
nvidia-smi
```

WSL2 Ubuntu가 없다면 `wsl --install -d Ubuntu-24.04`를 사용자 관리자 PowerShell에서 실행하고 필요 시 재부팅한다. 기존 WSL 배포판을 삭제하거나 재설치하지 않는다. 학습 파일은 WSL의 Linux 홈 아래에 두는 것을 권장한다.

WSL Ubuntu (Python3/venv가 설치된 환경에서):

```bash
# 이미 WSL에 저장소가 있으면 그 경로 사용. 없을 때만 실행.
git clone --branch docs/local-codex-training https://github.com/BACKHYUN96/CHLOE.git ~/CHLOE-training
cd ~/CHLOE-training
git switch -c experiment/local-llm-training
python3 training/scripts/preflight.py --output artifacts/llm-training/preflight.json
python3 -m venv .venv-llm
source .venv-llm/bin/activate
# 의존성 설치는 로컬 Codex가 호환 조합을 확인하고 lock 작성 후 수행.
# python -m pip install -r training/requirements.lock.txt
```

아래는 **로컬 Codex가 구현·검증해야 하는 CLI 계약**이며 현재 실행 가능한 학습 명령이 아니다:

```bash
python training/scripts/train.py --config training/configs/smoke.json
python training/scripts/evaluate.py --config training/configs/smoke.json --compare-base
python training/scripts/export.py --config training/configs/smoke.json --format gguf
```

옵션/실제 재현 명령은 구현 후 이 문서에 갱신한다. 패키지 버전이나 모델 지원을 추정해 빈 trainer를 성공 처리하지 않는다.

## 데이터 계약과 완료 기준

로컬 Git 제외 경로 `artifacts/llm-training/data/`에 JSONL 저장. 각 레코드에 id, source/license, review_status, split, messages(role/content)를 두고 assistant content는 앱의 JSON 출력 계약을 따른다. 원본 대화 전체를 로그/PR에 붙이지 않는다. 예시는 형식 참고이며 학습 승인 데이터가 아니다:

```json
{"id":"example-only","source":"authored-example","license":"pending-author-review","review_status":"pending","split":"train","messages":[{"role":"user","content":"친구처럼 반말로 이야기하자."},{"role":"assistant","content":"{\"spoken_text\":\"좋아, 편하게 이야기하자.\",\"intent\":\"chat\",\"emotion\":\"warm\",\"delivery\":{\"pace\":\"normal\",\"energy\":\"medium\",\"expressiveness\":\"gentle\"},\"tts_instruction\":\"\"}"}]}
```

실제 학습에서는 앱과 동일한 system persona와 template를 사용하고, 메시지 본문/특수 토큰/assistant label masking이 맞는지 검사한다. train에 test 입력이나 정답이 섞이지 않게 한다.

완료 보고는 환경 준비 / 모델 로드 / 10step / adapter 재로드 / 블라인드 전후 비교 / GGUF 변환 / Android 실측을 각각 완료·실패·미실행으로 나눈다. 모든 단계의 성공을 한 번에 추정하지 않는다. 비용 발생 서비스/클라우드 학습/음성 업로드는 이번 범위에 없다.

우리는 별도 Android 패치에서 prefill 병목과 지시문 노출/자기소개 품질을 다룬다. 로컬 학습 결과가 나오기 전 기본 모델을 교체하지 않는다.
