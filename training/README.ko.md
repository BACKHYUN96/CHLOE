# 로컬 Codex 작업 지시: CHLOE 한국어 대화 LLM 학습

이 문서를 로컬 Codex에게 읽히고 실제 PC에서 진행한다. 최초 자료는 **학습 인수인계/사전 점검**이었다. 아래 현재 상태는 실제 PC 실행 결과이며 클라우드 학습 결과가 아니다.

## 2026-11-14 JSON 계약 수정

기존 원본/adapter를 재학습하지 않고 PC 추론 조건을 수정했다. 이전 실패16개 중15개는 JSON 문법은 맞았지만 주로 enum을 위반했다. PC는 “주어진 schema”라는 문구만 보내고 실제 schema와 앱의 grammar 제약을 제공하지 않았다. 현재 평가는 실제 enum/필수 키를 전달하고 byte 기반 JSON Schema decoder와 소비자 검증을 함께 사용한다. [원인·수정·비교 보고서](../docs/validation/local-llm-json-contract-report.md)를 따른다. 아래2026-11-12의0/16은 수정 전 조건의 기록이다.

최종 동일 조건의54질문+이전 실패 test1질문×2말투 비교에서 **원본110/110, adapter110/110**, 총220/220 계약 통과를 실제 확인했다. 회귀24개 통과. 원본·adapter SHA와 기존 venv는 그대로다. 이는 생성 조건 수정의 구조적 결과이며 adapter 품질 이득이나 Android 성공으로 승격하지 않는다.

사용자 말투·내용 평가용 [블라인드 평가 자료 생성·검증 보고서](../docs/validation/local-llm-blind-review-report.md)를 추가했다. 같은 실제 응답 중 반말·존댓말·자기소개·정직성·문맥 기억을 사전 고정해22카드/40쌍으로 구성했다. 이후 사용자가 평가 JSON을 제출해 [집계·분석](../docs/validation/local-llm-human-review-report.md)을 완료했다. **adapter 선호2, 원본 선호0, 비슷함4, 둘 다 부적합13, 보류3**이다. 모든 카드를 검토했고 보류는 그대로 유지한다. 상세 점수132개는 모두 null이며 품질 이득·모델 승격은 미승인이다. 원문 평가지·응답·대응표는 Git 제외 경로에 보관하고 PR에는 생성기·합성 테스트·비민감 집계·분석만 포함한다. 추가 학습·추론·모델 변경은 수행하지 않았다.

기존 학습 venv를 보존하도록 decoder만 별도 폴더에 설치한다. Linux의 `gcc`/`python3.12-dev`가 필요하며 이번 CHLOE 전용 배포판에만 추가했다. 전체 비교는 새 출력 경로를 지정하고, 반복 실패했던 test 입력도 포함할 수 있다.

```bash
.venv-llm/bin/python -m pip install --no-deps --require-hashes \
  --target artifacts/llm-training/contract-deps-xgrammar-20261114 \
  -r training/requirements.contract.txt
.venv-llm/bin/python training/scripts/evaluate.py --config training/configs/smoke.json \
  --compare-base --include-heldout --contract-mode constrained \
  --output artifacts/llm-training/contract-20261114/xgrammar-final
```

`--contract-mode legacy`는 이전 schema 누락 조건, `schema`는 schema 전달만 하는 조건, `constrained`는 schema 전달과 생성 제약을 함께 적용하는 기본 조건이다. `--grammar-deps`로 별도 설치 경로를 지정한다. `--case-ids conv35 conv37`처럼 특정 질문을 재현할 수 있다. 형식 통과는 말투/자연스러움 개선이나 Android 검증을 의미하지 않는다. 새 학습 또는 모델 변환은 수행하지 않았다.

## 2026-11-12 기록 · WSL2 QLoRA10step 실행, 수정 전 계약 실패

