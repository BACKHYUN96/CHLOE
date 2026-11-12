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

## alpha9 수정 후보

alpha8 사용자 실측에서 4회 모두 fallback이 보고되어 검증 완료 상태가 아니다. alpha9는 upstream chat session/sampling/parser 계약을 적용하고, 실패 안내의 기억 저장 및 자동 TTS를 차단한다. 로컬 `진단용 원문 보기`는 기본 off이며 생성 텍스트 8192바이트 이내를 표시한다. 이 원문에는 추론 내용이 있을 수 있으므로 자동 음성화하지 않는다. 내용 없는 측정 JSON에는 원문/사용자 입력이 없다. 요청마다 model/release_before_tts/polite/run_id를 남기며 PSS 관측 최대를 새로 시작한다. 1초 표본이므로 짧은 순간의 최대값은 보장하지 않는다. 기존 alpha8 최상위 model 필드만으로 과거 회차의 모델을 확정하지 않는다.

APK 업데이트 후 기존 GGUF/TTS 파일은 유지한다. 먼저 대화 초기화 → 인사 1회 → native_parse_status 및 evaluation 확인. 성공할 때만 다음 입력과 TTS를 시험한다. 실패 시 코드와 로컬 원문으로 원인을 좁힌다. 기기에서 성공하기 전까지 이 변경은 수정 후보이며, 속도나 음질 개선을 주장하지 않는다.

## alpha10 · 서비스 재연결

사용자 alpha9 측정 1회는 4B, `native_parse_status=ok`, `fallback=false`, 로드 581.6ms / 첫 토큰 19009.4ms / 전체 36460.8ms / 112토큰 / worker PSS 2934541KiB였다. 사용자는 앱 재실행 후 첫 응답만 나오며, 멈춘 상태에서 외부 모니터의 전력이 낮아지는 현상을 보고했다. 이 전력값은 앱 내 계측이나 GPU 사용 증명이 아니다. 측정 파일에는 완료된 1회만 있어 실패 요청의 위치를 직접 입증하지는 못한다.

소스에서 확인한 재연결 결함: 기존 `AndroidLocalLlmEngine.stop()`은 remote만 null로 만들고 bound=true를 유지했다. 작업 중 중지/초기화/모델 변경/화면 이탈/TTS 전 해제를 거친 뒤 요청하면 pending에 넣고도 `if (!bound)` 때문에 새 bind를 하지 않을 수 있었다. Android가 이미 연결된 서비스를 다시 통지할 의무도 없다. 따라서 실제 연산을 하지 않는 대기 상태가 만들어질 수 있었다. 이것이 기기에서 관측한 모든 실패의 유일한 원인인지는 추가 검증이 필요하다.

alpha10은 LlmRequestClient와 AndroidLlmChannel을 분리한다. 중지 시 기존 채널을 먼저 무효화하고 unbind하며, 다음 요청은 새 채널을 만든다. 살아 있는 연결은 연속 요청에서 재사용한다. 이전 채널 콜백과 이전 요청 ID의 응답은 무시한다. 서비스는 `accepted`/`inference` 단계를 보고한다. 연결·접수 15초, 연산 180초 watchdog은 오류로 종료하고 채널을 해제하여 다음 시도에서 재연결한다. native 한 번의 decode가 끝나야 한다는 제한 대신 기존 worker 프로세스 종료 경로로 취소한다. 이 제한은 응답속도 목표가 아니다. 실패 측정에는 failure_code와 request_stage가 남는다.

회귀 테스트는 연속 정상 요청, 중지 후 재연결, bind 전 취소와 늦은 콜백, 이전 응답 차단, 미접속 timeout 후 재시도, progress 시 예산 전환, disconnect 후 복구를 검사한다. fake transport 기반 상태 시험이며 실제 Binder/폰 실측을 대체하지 않는다. 4B 속도/발열 최적화, native 추가 변경은 이번 범위에 없다. 모든 native 라이브러리는 alpha9 APK와 동일함을 확인했다.

기기 시험: 앱을 끄지 않고 3회 연속 입력 → 중지/초기화 후 재요청 → 모델 변경 → TTS 재생 후 재요청. 실패 시 상태와 내용 없는 JSON을 내보낸다. 실제 기기 성공/10·30분 안정성은 아직 미검증이다. APK와 빌드 자료는 `validation/conversation/alpha10-build.json`을 따른다.

## alpha11 · 말투와 지연 계측

alpha10 사용자 제공 4B 결과 3회는 모두 parser ok/fallback false/한도 미도달이었다. 첫 토큰 19.19/23.86/28.41초, 생성 35.91/47.12/58.17초. 사용자 보고상 3회 성공이지만 각 요청의 load_ms가 모두 양수이고 prompt_tokens도 230/227/212로, 파일만으로 같은 문맥을 유지한 3회 warm 연속 대화나 TTS 후 재연결 성공을 확정하지 않는다. 세 번의 성공과 10·30분 안정성은 별개다. 뒤 회차의 토큰 수도 늘어 발열 하나로 지연 증가를 설명하지 않는다.

