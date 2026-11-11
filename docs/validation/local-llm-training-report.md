# 로컬 대화 LLM 학습 사전 검증 · 2026-11-12 갱신

## 2026-11-12 WSL 설치 진행 · 재부팅 필요

사용자가 WSL2 설치부터 진행하도록 명시적으로 요청해, Windows 관리자 승인(UAC)을 거쳐 `wsl.exe --install -d Ubuntu-24.04 --no-launch`를 실제 실행했다. **WSL 패키지와 커널 설치는 완료했고, VirtualMachinePlatform 기능 활성화를 위한 Windows 재부팅이 필요하다. Ubuntu 배포판 등록과 WSL2 실행 준비는 아직 완료되지 않았다.** 재부팅은 자동 실행하지 않았다.

설치 전 작업 트리는 깨끗했고, 로컬/원격 작업 브랜치는 `277d44185e124ddb951ade165e7c2fcf703fb2ea`로 같았다. 원격 main은 기존 `fd9b5982466db52c65ded7f3436e94beb3fcb54c`였다. 기존 WSL 배포판은 없었으며 기존 앱·Python 환경·Android 모델·GGUF·TTS는 변경/삭제하지 않았다. WSL에 Linux NVIDIA 드라이버를 설치하지 않았다.

| 실제 명령/검사 | 결과 |
| --- | --- |
| 관리자 역할 / CPU 가상화 확인 | 일반 셸은 관리자 아님; 펌웨어 가상화 및 SLAT는 true |
| 관리자 설치 명령 | 2026-11-12 00:40:51–00:41:42 KST, 반환0, stderr 0 bytes |
| 설치 로그 | VirtualMachinePlatform 추가, WSL 3.0.5 설치 완료, 시스템 재시작 후 변경 사항 적용 안내 |
| `wsl --version` | 반환0; WSL 3.0.5.0 / kernel 6.18.58.1-1 / WSLg 1.0.79 |
| Windows CBS RebootPending | true |
| `wsl --status` | 반환0, 기본 버전2; 가상 머신 플랫폼이 활성화되지 않아 WSL2를 시작할 수 없다는 안내 |
| `wsl --list --verbose` | 설치된 배포판 없음; shell -1 / Python unsigned 4294967295 |
| 설치 후 strict preflight | 반환1; Windows 호스트에서 실행, WSL2·CUDA runtime 검증 미완료 |

설치 명령의 반환0이나 WSL 기본 버전2를 Ubuntu/WSL2/CUDA 실행 성공으로 보고하지 않는다. 지금 상태에서 WSL 설치를 반복하거나 기존 환경을 재설치하지 않는다. 실제 설치 기록은 [wsl-install-20261112.json](local-llm-training/wsl-install-20261112.json), 설치 후 환경은 [preflight-after-wsl-install-20261112.json](local-llm-training/preflight-after-wsl-install-20261112.json)에 보관했다. 원본 로컬 설치 로그는 Git 제외 경로 `artifacts/llm-training/wsl-install-20261112-attempt1/`에 보존했다.

**사용자에게 필요한 다음 작업은 열려 있는 작업을 저장하고 Windows를 재부팅하는 것이다.** 재부팅 후 이 채팅에서 이어서 진행하면 아래 순서로 확인한다.

1. `wsl --status`, `wsl --version`, `wsl --list --verbose`를 다시 읽는다. Ubuntu-24.04가 이미 등록돼 있으면 다시 설치하지 않는다.
2. 배포판이 여전히 없을 때만 `wsl --install -d Ubuntu-24.04 --no-launch`로 Ubuntu 설치를 마친다. 초기 Linux 계정 설정이 필요하면 안내한다. 기존 배포판 unregister/reset 및 자동 재부팅은 하지 않는다.
3. Ubuntu VERSION=2와 Linux 내부 `nvidia-smi`를 확인하고 Linux 홈에 독립 작업 clone 및 Linux Python `.venv-llm`을 준비한다. Windows venv는 재사용하지 않는다.
4. 아래 재개 조건에 따라 실제 학습 조합·checkpoint 로드/forward·LoRA target·assistant mask를 검증한 뒤 lock 및 train/evaluate/export를 구현한다. 승인된 데이터가 준비되면 최대10-step·adapter 저장/재로드를 실행하고 같은 PR을 업데이트한다.

