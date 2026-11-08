# 0.1.0-alpha3 — 1.7B Sohee 추가

0.6B와 1.7B CustomVoice 모델을 앱 내부에 각각 보관하고 선택해서 초기화한다. 두 모델을 동시에 추론 메모리에 올리지 않는다. 모델 선택 변경 시 현재 worker를 종료해 메모리를 해제하고 새 모델을 초기화하도록 한다. 기존 alpha1/2의 `files/models/active`는 `files/models/0.6b`로 이름을 변경해 보존하며 가중치를 다시 다운로드할 필요가 없다.

1.7B 공식 출처: `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, revision `0c0e3051f131929182e2c023b9537f8b1c68adfe`, Apache-2.0. Talker hidden size 2048, code predictor hidden size 1024, Sohee ID 2864다. 0.6B와 동일한 고정 C++ 런타임을 사용하고 CustomVoice·Sohee·선택한 hidden size·F32 CP-down tensor를 확인한다. 1.7B 초기화에는 instruction capability도 확인한다.

## 모델 준비

```powershell
.\.venv\Scripts\python.exe scripts\prepare_models.py --variant 1.7b
```

결과 폴더: `models/chloe-sohee-1.7b-f16-stable/`.

- `qwen-talker-1.7b-customvoice-f16-stable.gguf`
- `qwen-tokenizer-12hz-f16.gguf`
- `model-pack.json`
- `LICENSE-Qwen-Apache-2.0.txt` (라이선스 고지, 앱 가져오기에는 추가 입력 불필요)

기존 0.6B 변환과 같은 F16 + 코드 예측기 FFN down 5개 F32 규칙을 적용한다. 1.7B도 이 다섯 투영은 F32로 보존해 낮은 정밀도 경로의 위험을 줄이며, 품질을 위해 가중치 양자화는 하지 않는다. 0.6B에서 이 방식이 필요했던 것과 1.7B의 호스트 검증 결과는 구분한다. 고정 upstream 변환기는 instruction 지원 값을 계산하지만 GGUF에는 기록하지 않아, 1.7B에는 이 값을 명시적으로 직렬화한다.

## 폰에서 설치

1. alpha3 APK를 기존 앱 위에 업데이트 설치한다. 앱을 삭제하지 않는다.
2. Drive의 1.7B 모델 폴더에서 `CHLOE-Sohee-1.7B.z01`~`.z35`와 `CHLOE-Sohee-1.7B.zip` **36개**를 모두 같은 폴더에 다운로드하고, ZArchiver 또는 PC 7-Zip으로 마지막 `.zip`을 열어 압축을 푼다. 압축 다운로드는 약 3.33GB, 압축 해제 모델은 약 4.23GB다.
3. 앱에서 **1.7B** 선택 → **폴더 가져오기** → 압축 해제한 모델 폴더 선택 → **초기화**.
4. 우선 말투 지시를 비워두고 짧은 기본 문장으로 합성·재생을 확인한다. 이후 말투 지시를 추가해 비교한다.
5. **0.6B**를 누르면 해당 기존 모델로 전환할 수 있다. 선택 전환 후 매번 초기화가 필요하다.

파일 두 개와 매니페스트가 한 폴더에 있어야 한다. 다른 모델의 폴더를 선택하면 거부하며 0.6B를 덮어쓰지 않는다. 각 모델의 패키지는 Tokenizer도 따로 포함한다. 최초 설치 중에는 다운로드·압축 해제·내부 복사 공간이 모두 필요하므로 1.7B 추가 시 충분한 여유 공간(약 15GB 권장)을 준비한다.

## 말투 지시와 비교

1.7B를 선택했을 때만 선택적인 말투 지시 입력이 표시된다. 예: `차분하고 다정하게, 친한 친구에게 말하듯`. 지시는 최대 240자이며, 0.6B에 지시를 보내면 명시적으로 거부한다. 말투 지시는 모델의 기능이지 원하는 감정을 항상 정확하게 구현한다는 보장은 아니다. 같은 텍스트·같은 seed·지시 유무를 나눠 청취해야 한다.

모델 선택과 말투 지시는 평가 JSON의 `model_variant`, `instruction`, `model_pack`에 기록한다. 모델을 바꾸면 화면의 이전 결과는 지우며, 이미 저장한 WAV/평가 JSON은 보존한다. 시작 시 모델 선택을 복원한다.

S26 Ultra의 1.7B 메모리·속도·발열·음질은 기기에서 검증해야 한다. 0.6B보다 빠르다고 가정하지 않으며, 메모리 부족이나 네이티브 종료가 발생하면 UI에서 오류를 표시하고 0.6B를 다시 선택할 수 있다. 원격 서버·인터넷 권한은 추가하지 않았다.

## 개발 검증

단위 테스트 13개 통과. 기존 0.6B 폴더 이전, 두 모델 공존, alpha2/alpha3 중단된 교체 복구, 1.7B 파일명과 매니페스트 일치 및 잘못된 경로/모델 거부를 검사했다. `assembleDebug`, `lintDebug`(오류 0/경고 9), `assembleDebugAndroidTest`가 성공했다. Debug 서명은 기존 alpha2와 같고 16KB ZIP 정렬도 통과했다. 기기 테스트 APK는 빌드만 했으며 실제 기기에서 실행하지 않았다.

공식 원본 `model.safetensors`는 3,833,402,552바이트이며 SHA-256 `38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137`을 공식 LFS 메타데이터와 대조했다. 변환 Talker는 3,871,042,976바이트, Tokenizer는 358,980,384바이트이며 합계 **4,230,023,360바이트**다. 두 모델을 별도 패키지로 보관할 때 0.6B+1.7B 합계는 약 6.44GB다.

호스트(Linux x86_64 / AMD EPYC / CPU 4스레드)에서 기본 10문장 모두 24kHz 모노 PCM16 WAV를 생성했고 토큰 상한 도달은 없었다. 출력 길이 2.24~4.40초, 평균 RTF **2.012**. 모두 RMS가 0보다 크고 PCM 샘플 포화는 없었다. 런타임 표시 RSS peak는 4.28~4.44GB였다. 같은 호스트에서 모델 압축 작업을 병행했으므로 이 수치는 정밀한 성능 비교용 벤치마크가 아니다. S26 Ultra 성능으로 해석하지 않는다.

말투 지시 `Speak warmly and gently, like a close friend, with natural pauses.`를 넣은 별도 시험도 성공했다. 로그에서 instruction 19 token을 실제로 전처리한 것을 확인했고, 2.80초 WAV를 생성했다. 말투 지시를 받았다는 검증이며, 지시한 감정이 자연스럽게 표현됐다는 청취 판정은 아니다. 기본/지시 음성 샘플을 함께 제공한다.

전체 측정과 출처·빌드 검증은 [alpha3 검증 파일](validation/alpha3/host-results.json), [말투 지시 결과](validation/alpha3/instruction-result.json), [모델 매니페스트](validation/alpha3/model-pack.json), [빌드 기록](validation/alpha3/build.json)에 보존했다. APK SHA-256은 빌드 기록을 참고한다. 개인의 기기 평가 JSON·음성 파일은 이 검증 파일에 포함하지 않았다.
