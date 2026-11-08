# 0.1.0-alpha2 — AudioTrack 재생 초기화 수정

사용자가 제공한 SM-S948N / Android API 37 측정 기록에서 Sohee 한국어 합성은 완료됐지만 앱 화면에 `AudioTrack 초기화 실패`가 표시됐다.

- 입력: `안녕하세요?`
- 생성: 8706.77ms, 출력 3.36초 / 24kHz / 모노 / PCM16
- RTF: 2.5913
- 첫 PCM 준비: 8710.24ms, WAV 수신: 8715.17ms
- 관측 최대 worker PSS: 2,584,314KiB ≈ 2523.7MiB
- 첫 재생 출력: null. 소리가 재생됐다고 해석하지 않음.

이것은 첫 실기기 합성 측정이며, 한국어 청취 품질이나 기기 재생 성공의 증거는 아니다. 개인 기기 fingerprint와 원본 평가 JSON은 저장소에 복사하지 않았다.

## 원인과 수정

`AudioTrack.MODE_STATIC`은 생성 직후 `STATE_NO_STATIC_DATA`이고, PCM을 처음 성공적으로 쓰면 `STATE_INITIALIZED`로 바뀐다. alpha1는 쓰기 전에 `STATE_INITIALIZED`를 요구해 정상 상태도 오류로 처리했다.

alpha2는 생성 직후에는 `STATE_UNINITIALIZED`만 거부하고, PCM 전체 쓰기 성공 이후 `STATE_INITIALIZED`를 검사한다. 모델·화자·오디오 데이터·샘플레이트는 바꾸지 않는다. 진단 JSON에 앱 버전과 재생 오류를 기록한다.

이 상태 전이를 확인하는 기기용 회귀 테스트 `StaticAudioTrackTest`를 추가했다. 빌드 결과와 기기 테스트 실제 실행 여부는 최종 작업 보고에 구분한다. 연결된 기기가 없으므로 여기서 실제 재생 성공을 주장하지 않는다.

최종 검증: `assembleDebug`, 단위 테스트 7개, `lintDebug`(오류 0/경고 9), `assembleDebugAndroidTest` 통과. 기기용 테스트 APK는 빌드했으나 실제 실행하지 않았다. 버전 코드 2, 기존 alpha1과 동일한 서명 인증서를 확인했고 16KB ZIP 정렬 검사도 통과했다. APK SHA-256: `ea23bd75b6380fbda679936e5c8bc456b656a0187f6f2463b8b8f2e1ad70cfd1`.

## 업데이트 및 재시험

기존 앱을 삭제하지 말고 alpha2 APK를 업데이트 설치한다. 같은 개발 서명키를 사용하므로 기존 내부 모델을 보존할 수 있다. 설치 후 화면에 `0.1.0-alpha2`가 표시되는지 확인하고 초기화 → 같은 문장 합성 → 자동 재생 또는 재생을 시험한다. APK 설치 중 서명 충돌이 나타나면 삭제하기 전에 오류 내용을 확인한다.

Android Studio/ADB 사용 시:

```powershell
adb install -r CHLOE-Voice-Lab-0.1.0-alpha2-arm64-debug.apk
.\gradlew.bat :app:connectedDebugAndroidTest
```

소리가 들리지 않으면 새 측정 JSON과 WAV를 내보낸다. 첫 재생 timestamp는 기기에 따라 null일 수 있으므로 실제 청취 결과도 함께 기록한다.