사용자 재부팅 후 독립 `CHLOE-Training-24.04` 배포판의 Linux 전용 `.venv-llm`에서 GPU/PyTorch·원본 모델 SHA·assistant mask·forward/backward를 검증하고 train/evaluate/export와 고정 requirements를 구현했다. 승인한 합성6개(train4/validation1/test1)로10step, adapter 저장과 새 객체 재로드까지 실행했다. 최종 학습4.09초, trainable417,792개, peak allocated 약4.47GiB / reserved4.78GiB였다. 기존 Windows 환경·Android 모델은 보존했다.

**재로드 응답은384토큰 한도에 걸려 JSON 미완성이고, 첫4질문×2말투×원본/adapter의16회 부분 비교는 엄격한 앱 JSON/enum 계약 통과0회다.** 전체54입력·사람 평가·품질 이득·GGUF·Android는 미검증이다. 원본/adapter 모두의 실패를 그대로 기록했으며 기본 모델을 교체하지 않는다.

실제 지표·실패·재현 명령은 [최신 보고서](../docs/validation/local-llm-training-report.md), 실제 선택 버전은 [requirements.lock.txt](requirements.lock.txt)에 있다. Linux clone에서 다음 명령을 사용한다. 승인 데이터·가중치·adapter는 Git 제외 로컬 artifact에 보존한다. 출력 경로가 존재하면 덮어쓰지 않으므로 재실행은 config의 output_dir을 새 경로로 지정한다.

```bash
.venv-llm/bin/python -m pip install -r training/requirements.lock.txt
.venv-llm/bin/python training/scripts/prepare_model.py --config training/configs/smoke.json
.venv-llm/bin/python training/scripts/train.py --config training/configs/smoke.json
# 기본은 전체54입력×2말투 비교. 이번 실제 실행은 --limit 4를 붙인 부분 비교다.
.venv-llm/bin/python training/scripts/evaluate.py --config training/configs/smoke.json --compare-base
.venv-llm/bin/python -m unittest discover -s training/tests -v
```

`export.py --config training/configs/smoke.json --format gguf --quality-approval <receipt.json>`은 사람 품질 이득 승인과 일치하는 adapter hash, clean pinned llama.cpp 및 준비된 quantizer를 요구한다. 이번에는 승인 누락 거부만 확인했고 merge/GGUF 정상 경로는 미실행이다.

## 앞선 기록 · 재부팅 전 설치 상태

이하 기록은 최초 설치/점검 당시 상태다. 현재 실행 결과는 위 항목을 따른다.

사용자 요청으로 관리자 승인 후 WSL 설치를 실행했다. WSL 3.0.5 / kernel 6.18.58.1-1 설치와 VirtualMachinePlatform 기능 추가는 완료했으며 **변경 사항 적용을 위한 Windows 재부팅이 필요하다.** 자동 재부팅은 하지 않았다. Ubuntu 배포판은 아직 등록되지 않았고 WSL2 내부 GPU/CUDA 실행도 미검증이다. 기존 환경·앱·Android 모델은 보존했다.

재부팅 후 배포판 목록을 다시 확인하고, Ubuntu가 없을 때만 설치를 마친 뒤 Linux 전용 `.venv-llm`에서 학습 호환성 검증→trainer 구현→최대10-step→adapter 재로드 순서로 이어간다. 상세 설치 반환 코드와 재개 절차는 [보고서의 2026-11-12 갱신](../docs/validation/local-llm-training-report.md)에 있다. 아래 2026-11-11 기록은 최초 점검 당시 상태다.

## 2026-11-11 최초 로컬 실행 상태

실제 Windows PC에서 RTX 4070 SUPER 12GB·RAM 약64GiB를 확인했지만 WSL 미설치로 WSL2/CUDA 학습 환경 검증에 실패했다. 별도 `.venv-llm`에서 점검했고 기존 앱·Android 모델은 변경하지 않았다. 공식 Qwen3.5-2B revision의 메타데이터/라이선스/SHA와 TRL Qwen3.5 전용 mask template 및 pinned llama.cpp 지원 소스를 대조했다. 모델 가중치 로드·10-step·adapter·품질 비교·GGUF·Android 실측은 미실행이다. requirements lock과 train/evaluate/export는 실제 runtime 검증 후 구현할 계약으로 남는다.