이번 갱신은 설치 실행 증거와 재개 절차를 추가한 문서/JSON 변경이다. `git diff --check`와 JSON 무결성 검사를 실행했다. 아래 9개 테스트 통과 기록은 2026-11-11의 코드 검증 결과이며 이번에 학습·Android·모델 실행 검증을 추가했다는 뜻이 아니다. 학습 스크립트 구현·10-step·adapter·평가·GGUF·Android 실측은 계속 미완료다.

## 최초 검증 결과 · 2026-11-11

**호스트 점검과 공식 소스 대조를 완료했으나, WSL2가 설치되지 않아 학습 환경 검증은 실패했다. Qwen3.5-2B 모델 로드·10-step 학습은 미실행이다.** Qwen3.5 자체가 이 GPU에서 학습 불가능하다는 결과는 아니다. 기존 Android 앱·모델·Sohee TTS·GGUF·사용자 파일은 건드리지 않았다.

별도 clone의 `docs/local-codex-training` 커밋 `da0546c`에서 `experiment/local-llm-training`을 만들었다. 시작 시 작업 트리는 깨끗했다. 원격 main은 `fd9b5982466db52c65ded7f3436e94beb3fcb54c`이며 `training/README.ko.md`가 없다. 인수인계 [PR #13](https://github.com/BACKHYUN96/CHLOE/pull/13)은 미병합이므로 이번 PR의 base는 `docs/local-codex-training`이다. main에 Android 변경 전체를 다시 포함하거나 자동 병합하지 않는다.

| 단계 | 상태 | 실제 증거/이유 |
| --- | --- | --- |
| Windows PC 사양·GPU 조회 | 완료 | i9-14900K, RAM 약 64GiB, RTX 4070 SUPER 12282MiB |
| WSL2 환경 준비 | 실패 | `wsl --status` 50, `wsl --list --verbose` 1, WSL 미설치 안내 |
| CUDA PyTorch·학습 패키지 import | 실패 | 새 `.venv-llm`의 6개 패키지 모두 `ModuleNotFoundError` |
| 공식 모델·학습/변환 소스 조사 | 완료 | revision·메타데이터 SHA·템플릿 대응·변환 등록 확인; 실행 호환성과 구분 |
| 원본 checkpoint 로드/forward·실제 named_modules | 미실행 | WSL2/CUDA 환경 미준비; 가중치 미다운로드 |
| 학습 requirements lock·train/evaluate/export | 미완료 | 실제 import/forward로 선택 조합을 검증하지 못해 잠금 파일과 trainer를 확정하지 않음 |
| 최대 10-step QLoRA | 미실행 | 환경 선행 조건과 사람이 승인한 학습 데이터가 없음 |
| adapter 저장·재로드·추론 | 미실행 | adapter가 없음 |
| 원본/adapter 블라인드 비교 | 미실행 | 평가 입력만 고정, 생성·사람 평가는 없음 |
| merge·GGUF·Q4_K_M | 미실행 | 품질 이득·adapter 없음 |
| Android 실측 | 미실행 | 앱·importer·runtime 변경 및 기기 조작 없음 |

loss, trainable parameter 수, 학습 시간, 최대 GPU allocated/reserved는 모두 **미측정(null)**이다. OOM이나 학습 오류를 관측한 것이 아니다. CPU offload·다른 모델로의 대체·4B 다운로드도 하지 않았다. Windows native 학습 경로를 불가능하다고 판정하지 않았으며, 이번에는 인수인계의 WSL2 경로를 따른다.

## 실제 PC와 실행 기록

2026-11-11 23:42–23:47 KST에 읽기 전용으로 확인했다. 권한 제한 밖에서도 WSL 미설치 반환 코드를 재확인했다. `nvidia-smi`가 보여 주는 CUDA 13.4는 드라이버 지원 표기이며 CUDA Toolkit/PyTorch 설치나 CUDA tensor 실행의 증거가 아니다.

| 항목 | 관측 |
| --- | --- |
| OS | Windows build 26200; Python platform 문자열 `Windows-10-10.0.26200-SP0` |
| CPU | Intel Core i9-14900K, 24 cores / 32 logical processors |
| RAM | 68,399,480,832 bytes |
| GPU / 드라이버 | RTX 4070 SUPER, 12282MiB / 616.92, WDDM |
| 시작 시 GPU 사용 메모리 | 2751MiB; 학습 peak가 아닌 다른 앱 포함 순간 관측 |
| 작업 볼륨 C: 여유 | preflight 시점 213,373,562,880 bytes, 약 198.7GiB |
| Python | PATH는 WindowsApps alias, `py -0p`에는 등록 없음. 별도 설치 경로의 CPython 3.10.6 발견 |
| 격리 환경 | 기존 CPython으로 작업 clone에 `.venv-llm` 신규 생성; pip 22.2.1 / setuptools 63.2.0만 존재 |
| torch / transformers / peft / trl / bitsandbytes / accelerate | 모두 미설치; 다른 앱의 Python/venv는 변경하지 않음 |

아래 Windows 명령은 작업 clone 루트에서 실제 실행했다. `$python310`은 기존 `AppData/Local/Programs/Python/Python310/python.exe`의 절대 경로이며 개인 계정명은 생략한다. WSL 설치 명령은 실행 기록에 포함되지 않는다.

```powershell
& $python310 --version
& $python310 -m venv .venv-llm
& ./.venv-llm/Scripts/python.exe training/scripts/preflight.py --output artifacts/llm-training/preflight-host.json --require-wsl2 --require-runtime
& ./.venv-llm/Scripts/python.exe training/scripts/inspect_model.py --output artifacts/llm-training/model-metadata.json
& ./.venv-llm/Scripts/python.exe -m unittest discover -s training/tests -v
git diff --check
```

| 명령 | 반환 코드 | 결과 |
| --- | --- | --- |
| `git clone --branch docs/local-codex-training --single-branch --filter=blob:none … work/CHLOE` | 0 | 새 폴더에만 복제; submodule/모델 초기화 안 함 |
| `git fetch origin main` | 0 | main SHA 확인; main에는 인수인계 문서 없음 |
| `git switch -c experiment/local-llm-training` | 0 | 별도 작업 브랜치 생성 |
| `wsl --status` / `wsl --list --verbose` | 50 / 1 | WSL 미설치 |
| `nvidia-smi` 및 preflight GPU query | 0 | Windows GPU 조회 성공 |
| `Get-CimInstance Win32_Processor` / `Win32_ComputerSystem` | PowerShell 성공 | 위 CPU/RAM 값; 제한된 셸에서는 CIM 접근 실패해 읽기 권한 있는 실행으로 재확인 |
| CPython `--version` / `-m venv .venv-llm` | 0 / 0 | Python 3.10.6, 새 격리 환경 |
| preflight `--require-wsl2 --require-runtime` | 1 | WSL2·package imports·Qwen3.5 class import·CUDA tensor 확인 실패를 JSON으로 저장 |
| `inspect_model.py --output …` | 0 | 고정 revision의 소형 메타데이터만 HTTPS 조회 |
| `unittest discover -s training/tests -v` | 0 | 9개 통과; CUDA/실제 모델 시험 아님 |
| `git diff --check` | 0 | 공백 오류 없음 |

초기 제한 셸의 clone/fetch는 네트워크 이름 조회 실패로 끝났고, 허용된 네트워크 실행에서 재시도해 성공했다. `npx skills add nvidia/skills --list` 역시 DNS 실패하여 공식 [NVIDIA 카탈로그](https://raw.githubusercontent.com/NVIDIA/skills/main/skills.sh.json)를 읽었다. 이번 Qwen/Transformers 점검에 추가할 전용 스킬은 선택·설치하지 않았다.

비민감 실행 증거: [호스트 preflight](local-llm-training/preflight-host.json), [모델 메타데이터](local-llm-training/model-metadata.json), [읽은 upstream 소스 SHA](local-llm-training/source-audit.json). 토큰·개인 대화·음성·가중치·가상환경은 PR에 넣지 않는다.

## Qwen3.5-2B 호환성 조사

모델은 [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B/tree/15852e8c16360a2fea060d615a32b45270f8a8fc), revision `15852e8c16360a2fea060d615a32b45270f8a8fc`, Apache-2.0이다. 모델 API와 LICENSE를 읽었으며 remote code는 실행하지 않았다.

- config는 `qwen3_5` / nested `qwen3_5_text`, 24개 layer에 linear attention 18개와 full attention 6개를 지정한다. Qwen3와 같은 모델이라고 취급하지 않는다.
- 공식 [Transformers Qwen3.5 문서](https://huggingface.co/docs/transformers/model_doc/qwen3_5)의 text-only class는 `Qwen3_5ForCausalLM` / `Qwen3_5TextConfig`다. 실제 checkpoint에서 text 경로로 로드할 때 missing/unexpected key·weight mapping을 검사해야 한다. config에 적힌 `transformers_version=4.57.0.dev0`는 검증된 최소 지원 버전이라는 뜻이 아니다.
- 읽은 [Transformers 소스](https://github.com/huggingface/transformers/blob/a72a1c385297bfaf1c8a07b5f4e689a315b90b77/src/transformers/models/qwen3_5/modeling_qwen3_5.py)는 `5.23.0.dev0` 개발 커밋이다. text class·gradient checkpointing·PyTorch DeltaNet 경로가 있다. 이것을 설치하거나 안정 버전 조합으로 잠그지 않았다. 선택 runtime에서 kernel 사용 여부와 fallback 비용을 따로 기록해야 한다.
- 실제 모델의 `named_modules()`는 아직 검사하지 않았다. 소스상 full attention에는 q_proj/v_proj 등이, linear attention에는 in_proj_qkv 등이 있어 모든 linear 일괄 LoRA 적용은 피한다. 첫 후보는 실제 확인한 full-attention q_proj/v_proj의 제한된 범위, rank8이며 대상 목록·개수를 저장해야 한다.
- 공식 [PEFT quantization 가이드](https://huggingface.co/docs/peft/developer_guides/quantization)와 [k-bit 준비 구현](https://github.com/huggingface/peft/blob/34d342a6156bd77a83f093b5be21fd8396edc451/src/peft/utils/other.py)을 읽었다. NF4/double-quant/BF16 + `prepare_model_for_kbit_training` 경로는 일반적 지원 근거이며, 이 PC의 Qwen3.5 QLoRA 성공 근거는 아니다. [bitsandbytes 설치 문서](https://huggingface.co/docs/bitsandbytes/main/en/installation)도 확인했으나 CUDA wheel/kernel 조합은 미검증이다.
- 원본 template와 tokenizer_config의 template는 byte-identical이고 `enable_thinking`을 포함하지만 generation marker는 없다. [TRL SFT 문서](https://huggingface.co/docs/trl/sft_trainer)는 assistant-only loss에 generation mask를 요구한다. 읽은 [TRL 커밋](https://github.com/huggingface/trl/blob/6a7764ac47291f290521e5e6f8ef1176d068281c/trl/chat_template_utils.py)은 Qwen3.5 전용 자동 대응을 구현한다. 이 모델 template가 `qwen3_5_nothink.jinja`와 byte-identical임을 직접 비교했고, 대응하는 `qwen3_5_nothink_training.jinja`의 marker도 확인했다. 따라서 소스상 경로는 있으나 실제 tokenizer/TRL import 및 `enable_thinking=False`의 token mask·assistant-only loss 검사는 남아 있다. Qwen3용 template를 수동 대체하지 않는다.

| 공식 파일 | 로컬 확인 SHA-256 |
| --- | --- |
| config.json | `ed1c1723241f23f7f4e23430759cbd7dcfb4103cbdfe052bfe7626b57c2615b4` |
| chat_template.jinja | `273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80` |
| tokenizer_config.json | `49e2b6e395f959f077f1e992b338919c0d4a9732fc6e613995e06557f843500c` |
| LICENSE | `bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a` |

공식 API가 게시한 checkpoint `model.safetensors-00001-of-00001.safetensors`는 4,548,221,488 bytes, SHA-256 `aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1`이다. **이는 게시자 메타데이터이며 로컬 가중치 다운로드/해시 검증 결과가 아니다.**

## 평가·데이터·Android 경계

[evaluation-plan.json](../../training/configs/evaluation-plan.json)에 앱의 기존 50개 fixture ID/순서, LF 정규화 SHA-256 및 Git blob OID를 고정했다. 자기소개/개발자·선생님 호칭/지시문 노출을 보강하는 합성 질문 4개를 추가해 총 54개다. 정답이 없는 평가 전용 입력이며 train 데이터가 아니다. 반말/존댓말 각각 seed42, greedy, thinking=false, context2048, 최대 생성384를 원본/재로드 adapter에 동일 적용할 계획이다. 문맥 10개는 순서·4턴/1200자 제한을 지키고, 각 모델 자신의 이전 응답을 사용하므로 전체 대화 경로 비교로 해석한다. 나머지는 매회 초기화한다.

실제 학습 데이터는 준비하지 않았다. README의 pending 예시를 approved로 바꾸거나 개인 대화·음성을 수집하지 않았다. train/validation/test의 대화·의역 family 분리와 권리/사람 승인은 모두 남아 있다. 평가 입력과 의역 family를 train/validation에서 제외하고 학습 전에 사람에게 분리 결과를 확인받아야 한다. 자연스러움·말투·자기소개·과잉 공감·지시문 노출·문맥·정직성 점수와 JSON 유효성은 전부 null이고 블라인드 평가는 미실행이다.

실제 persona의 기준은 `app/src/main/java/ai/chloe/voicelab/conversation/ConversationEngine.kt`의 `PersonaManager.system(polite)`이며, schema와 소비자 검증을 함께 따라야 한다. 별도의 `style` 키는 현재 schema에 없다. `intent/emotion/delivery` enum, 220자 발화, 추가 키 금지 및 persona의 `tts_instruction=""` 규칙을 비교해야 한다. schema만으로는 빈 instruction을 강제하지 않으므로 평가에서 따로 검사한다. 512-token 학습 후보에서는 긴 한국어 persona와 완전한 assistant JSON이 모두 들어가는지 검사하고, assistant 전체가 잘리거나 label이 전부 -100인 샘플을 묵인하지 않는다.

Android pinned llama.cpp는 `aa75ff3239f9cc675b081697deda9e1b112345c6`이다. 해당 커밋의 [conversion/qwen.py](https://github.com/ggml-org/llama.cpp/blob/aa75ff3239f9cc675b081697deda9e1b112345c6/conversion/qwen.py#L694)에 Qwen3_5 text/conditional class → QWEN35 등록이 있고 [qwen35 runtime](https://github.com/ggml-org/llama.cpp/blob/aa75ff3239f9cc675b081697deda9e1b112345c6/src/models/qwen35.cpp)도 직접 읽었다. 소스 존재와 새 학습 모델의 변환·기기 성공은 별개다. adapter 품질 이득이 나온 뒤 새 디렉터리에 merge→GGUF→Q4_K_M→동일 평가 순서로 진행한다. importer의 새 ID/size/SHA allowlist는 별도 Android PR이며 기본 모델을 교체하지 않는다.

## 재개 조건

1. 사용자가 관리자 PowerShell에서 `wsl --install -d Ubuntu-24.04`를 실행하고, 안내가 있으면 재부팅한 뒤 초기 Linux 사용자 설정을 마친다. 이번 작업에서는 OS 기능/드라이버/재부팅을 변경하지 않았다. [Microsoft 설치 문서](https://learn.microsoft.com/en-us/windows/wsl/install), [NVIDIA WSL 지침](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)을 따른다. WSL에 Linux 디스플레이 드라이버를 설치하지 않는다.
2. `wsl --list --verbose`에서 Ubuntu VERSION=2와 WSL 내부 `nvidia-smi`를 확인한다. Linux 홈의 별도 clone에서 이 작업 브랜치를 사용하고 `.venv-llm`을 **Linux Python으로 새로** 만든다. Windows venv를 재사용하지 않는다.
3. CUDA PyTorch 및 Transformers/PEFT/TRL/bitsandbytes/accelerate 조합을 후보별 검증한다. 버전을 먼저 선택해 기록하고 이 venv에만 설치한다. 실제 import·CUDA tensor·Qwen3.5 checkpoint forward/backward·LoRA target·mask를 확인한 조합을 정확한 CUDA wheel 출처 및 전이 의존성과 함께 `training/requirements.lock.txt`로 남긴다. upstream 개발 커밋을 무조건 최신 설치하는 명령은 제공하지 않는다.
4. 승인된 합성/저작 대화와 분할·고정 평가를 준비한 후 train/evaluate/export를 실제 선택 API로 구현한다. 첫 학습은 최대10 step/microbatch1/context512/rank8/gradient checkpointing 후보부터 시작한다. fallback·메모리 축소·실패를 명시하고 유한 loss, adapter 저장·재로드·추론, 시간/메모리/파라미터를 확인한다.
5. 원본/adapter 사람 비교에서 품질 이득을 확인해야 더 긴 학습·merge·GGUF·Android 검증으로 진행한다. 이번 PR은 이 후속 단계의 성공을 주장하지 않는다.

구현된 stdlib 점검 명령은 다음과 같다. strict 모드의 0은 **설치 환경 gate 통과**일 뿐 모델 학습 호환성 인증이 아니다. 기존 출력 경로는 덮어쓰지 않는다.

```bash
python training/scripts/preflight.py --output artifacts/llm-training/preflight-wsl.json --require-wsl2
# 후보 패키지를 선택·설치한 후:
python training/scripts/preflight.py --output artifacts/llm-training/runtime-wsl.json --require-wsl2 --require-runtime
python training/scripts/inspect_model.py --output artifacts/llm-training/model-metadata-wsl.json
python -m unittest discover -s training/tests -v
```
