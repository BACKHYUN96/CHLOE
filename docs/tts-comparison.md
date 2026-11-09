# CHLOE 한국어 TTS 비교 실험

목표는 파라미터 수나 단일 CER 우승이 아니라 한국인이 듣기에 자연스러운 여성 음성이다. 한국어 발음·억양·문장 끝·리듬·감정·일관성을 사용자 블라인드 청취로 판단한다. 특정 서비스/실제 인물의 음성은 참조·복제하지 않는다.

이 문서는 alpha7 실험 기능과 조사 결과다. **호스트에서 소리가 생성된 것, Android용 코드가 빌드된 것, S26 Ultra에서 실행된 것은 서로 다른 검증 단계다. 최종 품질 우승 모델은 아직 정하지 않았다.** 실제 산출 수/성공·실패/시간은 [검증 자료](validation/tts-comparison/)를 따른다. 비어 있는 평가를 0점으로 채우지 않는다.

## 보존한 기준과 브랜치

시작 시 작업 트리는 깨끗했고 `feat/voice-reference-presets`의 `61471e984a8664d0d54e24f5729d2d845fef075e`에서 `experiment/tts-korean-naturalness`를 생성했다. 당시 원격 main은 `fd9b5982466db52c65ded7f3436e94beb3fcb54c`였다. 기존 PR #4/#6의 CPU/말투 표본에 의존하며 GPU 실험 PR #5에는 의존하지 않는다. main을 자동 병합하지 않는다.

- 기준 모델: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, revision `0c0e3051f131929182e2c023b9537f8b1c68adfe`.
- tokenizer: `Qwen/Qwen3-TTS-Tokenizer-12Hz`, revision `7dd38ad4e9bad454aae9cd937d0cd577604fe229`.
- runtime: qwen3-tts.cpp `4562731dc612cb87b4cd1eedac275a17d1078773`, ggml `eced84c86f8b012c752c016f7fe789adea168e1e`.
- 형식: GGUF F16, code predictor의 5개 FFN down-projection만 F32 안정화. 저비트 양자화가 아니다.
- 기존 Sohee(speaker 2864), Korean(language 2064), CPU 기본 4스레드, buffered 전체 디코딩을 유지한다. 기존 `NativeBridge`, `VoiceWorkerService`, 모델 라이브러리의 구현은 바꾸지 않았다.
- 실험 기본 sampling: temperature 0.9 / top-k 50 / top-p 1.0 / repetition penalty 1.05 / max audio tokens 1024. seed는 42·43·44.
- 기존 합격 말투 5개는 유지하고 TTS Lab에서 선택하면 `optimized` 조건으로 분류한다. 공통 조건은 별도의 고정 지시이며 기존 앱의 기본 지시를 덮어쓰지 않는다.

실제 수치와 남은 검증은 [실험 결과](validation/tts-comparison/results.md), APK 검사 결과는 [build.json](validation/tts-comparison/build.json)에 정리했다. 공통 240개와 별도 조정 48개는 WAV 원본을 유지하며, 아직 사람의 6항목 품질 평가는 미입력이다.

## 모델과 지원 범위

| 모델 | 공식 한국어·라이선스 | 확인한 실행 경로 | 이 APK |
| --- | --- | --- | --- |
| Qwen3-TTS 1.7B CustomVoice | 한국어, Apache-2.0 | 기존 C++/JNI CPU 경로 및 과거 사용자 기기 실행 | Sohee 1.7B 생성·측정 지원. 새 Lab 기기 시험은 미실행 |
| Qwen3-TTS 1.7B VoiceDesign | 한국어, Apache-2.0 | 공식 `generate_voice_design`, pinned C++의 voice_design metadata/instruction 경로 및 이번 호스트 실행 | 별도 JNI·모델 가져오기 구현. Android 빌드는 검증, 폰 실행·음질은 미검증 |
| VoxCPM2 2B | 한국어 포함 30개 언어, 코드/원본 모델 Apache-2.0 | OpenBMB 공식 모바일 앱의 Android JNI와 고정 C++ runtime 확인. F16 호스트 경로도 별도 검증 | **CHLOE native 엔진 미연결**. PC WAV 가져오기·블라인드 평가 지원 |
| Fun-CosyVoice3-0.5B-2512 | 한국어 포함 9개 언어, Apache-2.0 | 공식 PyTorch 로컬 API. 커뮤니티 CPU/Adreno OpenCL 경로도 문서 확인 | **CHLOE native 엔진 미연결**. PC WAV 가져오기·블라인드 평가 지원. 공식 Python CPU 음성 생성 확인 |

