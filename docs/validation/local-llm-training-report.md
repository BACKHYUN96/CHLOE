# 로컬 대화 LLM 학습 사전 검증 · 2026-11-12 갱신

2026-11-14 후속: 아래 JSON 계약 실패를 원문과 대조한 결과 실제 schema/grammar가 누락된 PC 평가 조건이 주요 원인이었다. 기존 원본/adapter를 보존한 수정·재비교는 [JSON 계약 후속 보고서](local-llm-json-contract-report.md)를 따른다. 아래는2026-11-12 당시 실행 기록이며 이후 재학습하지 않았다.

## 현재 결과 · 재부팅 후 WSL2/CUDA 및 10-step 실행

**WSL2 준비, 고정 Qwen3.5-2B 4-bit forward/backward, 10-step QLoRA, adapter 저장·새 객체 재로드를 실제 실행했다. 그러나 재로드 응답은 384-token 한도에 걸려 JSON 계약을 통과하지 못했고, 부분 원본/adapter 비교도 두 후보 모두 계약 실패다. 품질 개선·Android 적용을 승인하지 않는다.**

사용자 재부팅 후 `CHLOE-Training-24.04`라는 새 전용 배포판에 Ubuntu 24.04.5를 등록했다. 기존 Windows 환경·모델·앱은 보존했다. WSL 기본 메모리는 약31GiB, swap8GiB로 관측됐고 호스트64GiB와 구분한다. Linux의 약1TB 여유 표시는 동적 VHD의 가상 용량이며 물리 C: 여유 공간과 다르다. Linux 사용자 `chloetrain`의 `/home/chloetrain/CHLOE` 및 `.venv-llm`만 학습에 사용했다.

| 단계 | 현재 상태 | 증거 |
| --- | --- | --- |
| WSL2·Ubuntu·GPU·CUDA tensor | 완료 | WSL3.0.5, kernel6.18.58.1-microsoft-standard-WSL2, RTX4070 SUPER, BF16 CUDA 연산 통과 |
| 모델 로드·QLoRA forward/backward | 완료 | 원본 checkpoint SHA 검증, missing key 없음, GPU만 사용, assistant mask 검사 |
| 최대10-step·adapter 저장 | 완료 | 각 step loss/gradient 유한, 새 디렉터리에 저장 |
| adapter 재로드·생성 실행 | 완료 | 새 base 객체와 저장 adapter를 다시 로드해 추론 |
| 재로드 응답의 앱 계약 | 실패 | 384tokens, 종료 토큰 미도달, JSON 미완성·반복 출력 |
| 원본/adapter 부분 비교 | 실행 완료·계약 실패 | 고정 첫4질문×2말투×2후보=16회, 정상 종료16회, 엄격 JSON/enum/소비자 계약 통과0/16 |
| 전체54입력×2말투 비교·사람 블라인드 평가 | 미완료 | 부분 비교를 전체 품질 평가로 확대 해석하지 않음; 사람 점수 null |
| merge·GGUF·Q4_K_M·Android 실측 | 미실행 | 품질 이득 미확인. export의 승인 누락 거부 경로만 검증 |

### 실제 설정·수치

