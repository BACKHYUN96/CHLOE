# CHLOE Voice Lab 구현 경로 조사

조사일: 2026-11-08. 아래는 소스에서 확인한 범위이며 휴대전화 실행 성공과 구분한다.

## 원본과 고정 버전

| 대상 | 확인한 버전 / 라이선스 | 확인 내용 |
| --- | --- | --- |
| [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS/tree/022e286b98fbec7e1e916cb940cdf532cd9f488e) | `022e286b98fbec7e1e916cb940cdf532cd9f488e`, Apache-2.0 | 공식 Python/PyTorch 구현. Android 런타임 자체는 제공하지 않음 |
| [공식 0.6B CustomVoice 모델](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/85e237c12c027371202489a0ec509ded67b5e4b5) | `85e237c12c027371202489a0ec509ded67b5e4b5`, 모델 카드 Apache-2.0 | `tts_model_type=custom_voice`, `tts_model_size=0b6`, `spk_id.sohee=2864`, `codec_language_id.korean=2064` |
| [공식 12Hz 음성 Tokenizer](https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz/tree/7dd38ad4e9bad454aae9cd937d0cd577604fe229) | `7dd38ad4e9bad454aae9cd937d0cd577604fe229`, 모델 카드 Apache-2.0 | 음성 코드를 24 kHz 오디오로 디코딩하는 가중치. 텍스트 BPE와 별개 |
| [Danmoreng Android 앱](https://github.com/Danmoreng/qwen3-tts-android/tree/35738304b31c425cc08fb5405372fedfd6531b3b) | `35738304b31c425cc08fb5405372fedfd6531b3b`, MIT | 기본 모델은 `qwen-talker-0.6b-base-Q4_K_M.gguf`. 음성 프로필은 녹음 기반 embedding. 이 앱을 Sohee 지원 앱으로 간주하지 않음 |
| [앱이 고정한 C++ 런타임](https://github.com/Danmoreng/qwen3-tts.cpp/tree/4562731dc612cb87b4cd1eedac275a17d1078773) | `4562731dc612cb87b4cd1eedac275a17d1078773`, MIT | CustomVoice 메타데이터 변환, named speaker, 한국어 언어 ID, CPU 경로 존재. README의 명시적 CustomVoice 설명은 1.7B 기준 |
| [ggml](https://github.com/ggml-org/ggml/tree/eced84c86f8b012c752c016f7fe789adea168e1e) | `eced84c86f8b012c752c016f7fe789adea168e1e`, MIT | ARM CPU 커널. JNI/CMake는 NDK r28c로 ARM64 빌드 |

공식 README의 Sohee 설명은 “Warm Korean female voice with rich emotion.”이다. 공식 0.6B CustomVoice는 9개 고정 화자를 제공하지만 **자연어 instruction 제어를 지원하지 않는다**. 1.7B의 감정 지시 기능을 0.6B에 적용했다고 표시하지 않는다. 문장 부호나 텍스트가 억양에 미치는 효과 역시 실제 청취로 평가해야 한다.

## 확인한 실제 코드

- Android `README.md` 및 모델 관리 코드는 Base Q4_K_M 패키지 사용. 녹음 참조 화자와 고정 Sohee는 다르다.
- C++ `scripts/convert_tts_to_gguf.py`는 모델 유형, 0.6B/1.7B 크기, `talker_config.spk_id`를 읽고 `qwen3-tts.codec.speaker_names/ids`에 저장한다. 텍스트 tokenizer vocab/merges도 Talker GGUF에 넣는다.
- `src/transformer/transformer_loader_metadata.cpp`는 화자 이름/ID를 읽는다.
- `src/transformer/transformer_embeddings.cpp`의 `resolve_named_speaker`는 이름을 정규화한 뒤 codec embedding에서 해당 ID의 벡터를 사용한다.
- `src/pipeline/pipeline_synthesize.cpp`는 named speaker 조건부 합성 경로를 가진다.
- `src/pipeline/pipeline_models.cpp`는 명시적인 Talker 파일 선택을 허용하고 음성 tokenizer GGUF에서 디코더를 로드한다. CustomVoice 고정 화자에는 Base 화자 인코더나 참조 녹음이 필요하지 않다.
- 한국어 언어 ID는 공식 모델 설정과 CLI 모두 `2064`이다.

## alpha1에서 추가한 연결

기존 Android 앱 전체를 복제하지 않고 새 Compose 앱을 작성했다. Android 앱의 CMake 소스 목록을 MIT 고지와 함께 재사용하고 C++/ggml을 submodule로 고정했다. 자체 JNI에서 다음을 수행한다.

1. 고정 파일명으로 0.6B F16 Talker 선택. 임의 Base 파일 탐색 금지.
2. GGUF `model_type=custom_voice`, hidden size 1024, 화자 `sohee=2864`를 사전 검사.
3. 로드 후 런타임 capabilities와 available speakers를 재확인.
4. `tts_params.speaker="sohee"`, `language_id=2064`, seed 42, CPU 4스레드로 `synthesize` 호출.
5. 완성된 PCM을 WAV PCM16으로 저장. OOM/abort/segfault는 별도 `:voice` 프로세스에 격리하고 UI에서 재초기화 안내.

0.6B CustomVoice를 지원한다고 README만 보고 확정하지 않는다. 실제 변환·호스트 추론·Android 빌드·ARM64 기기 청취의 검증 결과는 `VALIDATION.ko.md`에 각각 기록한다. 호스트 추론은 Android 추론을 보증하지 않는다.

## 형식과 품질 선택

공식 safetensors를 그대로 Android에 넣어 ggml로 실행할 수는 없다. **동일 런타임의 변환 스크립트**로 Talker와 12Hz 음성 Tokenizer를 각각 F16 GGUF로 만든다. GGUF라는 확장자만 같아도 다른 변환기의 tensor 이름과 메타데이터는 호환되지 않을 수 있다.

alpha1는 **F16 + 코드 예측기 FFN down 투영 5개 F32** 기준이며 Q4/Q8로 자동 변경하지 않는다. 원본 BF16 행렬을 F16으로 변환하므로 bit-exact 원본 보존은 아니고, 작은 tensor도 변환기 규칙에 따라 F32를 유지한다. 최종 청취 품질 동등성은 검증 전이다. Android 오디오 출력용 PCM16 인코딩은 모델 가중치 양자화와 다르다.

초기 일반 F16 실행에서 코드 예측기의 첫 frame CB1~CB15 logits가 전부 NaN이 됐고 짧은 문장도 1024 frame 상한까지 이어졌다. ggml 평가 callback으로 최초 비정상 연산을 `code_pred.blk.2.ffn_down.weight`의 matmul로 좁혔다. 입력 토큰·화자 embedding은 공식 Python과 같았고 Talker 첫 logits의 cosine은 약 0.99999995였다. FFN down 5개를 F32로 보존하자 코드 예측기 logits가 유한해졌고 첫 세 단계의 공식 FP32 기준 argmax와 일치했다(max absolute difference < 0.019, cosine > 0.9999996). 같은 seed 42 / temperature 0.9 문장이 58 frame / 4.64초로 종료했다.

`scripts/convert_talker_stable.py`가 고정 upstream 변환기를 상속해 이 5개 행렬만 F32로 보존한다. 약 30 MiB가 추가되며 모델 변경·음색 대체·속도를 위한 정밀도 축소는 하지 않는다. JNI는 해당 5개 tensor의 실제 GGUF type까지 검사해 기존 불안정한 일반 F16 패키지를 거부한다. 캐시 0 초기화만으로는 오류가 해결되지 않았으며 해당 실험 변경은 최종 런타임에 포함하지 않았다.

현재 전체 문장 생성 후 재생하므로 첫 출력까지 생성 전체를 기다린다. 런타임에는 별도 streaming API가 있지만, 청크 경계와 음색/억양 동일성을 검증하기 전에 켜지 않는다. 속도보다 품질 우선이라는 요구사항을 따른 기준선이다. 통화, 실시간 맞장구, 말 끊기 대화 제어는 이 실험 APK 범위가 아니다.

## 라이선스

Qwen 코드와 공식 모델 카드는 Apache-2.0, C++ 런타임·ggml·참고 Android 앱은 MIT다. 모델 다운로드 시 해당 고정 모델 카드와 약관을 함께 보관해야 한다. 공식 저장소 LICENSE와 사용한 MIT 고지를 `third_party/licenses/`에 보존했다. APK에는 모델 가중치를 넣지 않는다. 특정 서비스 음성, 녹음, 독점 기술은 사용하지 않았다.