공식 자료: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), [VoiceDesign 모델 카드](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign), [VoxCPM2](https://github.com/OpenBMB/VoxCPM), [VoxCPM2 모델 카드](https://huggingface.co/openbmb/VoxCPM2), [공식 모바일 앱](https://github.com/OpenBMB/MiniCPM-V-Apps), [CosyVoice](https://github.com/QwenAudio/CosyVoice), [CosyVoice3 모델 카드](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512).

CosyVoice3는 ‘Android에서 불가능’으로 단정하지 않는다. [qvac-fabric-speech.cpp의 CosyVoice3 문서](https://github.com/tetherto/qvac-fabric-speech.cpp/blob/master/engines/tts/docs/cosyvoice3.md)는 CPU와 Adreno OpenCL을 검증 경로로 설명하고, buffered 생성 후 콜백 분할은 첫 음성 지연을 줄이지 않는다고 명시한다. [audio.cpp](https://github.com/0xShug0/audio.cpp)에도 별도 CosyVoice3 포트가 있다. 이들 구현은 이번 CHLOE APK에서 컴파일·기기 검증하지 않았으므로 지원 완료로 표시하지 않는다. CosyVoice2나 sherpa-onnx의 다른 모델 지원을 CosyVoice3 지원으로 간주하지 않았다.

정확한 원본 revision·파일 크기·해시는 [sources.json](validation/tts-comparison/sources.json)에 있다. 파라미터 수는 언어 품질 순위가 아니다. VoxCPM2의 제작사 ASR 결과는 CHLOE 측정값으로 재사용하지 않았다.

## 저장 공간·메모리·모델 준비

모델은 Git/APK에 넣지 않는다. 개발 PC의 모델 다운로드는 허용하지만 앱 실행 중 다운로드나 클라우드 TTS는 없다. 모델/샘플은 파일 선택기로 가져와 앱 내부 저장소에 복사한다.

| 패키지 | 선택한 형식과 파일 용량 | RAM 해석 |
| --- | --- | --- |
| 기존 Sohee | talker 3,871,042,976 + tokenizer 358,980,384 bytes ≈ 4.23GB | 과거 폰 PSS 기록과 새 Lab 실측은 별도 |
| VoiceDesign | talker 3,871,042,496 + 같은 tokenizer ≈ 4.23GB | 기기 peak 미측정. 파일 크기가 RAM 사용량을 뜻하지 않음 |
| VoxCPM2 | BaseLM F16 3,247,980,544 + Acoustic F16 1,825,096,352 bytes ≈ 5.07GB | 공식 앱의 ≥6GB 권장은 Q4 BaseLM 구성과 연결됨. 이번 F16의 폰 RAM 검증은 없음 |
| CosyVoice3 | 선택한 LLM/flow/HiFT·frontend 구성 약 4.44GB | 호스트 커널 RSS high-water는 별도 결과에 기록. 폰 RAM은 미측정 |

VoxCPM2는 공식 앱이 지정한 [GGUF 저장소](https://huggingface.co/tc-mb/MiniCPM-V-Apps-gguf)의 F16을 선택했다. 용량을 줄이려고 Q4로 몰래 바꾸지 않는다. 모델은 하나씩 단계적으로 준비했고 VoiceDesign 원본 checkpoint는 변환·SHA 확인·호스트 smoke 성공 후 작업 공간 확보를 위해 정리했다. 변환된 모델은 보존한다. CosyVoice3도 이후 단계에서 필요한 checkpoint/frontend만 준비했다. 대체 llm.rl 및 중복 Qwen pretrained checkpoint는 내려받지 않았다.

VoiceDesign 준비(개발 PC, 네트워크 필요):

```sh
# 별도 가상환경에 scripts/model-requirements.txt와 CPU torch 설치
hf download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  --revision 5ecdb67327fd37bb2e042aab12ff7391903235d3 \
  --include config.json generation_config.json vocab.json merges.txt tokenizer_config.json model.safetensors \
  --local-dir work/voicedesign-original
python scripts/convert_talker_stable.py --input work/voicedesign-original \
  --output work/qwen-talker-1.7b-voicedesign-f16-stable.gguf
python scripts/prepare_voice_design.py \
  --talker work/qwen-talker-1.7b-voicedesign-f16-stable.gguf \
  --tokenizer models/chloe-sohee-1.7b-f16-stable/qwen-tokenizer-12hz-f16.gguf \
  --output models/chloe-voicedesign-1.7b-f16-stable
```

`huggingface_hub==0.36.2` 환경에서는 `hf` 또는 `huggingface-cli` 명령을 사용한다. 앱은 `design-pack.json`과 GGUF 두 개가 있는 폴더를 선택한다. 기존 CustomVoice를 이름만 바꿔 가져오는 방식은 metadata 검사로 거부한다. VoiceDesign에는 Sohee 이름을 지정하지 않으며 임의의 한국어 성인 여성 음색 설명을 쓴다. 같은 설명으로도 음색이 생성마다 달라질 수 있어 일관성 평가가 필요하다.

VoiceDesign 내장 speech tokenizer와 기존 별도 tokenizer의 원본 safetensors SHA-256은 `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258`로 같음을 확인했다. 기존 변환 tokenizer를 재사용한다. 모델/변환물 재배포 시 원본 Apache-2.0 라이선스와 출처·변경 고지를 함께 보존해야 한다. 원본 음성의 권리는 모델 라이선스와 별도다.

## Android 사용법

alpha7 Performance APK를 기존 Performance 앱에 업데이트한다. 패키지·서명이 같고 versionCode가 높아 가져온 기존 모델을 유지한다. 기존 화면의 **TTS Lab · 모델 비교 실험**으로 들어간다. 기존 추론 프로세스를 중지한 후 독립 `:comparison`을 사용하며 기존 모델 폴더는 덮어쓰지 않는다.

1. Sohee는 기존 1.7B 폴더를 그대로 사용한다. VoiceDesign은 별도 폴더를 가져온다. 미연결 모델은 생성 버튼이 비활성화된다. 수정한 지시를 공통 기본값으로 되돌리려면 해당 모델의 선택 칩을 다시 누른다.
2. 공통 20문장, seed 42·43·44, 스타일을 선택한다. `한 문장 생성`은 자동 재생하고, `20문장 × 3회`는 재생을 생략하며 개별 WAV/JSON을 보관한다.
3. 기본 공통 지시를 편집하거나 합격 표본을 적용하면 모델별 조정(`optimized`)으로 분류한다. VoiceDesign에만 음색 설계 설명이 추가되므로 완전히 동일한 conditioning은 아니다. 모델의 서로 다른 RNG에서 동일 seed는 동일 난수를 뜻하지 않는다.
4. 같은 문장·seed 10회는 모델 유지 상태에서 지연·PSS·온도 변화의 대리 시험이다. batch ID/회차/총 계획 수와 오류·취소를 저장한다. 실제 통화·음성 인식·에코 제거 부하를 포함한 시험은 아니다.
5. WAV, 성능·출처·오류 JSON을 사용자가 지정한 로컬 위치로 내보낼 수 있다. 비행기 모드에서 재시험한다. 앱에 INTERNET 권한이 없다.

모델 초기화/합성 예외는 UI에 표시하고, native abort·OOM은 독립 프로세스 연결 종료로 처리한다. 중지는 실험 프로세스만 종료한다. 120초 강제 제한은 넣지 않았다. 열 상태가 SEVERE 이상이면 시작/다음 실행을 막고 부분 결과를 보존한다.

## 블라인드 청취·평가

PC 샘플 폴더의 `comparison-manifest.json`과 개별 WAV를 함께 가져온다. 경로 탐색·해시 불일치·다른 원문·미등록 모델·비정상 WAV는 거부한다. WAV는 16/24/48kHz mono PCM16 원본을 사용하며 리샘플링·속도 조정·음높이 변경·무음 절삭을 하지 않는다. 사운드 차이가 평가에 영향을 줄 수 있으므로 같은 청취 음량/기기를 사용한다.

준비한 원본을 묶으려면 `python scripts/package_tts_listening.py --reference-wav artifacts/cosy-reference-42.wav`를 실행한다. 이 ZIP은 로컬 산출물이며 외부 업로드하지 않는다. 스마트폰에서 압축을 해제한 폴더를 가져오면 모델을 설치하지 않아도 네 모델을 비교 청취할 수 있다.

A/B 화면은 모델 이름·파일명을 숨긴다. 같은 문장·조건·seed·플랫폼의 서로 다른 모델끼리 무작위 순서를 만든다. PC와 Android는 같은 trial에 섞지 않는다. 6항목을 각각 1~5점으로 입력하고 문장 끝/쉼/강세/감정 메모를 남긴다. 미입력은 null, 입력할 때마다 내부 JSON에 저장한다. 정답 공개 이후의 평가는 공개 상태로 표시한다. 기본 blind export에는 clip ID와 점수만 있고, 공개한 trial에는 모델 식별도 들어간다. UI에서 미평가를 제외한 평균을 볼 수 있지만 자동으로 최종 모델을 선정하지 않는다.

| 모델 | 발음 | 억양·종결 | 일상 자연스러움 | 감정 | 여성 음색 | 안정성·일관성 |
| --- | --- | --- | --- | --- | --- | --- |
| Sohee | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 |
| VoiceDesign | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 |
| VoxCPM2 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 |
| CosyVoice3 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 | 미평가 |

과거 몇 개 합격 표본의 점수를 이번 20문장 전체 모델 점수로 확대하지 않는다. 같은 seed 3회/다른 seed 간의 음색 변동도 이어 듣고 일관성 점수를 판단한다. 무작위 pair가 반복될 수 있으므로 평가 clip ID로 중복을 확인한다.

## 성능 항목의 의미

- `model_init_ms`: 해당 worker의 실제 최근 로딩 시간. 재사용 시 `init_this_request_ms=0`, `model_reused=true`로 구분한다.
- `generation_ms`: 모델 전체 buffered 합성. `code_generation_ms`, `audio_decode_ms`도 분리한다. 오디오 길이와 RTF를 함께 기록한다.
- `first_pcm_ready_ms`: 전체 PCM 준비 시간. streaming 첫 청크는 구현하지 않아 null이다.
- 한 문장 자동 재생의 `first_output_ms`: 생성 시작 기준 AudioTrack 하드웨어 프레임 타임스탬프. `first_output_from_request_ms`는 초기화를 포함한 UI 요청 기준이다. 기기가 timestamp를 제공하지 않으면 null이다. 수동 재생은 별도 수동 지연이며 생성 지연으로 바꾸지 않는다.
- 실제 스피커에서 귀까지의 첫 소리 도달 시간은 외부 측정이 없어 null이다.
- peak PSS는 1초 샘플링 관측값이다. CPU는 worker CPU 시간(ms)을 기록한다. 전체 CPU/GPU 사용률은 측정하지 않아 null이다.
- 온도는 Android가 제공한 배터리 온도이며 CPU die 온도가 아니다. 열 상태, 충전 여부, 배터리 전류/용량, 시스템 RAM도 지원 범위에서 기록한다.
- 지속 통화 저하는 아직 미측정이다. 같은 문장 반복 결과로 발열에 따른 변화를 살피되 통화 시험 성공으로 표시하지 않는다.

S26 Ultra는 연결되어 있지 않아 이번 Lab의 실기기 측정은 아직 없다. 개발 호스트는 Linux x86_64 AMD EPYC 9V45 가상 CPU로 Windows/폰 결과가 아니다. 호스트 생성 중 다운로드·빌드 또는 다른 모델 smoke가 겹친 구간이 있어 속도 순위용 통제 실험으로 사용하지 않는다.

## PC 재현과 보조 CER

```sh
# 완전 로컬 추론. 모델은 먼저 준비한다. 각 문장을 42/43/44로 생성.
python scripts/tts_comparison.py --model Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice \
  --models models/chloe-sohee-1.7b-f16-stable --binary /path/to/qwen3-tts-cli \
  --output artifacts/tts-comparison-custom
python scripts/tts_comparison.py --model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign \
  --models models/chloe-voicedesign-1.7b-f16-stable --binary /path/to/qwen3-tts-cli \
  --output artifacts/tts-comparison-design
# 사용자 조정 지시는 반드시 별도 조건으로 분리
# --condition optimized --instruction "..." --output artifacts/another-empty-folder
# --resume는 기존 WAV 해시를 재검사하고 성공 항목을 건너뛴다.
```

VoxCPM2의 공식 앱 runtime은 `e0eca9d8f57ac8f5a5ad6191a8007b93436c1e71`다. 호스트 빌드에서 Apple 전용 F_NOCACHE를 POSIX 전체에 호출하는 문제가 발견돼, 원본 체크아웃은 수정하지 않고 build-directory overlay로 해당 캐시 힌트만 guard했다. 모델·오디오 연산 변경이 아니다. 비교 wrapper는 CPU 4스레드를 명시한다.

```sh
git clone --depth 1 --branch ios-omni https://github.com/tc-mb/llama.cpp-omni.git work/llama-omni
git -C work/llama-omni fetch --depth 1 origin e0eca9d8f57ac8f5a5ad6191a8007b93436c1e71
git -C work/llama-omni checkout --detach e0eca9d8f57ac8f5a5ad6191a8007b93436c1e71
cmake -S work/llama-omni -B work/vox-build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PROJECT_INCLUDE=/absolute/path/CHLOE/scripts/native/vox_compare.cmake \
  -DGGML_NATIVE=ON -DGGML_CUDA=OFF -DGGML_VULKAN=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_OPENSSL=OFF
cmake --build work/vox-build --target chloe-vox-compare -j2
python scripts/tts_comparison.py --model openbmb/VoxCPM2 --models models/voxcpm2-f16 \
  --binary /path/to/chloe-vox-compare --output artifacts/tts-comparison-vox
```

`vox-pack.json`에는 `model_id`, source GGUF revision, 두 파일의 name/size/sha256을 넣는다. 준비된 manifest는 검증 자료에 보관한다. F16+F16 두 파일만 다운로드한다. CPU wrapper와 Linux overlay는 이번 호스트 검증 경로이며 Windows 빌드는 미검증이다.

고정 GGUF 파일 준비(다운로드 단계):

```sh
hf download tc-mb/MiniCPM-V-Apps-gguf --revision 2a3a3ddfbfc3d8e98c1070680b2fa98df88c3452 \
  --include VoxCPM2-BaseLM-F16.gguf VoxCPM2-Acoustic-F16.gguf --local-dir models/voxcpm2-f16
```

공식 VoxCPM Python 경로는 `VoxCPM.from_pretrained(local_dir, load_denoiser=False)` + 괄호로 감싼 음색 설명, cfg=2.0 / inference_timesteps=10 / seed를 사용한다. `--binary`를 빼면 이 경로를 쓰지만 Python 어댑터는 이번 환경에서 실행하지 않았다. CosyVoice3는 공식 `AutoModel` / `inference_zero_shot` / `inference_instruct2`를 CPU FP32로 실제 실행했다. 참조는 특정 인물이나 사용자 통화가 아니라 이번 VoiceDesign에서 새로 만든 일반적인 성인 여성 합성 음성이다. 고정 문장 “반가워요. 편하게 이야기해 주세요. 저는 여기서 듣고 있을게요.”의 6초 seed 42 파일을 사용했다. 세 후보의 보조 ASR 원문 일치 여부를 확인했으며, 이는 사람의 자연스러움 합격 판정이 아니다. 참조 hash·생성법은 [synthetic-reference.json](validation/tts-comparison/synthetic-reference.json)에 있다.

Cosy 공통 조건은 고정 참조를 이용한 zero-shot이며 스타일 지시는 적용하지 않는다(`instruction_applied=false`). 조정 조건은 같은 참조의 `inference_instruct2`다. 따라서 다른 모델과 완전히 같은 conditioning이라고 주장하지 않는다. 기본 RAS sampling 및 flow noise buffer seed 0을 보존하고, 문장별 Python/NumPy/Torch seed를 42/43/44로 기록했다. 공식 frontend는 짧은 대상 문장에 비해 참조 텍스트가 길다는 경고를 출력했다. 짧은 참조·공식 Python 교차 검증이 다음 실험 대상이다. Transformers는 SDPA에서 sliding-window attention이 구현되지 않았다는 경고도 출력했다. 이번 실행의 실제 backend 경고로 기록하며, attention 구현 변경의 영향을 별도 재시험해야 한다.

공식 requirements의 CUDA/TRT/vLLM은 설치하지 않았다. Python 3.12 / Torch·Torchaudio 2.3.1+cpu / NumPy 1.26.4 / ONNX Runtime 1.18.0 / Transformers 4.51.3 조합이다. 추가 고정 목록은 [cosy-cpu-requirements.txt](../scripts/cosy-cpu-requirements.txt)와 [freeze](validation/tts-comparison/cosy-cpu-freeze.txt)에 있다. Matcha-TTS submodule도 sources.json의 commit으로 고정한다.

저장 공간 절약을 위해 `--cosy-config-only-init`로 Qwen2를 local config에서 구성한 다음 upstream의 **strict=True 전체 llm.pt 로딩**을 사용했다. pretrained checkpoint를 중복 읽지 않는 초기화 변경이며 최종 가중치 생략·양자화가 아니다. upstream 소스는 수정하지 않았다. 이 CPU 준비 방식을 기본 설치와 bitwise 동등하다고 검증한 것은 아니다.

Cosy의 필요한 파일만 내려받고, 검증에 사용한 pack metadata를 준비한다. 아래는 **개발 준비 단계**이며 앱에서 다운로드하는 명령이 아니다.

```sh
hf download FunAudioLLM/Fun-CosyVoice3-0.5B-2512 --revision 29e01c4e8d000f4bcd70751be16fa94bf3d85a18 \
  --include llm.pt flow.pt hift.pt speech_tokenizer_v3.onnx campplus.onnx cosyvoice3.yaml \
    CosyVoice-BlankEN/config.json CosyVoice-BlankEN/tokenizer_config.json \
    CosyVoice-BlankEN/vocab.json CosyVoice-BlankEN/merges.txt --local-dir models/cosyvoice3-reference
python - <<'PACK'
import json
from pathlib import Path
sources=json.loads(Path('docs/validation/tts-comparison/sources.json').read_text(encoding='utf-8'))
for key,folder,name in [('vox_gguf_pack','voxcpm2-f16','vox-pack.json'),
                        ('cosy_used_pack','cosyvoice3-reference','cosy-pack.json')]:
    dest=Path('models')/folder/name
    dest.write_text(json.dumps(sources[key],ensure_ascii=False,indent=2),encoding='utf-8')
PACK
```

runner는 실행 전에 pack의 크기·SHA-256을 검증한다. 원본 라이선스도 각 모델 폴더에 보존한다. Python CPU 의존성 설치에는 Linux compiler와 ffmpeg/libsndfile이 필요할 수 있다. Windows의 APK 빌드는 기존 README 절차를 따르고, 위 PC 모델 검증은 Linux 경로로만 확인했다.

```sh
# Linux CPU 참고 경로. Windows 설치는 미검증. 다운로드/패키지 설치는 준비 단계다.
python3.12 -m venv work/cosy-venv
work/cosy-venv/bin/pip install torch==2.3.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cpu
work/cosy-venv/bin/pip install setuptools==70.3.0 wheel Cython==3.0.12 numpy==1.26.4
CC=gcc CXX=g++ work/cosy-venv/bin/pip install --no-build-isolation openai-whisper==20231117 pyworld==0.3.5
work/cosy-venv/bin/pip install -r scripts/cosy-cpu-requirements.txt
git clone --recursive https://github.com/QwenAudio/CosyVoice.git work/CosyVoice
git -C work/CosyVoice checkout --detach 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git -C work/CosyVoice submodule update --init --recursive
PYTHONPATH=work/CosyVoice:work/CosyVoice/third_party/Matcha-TTS \
  work/cosy-venv/bin/python scripts/tts_comparison.py \
  --model FunAudioLLM/Fun-CosyVoice3-0.5B-2512 --models models/cosyvoice3-reference \
  --output artifacts/tts-comparison-cosy --reference-wav /local/synthetic-reference.wav \
  --reference-transcript '반가워요. 편하게 이야기해 주세요. 저는 여기서 듣고 있을게요.' \
  --reference-rights-confirmed --cosy-config-only-init
```

`cosy-pack.json`에는 실제 필요한 local 파일과 hash를 기록한다. [sources.json](validation/tts-comparison/sources.json)의 `cosy_used_pack` 항목을 따라 모델 카드의 고정 revision에서 llm.pt/flow.pt/hift.pt, speech_tokenizer_v3.onnx, campplus.onnx, cosyvoice3.yaml, CosyVoice-BlankEN의 config/tokenizer 파일을 준비한다. 참조 WAV와 텍스트는 정확히 일치해야 한다. 권리가 없는 사람의 음성을 참조로 쓰지 않는다.

선택적 CER:

```sh
# faster-whisper와 로컬 CTranslate2 Whisper 모델을 별도로 준비한 경우만 실행
python scripts/tts_asr_aux.py --model /path/to/local-whisper \
  --samples artifacts/tts-comparison-custom --output artifacts/custom-asr-aux.json
```

ASR도 local_files_only이며 클라우드에 WAV를 전송하지 않는다. CER은 NFC 한글 음절/문자·영문 소문자 기준, 공백·문장부호 제거 후 edit distance로 계산한다. 영문 약어의 올바른 한국어 읽기가 CER상 오답이 될 수 있다. 이번에는 `Systran/faster-whisper-small`의 고정 revision을 내려받고 CPU int8·한국어·beam 5·temperature 0·VAD off로 생성 샘플을 실제 전사했다. 모델 약 484MB이며 config/tokenizer/vocabulary.txt도 필요하다. faster-whisper 1.2.1 / CTranslate2 4.8.5 / PyAV 16.0.1로 고정했다. 원본 WAV는 수정하지 않았다. CER 수치와 전사 결과는 검증 JSON에만 보조 지표로 남긴다. 낮은 CER만으로 억양·감정·자연스러움을 합격시키지 않는다.

## 다음 단계와 미완료

1. 새 APK의 S26 Ultra UI/가져오기/단일 합성/중지/오류 복구를 비행기 모드에서 확인한다.
2. 같은 조건의 블라인드 청취를 저장하고, 문장 끝·긴 쉼·단어 강세·과한 감정이 나쁜 샘플을 개별 식별한다. 최종 모델은 이 평가 후 제안한다.
3. VoxCPM2 Android 통합은 별도 runtime·프로세스·ABI 충돌 검증이 필요하다. 현재 APK에 미검증 엔진을 넣어 기존 ggml을 바꾸지 않는다.
4. CosyVoice3는 더 짧은 합성 참조와 다른 참조 seed의 영향을 분리하고, 모바일 커뮤니티 경로는 별도 브랜치에서 빌드·실기기 검증한다. VoxCPM2는 공식 Python 결과와 GGUF runtime 결과를 교차 확인한다.
5. ASR의 한국어·영문 약어 오판을 청취로 확인하고, 여러 문장의 음색 일관성·long-run 반복 측정·실제 통화 부하 측정을 진행한다. 원격 서버·클라우드 TTS·인터넷 권한은 추가하지 않는다.