- 환경: Python3.12.3, PyTorch2.9.1+cu128, Transformers5.23.0.dev0(`a72a1c3…`), PEFT0.21.3.dev0(`34d342a…`), TRL1.18.0.dev0(`6a7764a…`), bitsandbytes0.50.2, accelerate1.15.0. 기존에 읽은 HF 커밋을 선택했고 PyTorch는 공식 CUDA12.8 배포 조합을 사용했다. [requirements.lock.txt](../../training/requirements.lock.txt)는 전이 의존성까지 고정한 실제 freeze이며, wheel 전체를 hash-lock한 배포물은 아니다. pip25.3으로 설치·`pip check` 반환0.
- Qwen revision과 원본 checkpoint SHA는 아래 최초 조사와 동일하다. 이번에는 **4,548,221,488-byte checkpoint를 로컬에서 실제 해시 검증**했다. config/template/tokenizer config/LICENSE도 준비 CLI에서 일치함을 재확인했다. GGUF를 학습하거나 remote model code를 실행하지 않았다.
- 사용자가 검토 자료의 합성6개를 모두 시험용으로 승인했다. train4/validation1/test1의 서로 다른 대화 family로 분리했고 기존54평가 입력과 근접 문자열을 검사했다. 의미적 의역 누락까지 자동 증명한 것은 아니다. 데이터와 응답 본문은 PR에 넣지 않고 승인 범위·SHA만 기록했다.
- microbatch1, context512, gradient checkpointing, rank8/alpha16, AdamW lr1e-4, seed42, 최대10step. 실제 입력280–321tokens, assistant55–66tokens. 원본 Qwen3.5 template에 대응하는 TRL 전용 mask를 사용해 system/user/빈 thinking prefill을 loss에서 제외하고 완전한 assistant JSON을 확인했다.
- 실제 `named_modules()`에서 full-attention q_proj/v_proj 12개만 선택했다. trainable **417,792개**. NF4/double-quant/BF16, eager attention, GPU-only. `causal_conv1d`/flash-linear-attention 미설치로 **느린 reference PyTorch kernel**을 사용했다. CPU offload나 모델 교체는 없다.
- 최종10step의 loss는 **1.73999–2.21116**, 첫1.97212 / 마지막1.90731이다. 서로 다른 샘플 순환 값이므로 단조 감소나 품질 향상을 주장하지 않는다. validation loss2.01304 / test loss1.96367이며 각각 한 샘플뿐이다.
- 최종 학습 구간 **4.09464초**, PyTorch 최대 allocated **4,795,348,992 bytes(약4.47GiB)** / reserved **5,133,828,096 bytes(약4.78GiB)**. 다운로드·모델 로드·adapter 재로드·생성 시간과 전체 보드 메모리를 포함하지 않는다.
- adapter SHA-256 `661873993a9c70089937a64d9282e21a1ce2b622a5b60764305159c0c98bb025`. 로컬 outputs에 adapter ZIP만 제공하고 Git에는 가중치를 넣지 않았다. 품질 미검증 상태이며 Android용 GGUF가 아니다.

### 재현 명령과 검증 범위

Linux 전용 clone 루트에서 실행한다. 승인 데이터는 로컬 `artifacts/llm-training/data/smoke-approved.jsonl`에 보존돼 있으며 공개 저장소에는 없다. 이미 존재하는 run 출력은 거부하므로 재실행할 때 config의 output_dir을 새 artifact 경로로 지정한다.

```bash
python3 -m venv .venv-llm             # 새 clone에서만; 기존 venv 덮어쓰기 금지
.venv-llm/bin/python -m pip install pip==25.3
.venv-llm/bin/python -m pip install -r training/requirements.lock.txt
.venv-llm/bin/python training/scripts/prepare_model.py --config training/configs/smoke.json
.venv-llm/bin/python training/scripts/train.py --config training/configs/smoke.json
# 전체 비교 CLI; 이번에는 --limit 4를 명시해 부분 실행했다.
.venv-llm/bin/python training/scripts/evaluate.py --config training/configs/smoke.json --compare-base
.venv-llm/bin/python -m unittest discover -s training/tests -v
```

실제 호환성/학습/부분 비교/최종17개 회귀 테스트는 반환0이었다. `prepare_model.py`의 이미 준비된 모델 검증 경로를 실제 실행해 반환0을 확인했다. 최초 다운로드는 같은 snapshot_download API와 고정 allowlist를 사용한 사전 검사에서 수행했으며, 새 다운로드 CLI의 빈 디렉터리 경로를 다시 내려받아 시험하지는 않았다. 학습 구현은 직접 PyTorch/PEFT loop이고 TRL은 검증된 assistant mask template 경로를 사용한다. `evaluate.py`는 원본과 adapter에 같은 persona/seed/greedy/thinking=false/종료 토큰/384token/2048문맥을 적용한다. llama.cpp JSON grammar를 적용한 앱 실행과는 다르며 앱 schema와 소비자 규칙으로 사후 검증한다.

