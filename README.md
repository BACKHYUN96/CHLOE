[TTS Lab 모델 비교 실험 · alpha7](docs/tts-comparison.md): 기존 CPU 엔진을 유지하며 20문장·3개 seed, 블라인드 평가와 독립 VoiceDesign 경로를 추가했습니다. 모델별 미통합·미측정 상태는 보고서에 구분합니다.

말투 기준 표본 선택: [alpha6 적용 안내](docs/VOICE_REFERENCES.ko.md). CPU 기준, 1.7B Sohee의 합격 표본 지시를 선택할 수 있습니다.

# CHLOE Voice Lab · 0.1.0-alpha7

alpha4는 CPU 스레드 선택·자동 비교와 온도/배터리/메모리 기록을 추가합니다. 별도 설치되는 성능판 빌드와 모델 가져오기·측정 방법은 [성능 측정판 안내](docs/PERFORMANCE_ALPHA4.ko.md)를 참고하세요. GPU 가속은 이번 APK에 포함하지 않습니다.

alpha3는 0.6B/1.7B Sohee 선택과 모델별 저장을 추가합니다. 기존 0.6B 모델은 업데이트 시 자동 보존됩니다. 1.7B는 별도 가져오기가 필요합니다. [1.7B 설치 안내](docs/ALPHA3.ko.md)를 참고하세요.

사용자 제공 기록에서 1.7B의 실기기 생성·재생을 확인했습니다. 청취 평가와 호흡 표현 요구사항, 속도 개선의 후속 방향은 [실기기 피드백과 음성 표현 방향](docs/VOICE_DIRECTION.ko.md)에 정리했습니다. 장시간 안정성·발열과 조건을 통제한 음질 비교는 추가 검증이 필요합니다.

호흡 표현의 후속 실험으로 1.7B Sohee 비교 음성 15개를 생성했습니다. [호흡 표현 비교 01](docs/BREATH_STUDY_01.ko.md)에 재현 방법과 측정을 기록했습니다. 청취 평가와 기기 재현은 대기 중이며 앱 기본값은 유지합니다.

alpha2는 static AudioTrack에 PCM을 쓰기 전 상태를 오류로 판단했던 재생 버그를 수정합니다. 기존 alpha1 위에 업데이트 설치하며 모델을 다시 받을 필요는 없습니다. 상세 내용은 [수정 및 기기 측정 기록](docs/ALPHA2.ko.md)을 참고하세요.

Android ARM64에서 **Qwen3-TTS 0.6B·1.7B CustomVoice / Sohee / 한국어**를 검증하는 개인용 오프라인 음성 실험 앱입니다. 전체 대화 AI의 구현에 앞서 음질과 실행 가능성을 평가합니다.

**1.7B의 실기기 생성·재생 기록을 확인했으며, 장시간 안정성·발열과 통제된 음질 비교는 추가 검증이 필요합니다.** 0.6B의 기기 측정과 alpha2 재생 수정 기록도 문서에서 별도로 확인할 수 있습니다. 최초 alpha1 결과는 [검증 기록](docs/VALIDATION.ko.md), 최신 기기 결과는 [음성 표현 방향](docs/VOICE_DIRECTION.ko.md)에 있습니다. 참고 Android 앱은 Base 모델을 사용하며 그것을 Sohee 지원으로 간주하지 않았습니다. [구현 경로 조사](docs/RESEARCH.ko.md)를 먼저 읽어 주세요.

상황에 따른 말투 선택을 위해 일상·놀람·공감·설명 12문장을 두 조건으로 비교하는 [상황별 말투 실험](docs/SITUATION_STUDY_01.ko.md)을 추가했습니다. 청취로 선호를 확인한 뒤 휴대전화에서 재검증합니다.

설명·놀람 피드백을 반영한 [수정 비교 02](docs/SITUATION_STUDY_02.ko.md)에서 신규 7개와 참고 원본 6개를 준비했습니다. 개선 여부는 청취 대기 중입니다.

## 앱 기능

- 한국어 문장 입력, 기본 테스트 10문장 선택
- SAF 폴더 선택 → 모델 복사·크기/SHA-256 검사 → 앱 내부 저장소 보관
- CustomVoice / 0.6B·1.7B / Sohee 메타데이터 확인 후 선택한 모델 초기화
- Sohee 한국어 합성, WAV 자동/수동 재생, 중지
- 생성 시간, 오디오 길이, RTF, 첫 PCM 준비·WAV 수신·첫 재생 출력 지연
- 매초 추론 프로세스 PSS/native heap/Android 열 상태 로그
- 발음·억양·리듬 1~5점 평가 및 메모, WAV/측정 JSON 내보내기
- 별도 추론 프로세스에서 예외와 치명적 네이티브 종료를 처리하고 재초기화 안내

