# CHLOE Conversation Engine · alpha8

## 설계

기준 commit `ea7cedef9492a8ac45e81c8c40dff3d13efa93a6`에서 `feature/chloe-conversation-engine`을 만들었다. 기존 TTS JNI·VoiceWorkerService·모델 라이브러리·WavPlayer는 변경하지 않는다.

ConversationActivity → ConversationManager → PersonaManager/DialogueContextManager → AndroidLocalLlmEngine → Messenger → LlmWorker(:llm) → LlmNative. 기존 TTS의 ggml을 교체하지 않고 별도 Gradle native 모듈에서 공식 llama.cpp를 static 링크하고 archive symbol export를 숨긴다. 동일 NDK libc++ 하나를 패키징한다. 추후 원격 구현을 위한 ConversationEngine/LocalLlmEngine 경계만 두며 서버/API 구현은 없다.

VoiceDirector는 JSON 필수 키·타입·enum·길이를 검증한다. 유효한 spoken_text만 있으면 중립 fallback을 쓴다. JSON 조각·사고 과정·빈 결과·token cap 출력은 읽지 않는다. 자유 형식 tts_instruction는 검사 화면에 표시하되 TTS에 그대로 전달하지 않는다. TtsInstructionMapper가 intent/emotion/pace/energy/expressiveness를 제한된 한국어 지시로 바꿔 기존 LocalVoiceEngine에 보낸다. 이는 확률적인 자연어 conditioning이며 F0·들숨·웃음 위치의 정밀 제어가 아니다.

## 고정 모델과 지원 조사

원본 Qwen3.5-4B revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, 2B revision `15852e8c16360a2fea060d615a32b45270f8a8fc`, Apache-2.0. 공식 llama.cpp commit `aa75ff3239f9cc675b081697deda9e1b112345c6` (MIT)와 qwen35 모델 구현, 공식 Android 빌드 문서 확인.

GGUF는 원본 제작사 배포가 아닌 Unsloth 변환물이다. 4B Q4_K_M 2,740,937,888 bytes, 2B 1,280,835,840 bytes. 정확한 revision/출처/SHA는 assets/conversation-models.json에 있다. 파일 선택기에서 앱 내부 저장소에 복사하고 크기·SHA 검증 후 rename한다. 기존 파일은 덮어쓰지 않는다. runtime은 qwen35 architecture/Q4_K_M을 검사한다. 비전 mmproj는 쓰지 않는다.

내장 Jinja template를 common_chat_templates API로 적용하고 enable_thinking=false를 전달한다. 수동 ChatML로 대체하지 않으며 사용자 입력은 special-token 파싱을 끈다. JSON Schema를 grammar 경로에 전달하고 Kotlin에서 다시 검증한다. CPU4, context2048, 최대 생성384 tokens, greedy. context 초과 시 초기화를 안내한다. 메모리는 최대 4턴/1200자이며 장기 기억이나 요약이 아니다.

공식 출처:
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/Qwen/Qwen3.5-2B
- https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md

## 준비·사용

개발 PC에서 모델은 하나씩 준비한다. 앱은 모델 다운로드/클라우드 호출을 하지 않고 INTERNET 권한이 없다.

```bash
hf download unsloth/Qwen3.5-4B-GGUF --revision e87f176479d0855a907a41277aca2f8ee7a09523 --include Qwen3.5-4B-Q4_K_M.gguf --local-dir models/conversation-4b
hf download unsloth/Qwen3.5-2B-GGUF --revision f6d5376be1edb4d416d56da11e5397a961aca8ae --include Qwen3.5-2B-Q4_K_M.gguf --local-dir models/conversation-2b
git submodule update --init --recursive
./gradlew -PperformanceEdition=true :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

JDK17 / SDK35 / NDK28.2 / CMake3.22.1을 사용한다. Performance alpha8을 업데이트하고 Conversation Lab → 모델 선택 → GGUF 가져오기 → 비행기 모드 → 답변 생성. 기존 Sohee1.7B를 설치한 상태에서 스타일 음성과 기본 음성을 각각 재생한다. 기존 seed42/음색을 유지하며 기본 비교는 지시 없음이다. 발화는 220자 제한이다.

존댓말/반말은 UI 설정으로 지정한다. 사실성/일관성을 모델 프롬프트로 요구하지만 정확성을 보장하는 검증 모델은 없다. 검색·예약·전화 기능은 없다. 대화 로그는 기본 off/메모리 문맥만 사용한다. on이면 private conversation-log.jsonl에 입력/응답/LLM metrics를 1MiB 범위로 저장하고 off 전환 시 삭제한다. 외부 업로드·장기 메모리·대화 로그 내보내기는 구현하지 않았다. 별도 측정 내보내기는 raw 응답/입력 없이 최대 120턴의 성능·구조 검증 상태와 메모리 관측을 로컬 JSON으로 저장한다.

## 성능·메모리·안정성

기본은 LLM 요청 전에 TTS 종료 및 TTS 전에 LLM 프로세스 종료 요청, 해제 옵션을 끄면 상주시킨다. 이는 모델 상주 비교이고 CPU LLM/TTS의 동시 생성 파이프라인은 아니다. 종료는 비동기라 즉시 완전 해제를 보장하지 않는다. native abort/OOM은 별도 worker 연결 종료로 표시한다. 백그라운드/중지 시 작업을 끝낸다.

- load_ms: 새 모델 load/context 초기화, 재사용 0.
- first_token_ms: prefill부터 JSON 첫 토큰까지. 첫 발화·스피커 출력과 다름.
- generation_ms: prefill 포함 전체 생성. tokens_per_second는 prefill 포함 유효 생성률.
- llm_pss_kib: 응답 완료 worker snapshot, 피크 아님.
- UI 메모리: 같은 UID UI/LLM/TTS PSS를 1초마다 합산한 관측 최대. 순간 peak를 놓칠 수 있다.
- 10/30분 반복 버튼은 50문장 순회 → LLM → TTS → 재생. 실제 ASR/전화/에코 부하가 아니다. 실행 시간은 마지막 턴 때문에 초과할 수 있다.

현재 모델 가중치 미다운로드/기기 미연결로 실제 추론·동시 RAM·지연·10/30분 안정성은 미측정이다. 기존 TTS PSS와 GGUF 파일 크기를 더해 실제 RAM이라고 보고하지 않는다. 기본/상주 전략 및 4B/2B를 기기에서 같은 조건으로 측정한 후 채택한다.

## 회귀와 남은 작업

conversation-cases.json에 수다/위로/설명/정직성/문맥 50개를 작성했다. 문맥 그룹은 순서대로 시험한다. 단위 테스트는 50입력×두 선호 프롬프트 계약과 parser/fallback/매핑/history를 검사한다. **50개 실제 모델 대화 품질을 통과했다는 뜻이 아니다.** 사람 평가의 사실성/자연스러움은 null이다.

새 native 컴파일 중 디스크 부족 링크 실패가 발생해 이번 작업의 llm/.cxx만 정리하고 -g0로 심볼 크기를 줄였다. 기존 모델·샘플은 삭제하지 않았다. 최종 빌드 결과는 validation/conversation/build.json을 따른다. S26 Ultra의 모델 로드/문맥/음성 재생·오류 복구·원음 대비 스타일·메모리·발열은 아직 미검증이다. main 자동 병합하지 않는다.