`export.py --config … --format gguf --quality-approval <receipt.json>`은 사람 품질 검토·adapter hash가 맞지 않으면 merge 전 반환1로 거부한다. 이 거부 경로를 실제 확인했다. 정상 merge/변환 경로와 변환 의존성·quantizer 실행은 미검증이며 이번에는 실행하지 않았다. 긴 학습과 배포용 변환은 품질 이득이 확인된 뒤 진행한다.

증거: [실행 요약](local-llm-training/execution-summary-20261112.json), [WSL CUDA preflight](local-llm-training/preflight-wsl-runtime-20261112.json), [checkpoint 검사](local-llm-training/checkpoint-compatibility-20261112.json), [최종10step](local-llm-training/smoke-result-20261112.json), [부분 비교16회](local-llm-training/evaluation-partial-20261112.json), [데이터 승인](local-llm-training/data-review-20261112.json), [export 차단](local-llm-training/export-guard-20261112.json).

### 문제·수정·남은 항목

- 내장 Ubuntu 다운로드는 Store/web 양쪽 모두 WININET_E_NAME_NOT_RESOLVED로 실패했다. Microsoft 공식 배포 목록에서 Ubuntu24.04 이미지/해시를 확인하고 별도 DNS에서 조회한 공식 서버로 HTTPS 다운로드했다. 첫 IP 연결은 timeout, 다른 공식 IP는 성공했다. TLS 검증과 Windows DNS 설정은 유지했다. 새 배포판 안에서만 resolver1.1.1.1/1.0.0.1을 사용해 apt를 준비했다. 이미지 SHA는 실행 요약에 있다.
- 사전 forward/backward 후 결과 저장 중 HF의 set 타입을 JSON으로 쓸 수 없는 오류가 있었다. 원본 로그/부분 파일을 로컬에 보존했고 list로 변환해 재검사했다. 최종 증거 저장 함수는 파일 생성 전에 JSON 직렬화를 마치며 이 회귀를 테스트한다.
- 첫 비교에서는 text config의 EOS248044와 chat tokenizer의 im_end248046 차이로 정상 종료를 false로 표시했다. 두 종료 토큰을 지원하도록 고치고 회귀 테스트와 비교를 재실행했다. 수정 전·후 로컬 로그는 모두 보존했다. 최종 코드도 새 디렉터리에서 **원본부터 별도의10step**로 재현했으며 두 adapter SHA가 같았다. 연속20step 또는 더 긴 학습이 아니다. 수정 후16회 비교는 동일 adapter의 결과다.
- Windows에서 Linux로 복사한 파일의 CRLF 때문에 Linux diff 검사가 한 차례 실패했다. Linux 작업 복사본을 LF로 정규화한 뒤 diff 검사, Python 구문 컴파일과 세 CLI help가 모두 통과했다. Windows 원본 모델이나 사용자 자료를 정리하지 않았다.
- train/evaluate/export CLI와 lock 구현, 모델 준비,10step 및 재로드 실행은 완료했다. **재로드 JSON 계약·전체 평가·사람 품질 검토·GGUF·Android는 미완료/실패**로 유지한다. 6개 샘플로 이득을 주장하거나 추가 장기 학습을 자동 실행하지 않는다. register/enum/반복 개선과 더 넓은 승인 데이터가 후속 과제다.

## 앞선 설치 기록 · 재부팅 전

아래는 2026-11-12 00:41 당시 기록이다. 이후 사용자 재부팅과 위 환경 준비/실행으로 재부팅 차단은 해소됐다.

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