APK에는 모델을 넣지 않습니다. 실행 중 모델 다운로드, 외부 API 호출, Android 시스템 TTS 대체는 없습니다. Manifest에 **INTERNET 권한이 없습니다**. 모델을 다른 목소리로 자동 대체하지 않습니다.

## Windows 빌드

필요: Android Studio, Git, JDK 17, Android SDK Platform 35, Build Tools 35.0.0, NDK **28.2.13676358**, CMake **3.22.1**. Android Studio의 SDK Manager에서 설치합니다. 모델 변환에는 Python 3.12와 여유 디스크 약 8 GB 이상을 권장합니다.

```powershell
git clone --recurse-submodules https://github.com/BACKHYUN96/CHLOE.git
cd CHLOE
git submodule update --init --recursive
```

Android Studio에서 이 폴더를 열면 `local.properties`에 SDK 위치를 설정합니다. 명령행에서는 `ANDROID_HOME`을 자신의 SDK 경로로 설정해도 됩니다. `JAVA_HOME`은 JDK 17을 가리키게 합니다.

```powershell
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Linux/macOS에서는 같은 명령의 `gradlew.bat`를 `./gradlew`로 바꿉니다. 빌드 산출물은 `app/build/outputs/apk/debug/app-debug.apk`입니다. ARM64만 포함하며 최소 Android 12/API 31입니다. Debug APK는 debuggable이고 추론 C++ 라이브러리는 Release 최적화로 컴파일합니다. 첫 빌드에는 개발 PC 인터넷이 필요하지만 설치 후 앱의 오프라인 실행과는 별개입니다.

별도로 제공하는 `CHLOE-0.1.0-alpha3-sources.zip`에는 C++/ggml 소스도 포함되어 있습니다. ZIP을 풀어 Android Studio로 열 수 있고 submodule 다운로드를 다시 할 필요가 없습니다. GitHub의 기본 “Download ZIP”은 submodule 소스를 포함하지 않으므로 재귀 clone 또는 별도 전체 소스 ZIP을 사용하세요.

다른 개발 PC에서 만든 Debug APK는 서명키가 다를 수 있습니다. 서명 불일치 시 기존 앱을 삭제해야 설치할 수 있으며, 삭제 전 WAV/JSON을 내보내고 모델 원본을 보관하세요.

## 모델 준비 — PC에서만 실행

공식 Hugging Face 고정 리비전에서 내려받고 submodule에 고정한 변환기를 사용합니다. GPU는 필요하지 않습니다. 약 2.5 GB의 원본 다운로드와 약 2.21 GB의 변환 출력이 생깁니다. **F16 + 코드 예측기 FFN down 투영 5개 F32** 형식입니다. 일반 F16 변환에서는 실제 NaN/종료 실패가 발생해 약 30 MiB의 F32 안정화를 추가했습니다. 더 낮은 정밀도로 양자화하지 않습니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r scripts\model-requirements.txt
.\.venv\Scripts\python.exe scripts\prepare_models.py
```

생성되는 `models/chloe-sohee-f16-stable/` 전체가 가져오기 패키지입니다.

| 파일 | 출처와 역할 |
| --- | --- |
| `qwen-talker-0.6b-customvoice-f16-stable.gguf` | [공식 0.6B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice), 텍스트 BPE·Talker·code predictor·Sohee 화자 메타데이터 |
| `qwen-tokenizer-12hz-f16.gguf` | [공식 12Hz Tokenizer](https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz), 오디오 디코더 |
| `model-pack.json` | 준비 스크립트가 생성하는 출처 리비전·파일 크기·SHA-256 매니페스트 |

공식 원본의 `config.json`, `generation_config.json`, `vocab.json`, `merges.txt`, `tokenizer_config.json`, `model.safetensors`와 Tokenizer의 `config.json`, `model.safetensors`를 PC에 받습니다. 앱은 위 GGUF 두 개와 매니페스트만 사용합니다. 모든 출처·라이선스와 고정 커밋은 [조사 문서](docs/RESEARCH.ko.md)에 있습니다. 임의로 Base GGUF 파일명을 바꿔도 Sohee 패키지가 되지 않습니다.

이미 내려받은 공식 체크포인트가 있다면 `--local-talker 경로 --local-tokenizer 경로`를 둘 다 지정할 수 있습니다. 로컬 덮어쓰기 사용 여부가 매니페스트에 기록되며 출처 파일의 진위는 사용자가 확인해야 합니다. SHA-256은 복사 손상을 검출하며 출처를 인증하는 전자서명은 아닙니다.

