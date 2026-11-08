# alpha1 구조

```
Compose MainActivity
  └─ LabViewModel ─── ModelStore (SAF → 내부 저장소, 크기/SHA-256, 원자적 적용)
       ├─ VoiceEngine → LocalVoiceEngine → Messenger IPC
       │                                  └─ :voice VoiceWorkerService
       │                                       └─ NativeBridge JNI → qwen3-tts.cpp → ggml CPU
       ├─ WavPlayer → AudioTrack (WAV 재생, 출력 timestamp)
       └─ LabLog / JSON 평가 기록
```

`VoiceEngine`은 모델 초기화·합성·중지만 노출한다. 음성 인식, 대화, 메모리, 원격 엔진은 구현하지 않았다. 향후 RemoteVoiceEngine을 넣을 때 모델과 오디오 전송 규약을 별도로 정의하면 화면과 대화 계층의 변경을 줄일 수 있다.

- 합성은 별도 프로세스의 단일 worker에서 순차 실행. C++ 객체를 동시에 호출하지 않는다.
- JNI C++ 예외와 Kotlin 오류를 처리한다. 네이티브 치명 오류는 UI 프로세스와 격리하지만 OS가 앱 전체를 종료하는 시스템 OOM까지 방지할 수는 없다.
- buffered 합성에 안전한 중간 취소 API가 없어 중지는 `:voice` 프로세스를 종료한다. 재생은 즉시 취소하고 다음 생성 전에 모델을 재초기화한다. 모델 파일은 보존된다.
- 앱이 배경으로 이동하면 진행 중인 생성과 재생을 중지한다. 화면 회전은 ViewModel을 유지한다. foreground service나 wake lock은 없다.
- INTERNET, RECORD_AUDIO, 광범위한 저장소 권한 없음. SAF 폴더 선택으로 복사하고 WAV/JSON 내보내기만 수행한다. 완전 오프라인 검증 시 로컬 파일 제공자를 선택한다.
- `files/models/active`, `files/audio`, `files/reports`, `files/logs` 사용. 앱 삭제/데이터 지우기는 모델과 실험 결과도 삭제한다. 필요한 결과는 먼저 내보낸다.
- 매초 worker PSS, native heap, Android 열 상태를 기록한다. PSS 최대값은 1초 간격으로 **관측한** 최대치이며 연속적인 절대 peak가 아니다. UI와 시스템 전체 메모리는 별도로 `adb shell dumpsys meminfo`로 측정한다.
- 오류, 생성 단계, 메모리를 logcat과 내부 JSONL에 남긴다. upstream stdout/stderr는 `files/logs/native.log`에 보존한다. 이 로그에는 입력 문장이 포함될 수 있다. 사용자 명시적 내보내기/ADB 외에는 전송하지 않는다.
- 평가 JSON은 생성별 UUID로 보관한다. WAV와 보고서는 재시작 뒤에도 남지만 alpha1 UI는 현재 세션의 마지막 결과만 표시한다. 과거 결과 탐색/삭제 UI는 다음 단계다.
```
RTF = native 생성 시간(ms) / (출력 sample 수 / sample rate × 1000)
```

첫 PCM 준비: 합성 버튼 → JNI의 완성 PCM 반환 시점. WAV 수신: 합성 버튼 → WAV 저장 및 IPC 완료. 첫 재생 출력: 합성 버튼 → AudioTrack 출력 timestamp로 역산한 첫 frame. 자동 재생에서만 기록하며 timestamp를 얻지 못하면 null. 후자는 Android 오디오 clock 추정값으로 블루투스 지연이나 스피커의 물리적 음향 도달까지 측정하지 않는다.
