# CHLOE 기준 상태와 통합 순서

기록일: 2026-11-11. 이번 범위는 Phase 0 기준 감사와 Phase 0.5 LLM 출력 경로 수정이다. 마스터 지시서 전체 구현 완료가 아니다.

## 소스와 PR

원격 main은 fd9b5982466db52c65ded7f3436e94beb3fcb54c. 작업 시작 소스는 alpha8 73515a72c13dadb5aab32e3f58dbd1f791861f63이며 변경 사항은 없었다. GitHub 조회에서 #4 → #6 → #7 → #8 → #9가 아직 열린 종속 PR이었다. #5 GPU 실험은 이 계열과 별개이며 사용자 실측에서 느리고 불안정해 기본 경로로 채택하지 않는다. #2/#3 역시 열려 있으므로 순서 없는 일괄 병합을 하지 않는다.

이번 fix/conversation-template-parsing은 #9 기반 수정이다. main에는 Conversation Lab 자체가 없어, 현재 설치본을 고치기 위해 의도적으로 #9 위에 쌓는다. #9를 포함한 선행 변경의 검토/병합 전에는 독립적인 main 대상 수정으로 간주하지 않는다. 자동 병합하지 않는다.

## 보존하는 음성 기준

기존 Qwen3-TTS 0.6B/1.7B CustomVoice Sohee, F16 및 기존 CP down F32 예외 설정, 4 CPU 스레드, 음성 표본/평가/모델 가져오기를 보존한다. 이번 수정은 기존 TTS JNI, worker, ggml, 음성 라이브러리를 변경하지 않는다. 스타일의 자연스러움은 청취 기준이며 코드 빌드로 증명하지 않는다.

LLM: Unsloth Qwen3.5-4B/2B Q4_K_M, 개별 revision/바이트/SHA는 app/src/main/assets/conversation-models.json. llama.cpp aa75ff3239f9cc675b081697deda9e1b112345c6. CPU 4스레드, 문맥 2048, 생성 한도 384, greedy, thinking=false. 모델은 개발/파일 가져오기 단계에서만 준비하며 APK 실행은 오프라인이다.

## 사용자 alpha8 실측

사용자가 올린 두 측정 파일의 두 번째 파일은 앞선 3회와 새 1회를 포함한다. 중복 제거 후 4회이며 모두 fallback이었다. 인사에 같은 안내문이 반복되었다는 사용자 보고와 일치한다.

| 회차 | 로드 ms | 첫 토큰 ms | 전체 생성 ms | 토큰 | 생성 토큰/전체 초 | 한도 도달 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 621 | 6910 | 20938 | 121 | 5.78 | 아니오 |
| 2 | 0 | 10630 | 31977 | 135 | 4.22 | 아니오 |
| 3 | 2219 | 33986 | 66970 | 114 | 1.70 | 아니오 |
| 4 | 830 | 35492 | 144789 | 384 | 2.65 | 예 |

이 값은 개발 환경 재현이 아니라 Galaxy S26 Ultra 사용자 제공 측정이다. 기존 파일은 모델 선택을 최상위에만 기록하므로 각 회차를 4B/2B로 확정할 수 없다. TPS는 prefill 포함 전체 생성 시간 분모이며 decode 전용 속도가 아니다. worker PSS는 약 1.37/2.82 GiB 두 범위가 있으나 모델과의 대응을 추정하지 않는다. UI 최대 PSS는 비동기 1초 표본이며 진짜 최대값/동시 상주 메모리 증명이 아니다. 원문 출력은 측정 파일에 없으므로 실제 실패 원인은 아직 미확정이다. 대화/음성 원본은 Git에 넣지 않는다.

## alpha9 수정 후보와 통과 조건

alpha8 JNI는 common_chat_templates_apply 결과에서 grammar 문자열만 추출해 즉시 적용하고, 생성 텍스트를 템플릿 파서 없이 Kotlin에 보냈다. pinned upstream common/chat.cpp의 common_chat_session::apply_sampling 및 common/sampling.cpp는 lazy grammar trigger, preserved token, generation prompt prefill을 함께 처리한다. alpha9는 이 경로와 session.finish를 사용한다. 사고 과정은 파싱된 assistant content와 구분한다. 이 차이는 소스로 확인되었으나 4회 실패의 단일 원인이라고 확정하지 않는다.

형식 오류만 있고 spoken_text가 안전한 경우에는 제한된 스타일로 복구한다. 비어 있거나 불완전한 결과의 고정 안내문은 기억에 추가하지 않고 TTS/반복 시험도 시작하지 않는다. 내용 없는 측정 schema v2에 요청별 UUID, 모델, 해제 정책, 말투 설정, native 파싱 상태, 문맥 토큰 수, 실패 코드를 기록한다. 화면의 진단 원문은 명시적으로 켤 때만 보이며 기본 측정 export에는 포함하지 않는다. 선택한 대화 로그 저장은 별도 로컬 기능이다.

기기 통과 조건: 새 대화 인사 1회에서 native_parse_status=ok 및 evaluation.fallback=false 확인 → 서로 다른 짧은 입력 3회 → 2B/4B 각각 비교 → 기존 Sohee 재생 → 10/30분 안정성. 실패하면 로컬 진단 원문과 실패 코드를 확인한다. 같은 실패 APK에서 장시간 시험을 반복하지 않는다. alpha9 기기 결과는 아직 없다.

## 다음 단계와 경계

1. Phase 0.5 기기 통과 후에만 TTS 어댑터 최소 경계를 추가한다. 기존 Sohee를 첫 어댑터로 감싸고 모델별 지원 기능을 명시한다.
2. Supertonic / CosyVoice 3 / Pocket Korean은 공식 revision·한국어·라이선스·학습 지원·Android 실행 경로를 각각 재확인하고 하나씩 준비한다. 모델 크기로 우승을 결정하지 않는다. PC 참고 음질과 Android 실측을 구분한다.
3. 공통 문장/조건/seed/미평가 null, raw와 정규화 샘플, 사람의 블라인드 청취를 우선한다. 공개 음성의 학습 권한도 별도로 확인한다.
4. 독립 VAD/STT 후 반이중 대화 제어를 연결한다. 끼어들기는 AEC/재생 오인식 검증 이후다.
5. p50/p95, 실제 재생과 첫 청크 구분, 발열/메모리/10·30분을 검증한다. 첫 소리 2초/RTF<1은 목표이고 현재 달성값이 아니다.

현재 환경에는 장치/GPU가 연결되지 않았고 선택 GGUF를 추가 저장할 공간도 부족하다. 사용자 PC(4070 SUPER 12GB)의 학습/서버 기능은 직접 실행하지 않았다. 기존 모델·사용자 파일은 삭제하지 않았다.
