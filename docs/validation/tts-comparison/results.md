# 한국어 TTS 비교 · 실제 검증 결과

## 범위와 조건

Linux x86_64 / AMD EPYC 9V45 가상 CPU / 모델 CPU 4스레드의 **호스트 결과**다. S26 Ultra·Windows 결과가 아니며, 다운로드·빌드·ASR 부하와 일부 겹친 실행이 있어 속도 우승 순위를 정할 수 없다. 모델별 기본 sampling은 plan.json에 있다. Qwen/Vox는 매 WAV 별 프로세스 로딩, Cosy는 모델 재사용과 참조 frontend를 포함한다. 로딩 시간도 같은 cache·lifetime의 통제 시험이 아니다.

공통 20문장 × seed 42/43/44 × 네 모델 = 240 WAV. 공통 스타일의 의미를 맞췄지만 VoiceDesign/Vox에는 음색 설명이 추가되고 Cosy는 고정 합성 참조 zero-shot이므로 conditioning 자체는 동일하지 않다.

| 모델 | 공통 성공/계획 | 생성 중앙값 | RTF 중앙값 | 보조 micro CER |
| --- | --- | --- | --- | --- |
| Qwen CustomVoice / Sohee | 60/60 | 8.56초 | 2.44 | 6.89% |
| Qwen VoiceDesign | 60/60 | 9.78초 | 2.39 | 8.90% |
| VoxCPM2 F16 | 60/60 | 8.49초 | 3.17 | 48.50% |
| CosyVoice3 FP32 | 60/60 | 25.06초 | 8.13 | 7.77% |

모든 공통 생성의 프로세스/API 성공·유효 WAV는 확인했다. **이것은 발음·자연스러움 합격이 아니다.** 세부 샘플 시간·길이·해시·CER는 host-results.json, 실제 원본 WAV/전사 로그는 Git 제외 로컬 산출물에 있다. 생성 중 실패 0과 환경 준비 중 수정한 실패는 구분한다.

## 조정 실험

각 모델의 별도 지시문으로 ko01/ko11/ko12/ko13 × 세 seed를 생성했다. 최적 설정을 찾았다는 뜻이 아니며 전체 20문장 조정 시험도 아니다. 공통 조건과 섞지 않고 APK에서 “모델별 조정”으로 선택한다.

| 모델 | 조정 성공/계획 | RTF 중앙값 | 보조 micro CER |
| --- | --- | --- | --- |
| Qwen CustomVoice / Sohee | 12/12 | 2.48 | 0.00% |
| Qwen VoiceDesign | 12/12 | 2.35 | 0.00% |
| VoxCPM2 F16 | 12/12 | 3.12 | 3.92% |
| CosyVoice3 FP32 | 12/12 | 10.66 | 2.61% |

## 우선 청취할 항목

- VoiceDesign 공통 ko11의 길이가 seed별 20.96/6.40/7.12초로 크게 달랐다. ko01·ko12 등도 길이 편차가 있어 조정 조건과 번갈아 청취한다.
- VoxCPM2 공통 ko12는 13.76/23.52/1.12초, ko13은 2.08/17.92/17.92초였다. 보조 CER도 높았다. 이 특정 GGUF/runtime·긴 한국어 description의 문제인지, 모델 자체 특성인지 공식 Python과 교차 확인해야 한다. 전체 VoxCPM2 품질 열세로 일반화하지 않는다.
- Small Whisper는 영어 약어의 한국어 발음도 오답 처리할 수 있다. CER은 문장 끝 억양·긴 쉼·감정·여성 음색을 판단하지 못한다. 낮은 CER로 최종 모델을 선정하지 않는다.
- Cosy는 새 VoiceDesign 합성 참조를 고정 사용했다. 원래 Sohee와 같은 화자가 아니며, 음색/자연스러움은 아직 청취 평가하지 않았다. 짧은 대상 대비 긴 참조 텍스트 경고와 Transformers SDPA sliding-window 미구현 경고를 기록했다. 참조 길이/attention backend 영향은 별도 검증이 필요하다.

## 메모리·출력 지연·미측정

- Cosy 공통 batch 프로세스의 Linux /proc VmHWM 관측 최대 8,482,356 KiB (약 8.09 GiB). 커널 RSS high-water이며 Android PSS가 아니다. 초기화와 모델 상주를 포함하고 phone 요구 RAM으로 환산하지 않는다.
- Qwen CLI의 반올림 RSS snapshot과 일부 C++ 실행의 GNU time ru_maxrss는 별도 필드다. 계측 방법이 다른 값을 같은 peak 순위로 합치지 않는다.
- 호스트는 실제 스피커를 재생하지 않았다. 첫 하드웨어 출력·음향 도달·스트리밍 첫 청크·기기 온도·GPU 사용률·통화 지속 저하는 모두 미측정이다.
- 여섯 청취 항목은 전 모델 미평가(null)다. 기존 사용자가 합격한 표본의 점수를 이 모델 비교 전체 점수로 옮기지 않았다.

## 빌드·회귀 확인

- ARM64 Debug APK alpha7: 30,771,740 bytes, SHA-256 `103009602ee2e94efefc42fae4c1c6cbc64043672a5867951af87bcb3958fb8b`.
- Android 단위 테스트 28개, Python 7개 통과. Lint 오류 0 / 경고 11. AndroidTest APK는 빌드했지만 기기 미연결로 실행하지 않았다.
- INTERNET 권한 없음, 모델·음성 파일 미포함, 서명 확인, zipalign 16KB 및 모든 native PT_LOAD ≥16KB 확인.
- 기존 NativeBridge/JNI/VoiceWorkerService/VoiceEngine/ModelLibrary/WavPlayer 소스는 기준 commit 대비 동일하다. 호스트 baseline 60 WAV를 확인했다. 새 UI/기기 회귀 검증은 미실행이다.

## 준비 중 해결한 문제

- Vox 모바일 fork의 Linux F_NOCACHE 컴파일 오류: build-directory overlay로 Apple 전용 캐시 힌트만 guard, 원본 소스·모델 연산은 그대로 유지.
- Cosy CPU 준비: NumPy 2 ABI 충돌을 1.26.4로 해결하고 Python 3.12용 matplotlib/contourpy 고정. Whisper 빌드의 setuptools/pkg_resources와 pyworld compiler 문제를 별도 CPU 환경에서 해결. CUDA/TRT/vLLM은 사용하지 않았다.
- ASR vocabulary.txt 누락을 보완하고 PyAV 19 API 변경 문제를 실제 통과한 16.0.1로 고정.
- 이 준비 실패는 모델의 한국어 품질 점수나 최종 240개 생성 실패율로 계산하지 않았다.

## 현재 판단과 다음 실험

기존 Sohee 1.7B를 유지한다. 새 엔진으로 교체할 만큼의 사용자 블라인드 품질 근거가 아직 없다. 먼저 ko12/ko13의 공통·조정 조건을 듣고, 이어 감정·전화 대화 문장을 평가한다. 점수·메모를 저장한 후 모델 정답을 공개한다. 이후 상위 후보만 S26 Ultra 엔진 통합/동일 조건 실측을 진행한다. Vox/Cosy는 현재 Android native 통합이 아닌 PC 샘플 청취 경로다.