반말 persona에 역할/호칭과 무관한 말투 유지와 구체적인 예를 추가한다. 짧은 대화는 1~2문장으로 권하고 매번 질문을 강요하지 않는다. JSON 구조와 style enum은 보존한다. 실제로 사용하지 않던 자유형 tts_instruction은 빈 문자열로 생성하도록 요청한다. 실제 TTS는 이전부터 enum 매핑을 사용했으므로 음성 지시 경로는 같다. regex register_warning은 일부 존댓말 말끝을 잡는 보조 진단으로, 인용/명사 오탐 및 누락 가능성이 있다. 자동 어미 치환/재생성은 하지 않으며 실제 반말 일관성은 기기 응답으로 평가한다.

모델 객체에 종속된 chat template 분석 객체를 프로세스 내 재사용한다. 모델 변경 전에 reset하고 프로세스 종료 시 캐시는 사라진다. 각 응답 session과 sampler, 문맥 추론은 새로 생성하므로 생성 상태/KV를 재사용하는 기능은 아니다. template_cached/template_ms/tokenize_ms/prefill_ms/sampler_ms/decode_ms/decode_tokens_per_second/native_request_ms를 기록한다. 기존 tokens_per_second는 prefill 등을 포함하는 지표로 그대로 두고 decode 속도와 분리한다. 첫 토큰은 스피커 소리 지연이 아니다. 단계 계측은 모델 로드·템플릿·입력 연산·생성을 구분하는 자료이며 실기기 속도 개선 주장은 아직 없다.

메모리는 worker 자체 llm_pss_kib를 완료 시점 값으로 별도 표시한다. UI 측 Android PSS 합산은 누락/캐시/권한 제한을 배제할 수 없어 전체/진짜 최대값으로 부르지 않는다. app_total_peak_pss_kib는 null로 기록한다. 이전 alpha10의 UI 252MiB와 worker 약2.8GiB가 충돌한 문제를 숫자 보정이나 추정 합계로 가리지 않는다. 요청마다 history_turns를 기록해 초기화/문맥 유지 상태도 확인한다.

코드 회귀는 요청 완료 후 release/reset을 모사한 재연결을 확인하지만 실제 TTS 재생/Binder/기기 테스트는 아니다. 검증 순서: 업데이트 후 4B(또는 이미 준비한 2B)로 초기화 1번 → 인사/개발자 소개/이름 기억 질문을 초기화 없이 연속 입력 → 스타일 음성 재생 후 재요청 → 대화 초기화 후 재요청. history_turns=0/1/2, 말투, worker PSS와 각 지연 단계를 확인한다. 신규 기기 결과와 음성 청취, 10·30분은 미측정이다. 모델/양자화/CPU4/Sohee와 기존 TTS native는 유지한다.

## alpha12 · prefill 비교와 간결한 persona

alpha11 사용자 측정에서 prefill 27.8/38.8/54.8초, decode 약21~23초, template 5~11ms였다. 주요 비용은 입력 연산이므로 template cache만으로 해결됐다고 주장하지 않는다. Android/모델의 하이브리드 recurrent state에서 안전한 prefix 복구를 검증하지 않았으므로 이번에는 KV 재사용을 구현하지 않는다.

alpha12는 llama_set_n_threads(ctx,4,prefillThreads)를 매 요청 적용한다. 선택 가능한 prefillThreads는 4/6/8이며 기본4다. JNI/worker/client에서 값을 검증하고 request payload와 측정에 전달한다. n_threads_batch는 다중 토큰 입력용이며 단일 토큰 답변 생성 n_threads는 4로 유지한다. GPU offload/양자화/모델 변경은 없다. 고스레드가 더 빠른지 여부는 미측정이며 4가 더 좋을 수 있다. 실패 행에도 요청 설정을 남긴다.

간결한 프롬프트 기본 on. alpha11의 구체적인 개발자/선생님 예가 응답에 노출된 사용자 표본을 보고, 그 문구를 없애고 자기 이름/사용자 이름 구분과 내부 규칙을 대사로 설명하지 않는 규칙을 명시했다. alpha11 persona는 스위치를 끄면 그대로 사용한다. 프롬프트 전환은 문맥을 초기화한다. 기존 최대4턴/1200자 문맥, JSON Schema, enum 기반 TTS 매핑, 사고 과정 차단은 유지한다. 간결화가 사실성/말투를 개선한다는 실측은 아직 없다. 자동 대사 치환이나 숨은 재생성은 없다.

테스트: compact persona의 내부 역할 예 제거/자기소개/출력 계약/길이, compact에서도 문맥 보존, 요청별 스레드 전달과 허용 외 값 차단. 기존 재연결/파싱 테스트도 함께 실행한다. fake transport와 빌드가 실기기 속도·자연스러움 평가를 대체하지 않는다.