## 설치와 가져오기

1. 개발자 옵션의 USB 디버깅을 켜고 위 `adb install`로 설치합니다. APK를 폰에 복사해 직접 설치하는 방법도 가능합니다.
2. `models/chloe-sohee-f16-stable` 폴더를 USB/MTP로 폰의 `Download/CHLOE/SoheeF16` 등에 복사합니다. ADB도 가능합니다.

   ```powershell
   adb shell mkdir -p /sdcard/Download/CHLOE
   adb push .\models\chloe-sohee-f16-stable /sdcard/Download/CHLOE/
   ```

3. 앱에서 **폴더 가져오기** → `chloe-sohee-f16-stable` 하위 폴더를 선택합니다. Android는 Download 최상위 폴더 선택을 제한할 수 있으므로 해당 하위 폴더를 선택합니다. 클라우드 제공자 대신 휴대전화 로컬 파일을 선택합니다.
4. 복사·SHA 검사 완료 후 **초기화**를 누릅니다. 모델은 앱 내부 저장소 `files/models/active`에 복사됩니다. 복사 대상 공간 약 2.21 GB와 임시 여유 공간이 필요합니다.
5. 비행기 모드를 켜고 Wi-Fi를 끈 뒤 앱을 다시 실행해 초기화·합성을 시험합니다.

## 음성 테스트

기본 테스트 10문장을 열고 한 문장씩 선택 → 합성 시작 → 자동 재생 또는 재생 → 발음·억양·리듬 평가 → 평가 저장. 측정 JSON과 WAV를 내보내 문장별로 보관합니다. 평가는 생성 당시 입력에 연결됩니다.

- 안녕하세요? 저는 클로이예요.
- 오늘 하루는 어떻게 보내셨어요?
- 아, 진짜요? 그건 좀 신기한데요?
- 아니, 그게 아니라 제 말은요.
- 음... 잠깐만요. 제가 한번 생각해 볼게요.
- 와, 그거 정말 대단하네요!
- 오늘 많이 피곤하셨나 봐요.
- 그러게요. 저도 그렇게 생각해요.
- 아, 그건 조금 다르게 볼 수도 있겠네요.
- 네, 알겠어요. 언제든 편하게 이야기해 주세요.

처음에는 충전기를 분리하고 유선/내장 스피커로 시험합니다. 초기화 시간과 생성 시간은 별도입니다. 같은 문장을 3회 이상 실행해 첫 실행과 이후 실행의 차이, RTF, PSS, 열 상태를 비교하세요. 정확한 생성 조건은 F16 + F32 CP-down, CPU 4스레드, seed 42, 기본 temperature 0.9/top-p 1/top-k 50/repetition penalty 1.05입니다. 입력은 240자까지, 최대 1024 음성 토큰입니다. 상한 도달은 디코딩 전에 중단하고 오류로 표시합니다.

**중지**는 재생을 취소하고 추론 프로세스를 종료합니다. 다음 합성 전에 초기화가 필요합니다. 배경 이동 중 진행 중인 생성·재생도 중지합니다. 0.6B는 자연어 감정 지시를 지원하지 않으며 실시간 통화·스트리밍·마이크·일정·검색·전화 기능은 구현하지 않았습니다.

## 로그와 문제 확인

```powershell
adb logcat -s CHLOE.ui CHLOE.worker CHLOE.Native
adb shell dumpsys meminfo ai.chloe.voicelab
adb shell dumpsys meminfo ai.chloe.voicelab:voice
adb shell run-as ai.chloe.voicelab ls files/logs
adb shell run-as ai.chloe.voicelab cat files/logs/worker.jsonl
adb shell run-as ai.chloe.voicelab cat files/logs/native.log
adb shell run-as ai.chloe.voicelab ls files/reports
```

오류가 나면 화면 메시지, `native.log`, worker JSONL을 함께 확인합니다. 로그와 보고서에는 입력 문장이 포함될 수 있으므로 공유 전 내용을 확인하세요. 네이티브 프로세스 종료 후 UI가 유지되고 재초기화되는지도 확인합니다. 매니페스트만 있고 파일이 없거나 손상된 경우 폴더를 다시 가져옵니다.

세부 측정 정의와 저장 정책은 [아키텍처](docs/ARCHITECTURE.ko.md), 완료/미완료 및 다음 단계는 [검증 기록](docs/VALIDATION.ko.md)을 참고하세요.

VoxCPM2 로컬 LoRA 준비: [RTX 4070 SUPER 12GB · KSS 비상업 실험 안내](docs/voxcpm2-lora-local.md). 실제 PC 추론·학습·12GB 적합성은 아직 미검증입니다.