실제 결과와 재개 조건: [로컬 학습 보고서](../docs/validation/local-llm-training-report.md). [평가 계획](configs/evaluation-plan.json)은 기존50개+보강4개 입력을 고정하며 모든 품질 점수는 미평가다.

현재 실행 가능한 stdlib 점검 CLI:

```bash
# 기본은 설치/모델 다운로드 없는 inventory이며 환경 미준비여도 0을 반환할 수 있다.
python training/scripts/preflight.py --output artifacts/llm-training/preflight-new.json
# WSL2 환경이 아니면 기록 후 1 반환. 런타임 옵션은 import와 작은 CUDA tensor 연산만 수행한다.
python training/scripts/preflight.py --output artifacts/llm-training/runtime-new.json --require-wsl2 --require-runtime
# 공식 고정 revision의 소형 메타데이터만 HTTPS로 읽고 SHA를 기록. 가중치/remote code 실행 없음.
python training/scripts/inspect_model.py --output artifacts/llm-training/model-metadata-new.json
python -m unittest discover -s training/tests -v
```

`--probe-runtime`은 import/CUDA probe만 추가하며, `--require-runtime`은 이를 포함하고 실패 시1을 반환한다. 이 검사도 Qwen3.5 모델 forward나 QLoRA 성공을 인증하지 않는다. 모든 출력 파일은 기존 경로가 있으면 거부한다. Windows에서 만든 venv는 WSL에서 재사용하지 않는다.

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

아래는 최초 인수인계의 CLI 계약이다. 현재는 위 설정과 승인 데이터로 train/evaluate를 실제 실행했으며 export는 추가 품질 승인과 변환 도구가 필요한 제한 경로다:

```bash
python training/scripts/train.py --config training/configs/smoke.json
python training/scripts/evaluate.py --config training/configs/smoke.json --compare-base
python training/scripts/export.py --config training/configs/smoke.json --format gguf --quality-approval <receipt.json>
```

실제 실행 범위와 미실행 경로는 최신 보고서를 따른다. 패키지 버전이나 모델 지원을 추정해 성공 처리하지 않는다.

## 데이터 계약과 완료 기준

로컬 Git 제외 경로 `artifacts/llm-training/data/`에 JSONL 저장. 각 레코드에 id, source/license, review_status, split, messages(role/content)를 두고 assistant content는 앱의 JSON 출력 계약을 따른다. 원본 대화 전체를 로그/PR에 붙이지 않는다. 예시는 형식 참고이며 학습 승인 데이터가 아니다:

```json
{"id":"example-only","source":"authored-example","license":"pending-author-review","review_status":"pending","split":"train","messages":[{"role":"user","content":"친구처럼 반말로 이야기하자."},{"role":"assistant","content":"{\"spoken_text\":\"좋아, 편하게 이야기하자.\",\"intent\":\"chat\",\"emotion\":\"warm\",\"delivery\":{\"pace\":\"normal\",\"energy\":\"medium\",\"expressiveness\":\"gentle\"},\"tts_instruction\":\"\"}"}]}
```

실제 학습에서는 앱과 동일한 system persona와 template를 사용하고, 메시지 본문/특수 토큰/assistant label masking이 맞는지 검사한다. train에 test 입력이나 정답이 섞이지 않게 한다.

완료 보고는 환경 준비 / 모델 로드 / 10step / adapter 재로드 / 블라인드 전후 비교 / GGUF 변환 / Android 실측을 각각 완료·실패·미실행으로 나눈다. 모든 단계의 성공을 한 번에 추정하지 않는다. 비용 발생 서비스/클라우드 학습/음성 업로드는 이번 범위에 없다.

우리는 별도 Android 패치에서 prefill 병목과 지시문 노출/자기소개 품질을 다룬다. 로컬 학습 결과가 나오기 전 기본 모델을 교체하지 않는다.