기기 비교는 모델·문장·문맥(초기화)·프롬프트·충전 여부를 고정해 입력 스레드4/6/8을 시험한다. 설정당 가능하면 3회 이상, 순서를 바꾸고 열 상태를 비슷하게 맞춘다. prefill_ms, prompt_tokens, decode_threads, native_request_ms, 실패를 함께 본다. 우선 4스레드에서 alpha11/compact를 비교한 뒤 compact로4/6/8을 비교하면 원인을 나눌 수 있다. 이후 초기화 없이 이름 기억/개발자 소개/자기소개, TTS 후 질문을 확인한다. 첫 토큰 지연과 실제 스피커 출력은 구분한다. 이 환경에는 기기 연결이 없어 실기기 개선/발열/10·30분은 미측정이다.

별도 로컬 학습 지시서 PR #13과 독립이며 이 앱 PR은 alpha11 #12 위에 쌓는다. 디스크 확보를 위해 Drive 업로드 확인된 과거 alpha10의 작업 생성 로컬 APK 사본만 정리했다. alpha11/기존 모델/사용자 데이터/소스는 보존했다.

## alpha13 · 직접 응답과 고정 비교

direct-v4 프롬프트는 사용자 이름 질문에 사용자 이름으로 직접 답하고, 자기소개/역할 설명 반복과 말투 전환을 피하도록 보강한다. 알려준 이름이 없다면 추측하지 않는 규칙을 포함한다. 기존 alpha12 compact-v3 및 alpha11 persona를 스위치로 보존한다. 전환은 문맥 초기화다. 자동 이름 추출/답변 바꿔치기/추가 LLM 재생성은 없다. 실제 품질 개선은 미측정이다.

동일 조건 비교 시작/다음 버튼은 가상 이름 '새봄'의 소개→개발자 역할→이름 기억→피곤함 4개 입력을 순서대로 실행한다. 첫 시작 때 문맥을 초기화하고 다음 버튼은 문맥을 유지한다. 각 답변을 읽고 다음 버튼을 누른다. 모델/말투/스레드/persona/해제정책 변경 시 진행을 거부하고 초기화 후 다시 시작하도록 한다. 일반 답변 생성은 비교를 종료한다. 같은 설정으로 다른 모델을 선택해 다시 시작하고 JSON을 저장한다. comparison_protocol/run/case_id로 결과를 연결하며 사람 평가 human_quality는 null이다. 이름 포함 여부와 불필요한 자기소개 탐지는 문자열 보조 신호로, 정확성/자연스러움 점수가 아니다. 실패 행에도 비교 식별자를 기록한다. 말투 경고 regex의 공백 경계 오류도 수정했다.

상태 재사용은 조사 결과 활성화하지 않았다. [실제 API 한계와 필요한 검증](conversation-cache-investigation.md)을 따른다. native 모델/정밀도/CPU/Sohee 라이브러리는 변경하지 않는다. alpha13의 빌드·단위 테스트가 실제 비교/음성 청취/속도 향상/장시간 안정성을 증명하지 않는다. 사용자 입력/생성 대사는 기본 측정 JSON에 추가하지 않는다. 고정 공개 fixture ID만 포함한다. 기기 연결이 없어 새로운 실측은 남아 있다.

최종 빌드 중 디스크 부족으로 Kotlin 쓰기가 실패해, Drive에 보관된 과거 작업 생성 alpha8/9/11 로컬 APK 및 이번 중간 사본을 정리한 뒤 빌드/테스트를 다시 통과했다. alpha12/모델/사용자 파일은 보존했다.

## alpha14 · 9B 추가 실험

ConversationModelPolicy로2B/4B/9B 허용 모델을 관리한다. 9B importer manifest/기기 공간 검사/64bit 파일 크기를 추가하고, 기존2B/4B context와 timeout을 유지한다. 9B의 짧은 context/해제 정책/긴 연산 timeout과 모델 고정 다운로드·실행 한계는 [9B 안내](conversation-9b.md)를 따른다. 실제 모델 가중치 로드/추론/피크RAM/폰 안정성은 미검증이다. 모델 파일은 APK/Git/Drive에 넣지 않았다.

## alpha15 LLM GPU·상주 비교

CPU 기준을 보존하면서 Vulkan16/최대 오프로딩, 명시적인 상주 선택, 문맥만 비우기와 cold/warm 측정을 추가했다. 정확한 구현 경계·PocketPal OpenCL과의 차이·설치/재현 및 미측정 항목은 [LLM GPU Lab](llm-gpu-lab.md)을 따른다. prefix cache, streaming, OpenCL, PC 서버는 이번 변경에 구현하지 않았다. 기존 공개 모델/Sohee/JSON 계약은 보존한다.
