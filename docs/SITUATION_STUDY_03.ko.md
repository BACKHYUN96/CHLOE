# 설명·놀람 수정 비교 03

수정 비교 02의 사용자 청취 피드백을 반영한다. 신규 말투·대사 후보 6개와 기존 조건을 다시 생성한 대조군 5개를 비교한다. 합격한 차분한 공감형 surprise_01_C는 원본을 복사해 참고한다. 앱 기본값과 APK를 변경하는 작업은 아니다.

## 조건과 식별자

[실행 계획](validation/situation-study-03/plan.json)의 원문과 지시 전문을 사용한다. Sohee 1.7B CustomVoice / 한국어 / F16 + F32 CP-down, seed 42, CPU 4스레드, 기존 샘플링과 호흡 지시는 유지한다. ↗↘는 억양 방향이고 반복된 ?, !, ~는 말투·감정의 사용자 표현이다. 이를 원문에 자동으로 넣지 않는다.

| 새 후보 | 비교할 대조군 | 확인할 점 |
| --- | --- | --- |
| explanation_01_E | explanation_01_CTRL | 차분한 안내에 생기를 더하고 힘없는 인상 완화 |
| explanation_02_SMILE | explanation_02_CTRL | 발랄한 권유와 미소가 섞인 목소리 |
| explanation_02_LAUGH_ATTEMPT | explanation_02_CTRL 및 SMILE | 같은 원문으로 짧은 실제 웃음을 요청한 별도 조건. 실제 웃음 생성 여부는 청취 필요 |
| explanation_03_E | explanation_03_CTRL | 시간이에요 뒤 들숨 없이 오디오 길이와 비교하면으로 연결 |
| surprise_02_E | surprise_02_CTRL | 좋은 감탄을 유지하며 마지막 빠른데라는 단어만 상승 |
| surprise_03_gentle_WORD | surprise_03_CTRL | 잠깐을 잠깐만으로 한 글자 변경하고 나머지 지시·원문·문장부호 유지 |

CTRL은 수정 비교 02의 기존 지시(C, surprise_03만 D)로 새로 생성한 대조군이며 새 개선 후보를 뜻하지 않는다. 다른 후보들도 지시 효과를 개별 검증하며, 원하는 감정·웃음·무호흡 연결·음높이 곡선을 강제 제어하는 API로 취급하지 않는다. 원문 발음과 단어 누락·추가, 부자연스러운 웃음이 없는지도 확인한다.

정보 전달과 친근한 권유를 구분한다. 설명 전체에 상승 억양과 여운을 금지하는 규칙을 쓰지 않는다. 합격한 차분한 공감형을 억지로 들뜨게 바꾸지 않는다. 실제 웃음 시도와 미소 음성은 별개이며 녹음된 웃음 음원을 붙이지 않는다.

## 복원과 재현

새 실행 환경에서 소스와 고정 submodule을 복원하고, 이전에 보관한 모델을 복원했다. 분할 ZIP을 Info-ZIP으로 합친 결과가 잘못되어 검증에서 중단했고, 원본 36개 볼륨은 7-Zip 25.01 검사에 통과했다. 원본 분할 ZIP을 7-Zip으로 직접 해제한 뒤 두 GGUF의 크기·SHA-256을 기존 값과 대조했다. 잘못 합친 파일로 추론하지 않았다.

런타임 고정 커밋은 4562731dc612cb87b4cd1eedac275a17d1078773, ggml은 eced84c86f8b012c752c016f7fe789adea168e1e다. Linux CPU Release / GGML_NATIVE=ON으로 재빌드했고, CLI 바이너리 SHA-256은 이전 e34dc781e53cccfa760d2cce6e769de29f84e8f51e547d5eca0cb179457f2d2b와 일치했다. 모델 정밀도나 화자를 바꾸지 않았다.

```sh
python3 scripts/compare_situational_styles.py \
  --plan docs/validation/situation-study-03/plan.json \
  --binary /path/to/qwen3-tts-cli \
  --models models/chloe-sohee-1.7b-f16-stable \
  --output artifacts/situation-study-03-new
```

명령은 계획에 있는 11개 음성과 결과 JSON·빈 CSV를 생성한다. 비어 있지 않은 출력 폴더는 거부한다. 원본 참고 복사와 ZIP 포장은 별도다. 실행 계획의 파일 식별자, 출력 이름 충돌, 입력·지시 240자 제한을 추론 전에 검사한다. 모델 파일을 바꾸는 옵션은 계획 JSON으로 받지 않는다.

## 검증과 미완료

실행 계획의 6개 사례·11개 지시, 대조군과 기존 입력·지시의 일치, 잠깐만 조건의 한 글자 차이와 동일 지시, 공통 호흡 지시·240자 제한을 확인했다. 출력 경로 이탈·파일명 충돌·지시 길이의 검증 3개와 기존 PCM/공개 요약 검증 3개를 통과했다.

음질·발음·감정·실제 웃음과 지정 경계의 호흡은 청취 판정 대상이다. Android 빌드·폰 측정과 이어 말하기·동시 맞장구는 이번에 수행하지 않는다. 새 실행 계획과 helper는 개발 PC용이며 앱의 오프라인 동작과 네트워크 권한을 바꾸지 않는다.

## 생성 및 검증 결과

11/11개 정상 생성, 비무음, 24kHz 모노 PCM16, 포화 샘플 0개, 토큰 상한 미도달을 확인했다. 이 중 6개는 수정 후보, 5개는 기존 조건 대조군이다. native 생성 시간 범위는 8.234–17.818초, RTF 범위는 2.121–2.418다. Linux x86_64 AMD EPYC 9V45 기반 가상 CPU에서 추론 4스레드를 사용했다. 업로드를 병행한 진단값으로 Android 속도나 성능 최적화 결과를 뜻하지 않는다.

[대조군 비교](validation/situation-study-03/control-comparison.json)의 5개 모두 이전 WAV 해시와 일치했다. [실제 생성 기록](validation/situation-study-03/report.json)에는 입력·지시와 타이밍을 보관하고, [참고 원본 출처](validation/situation-study-03/reference.json)에는 합격 음성의 해시를 기록했다. 생성 시점의 청취 상태는 미평가이며 웃음·호흡·억양 개선을 판정하지 않았다.

Drive 패키지는 WAV 12개(수정 후보 6·대조군 5·합격 원본 참고 1), 안내 TXT·빈 평가 CSV·계획/결과/참고/대조군 JSON, 전체 ZIP이다. ZIP 내부 18개 항목의 CRC를 검사했다. 첫 출력 지연·폰 PSS·발열은 이번에 측정하지 않았다. Android 코드 변경이 없어 APK를 빌드하지 않았다.
