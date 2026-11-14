# 2026-11-14 PocketPal 공개 소스와 CHLOE 비교

**PocketPal은 참고할 가치가 있다.** 특히 모델별 템플릿/중단 조건, 유효 생성 설정 전달, content와 reasoning 분리, 종료/문맥 포화 표시가 CHLOE의 후속 검증에 도움이 된다. 다만 사용자가 경험한 긴 답변을 특정 엔진의 우월함으로 확정할 수는 없다. PocketPal의 모델/기본 생성 정책과 CHLOE의 음성용 제약부터 다르다. 이번에는 공개 소스 분석만 수행하고 앱/모델/기본값을 변경하지 않았다.

공식 `a-ghorbani/pocketpal-ai`의 커밋 [`33aca612c793dcaa728a5bb4f2243ac3371c6e6a`](https://github.com/a-ghorbani/pocketpal-ai/commit/33aca612c793dcaa728a5bb4f2243ac3371c6e6a)을 고정해 확인했다. 소스 package 버전은1.23.0이고 `llama.rn`0.13.0-rc.9를 사용한다. 공개 앱 코드는 [MIT](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/LICENSE)다. 코드 복사/포팅은 하지 않았다. 나중에 코드를 가져올 경우 해당 저작권/라이선스 고지와 별도 의존성/모델 라이선스를 각각 유지해야 한다. [package.json](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/package.json), [조사 파일/버전/경계](pocketpal-source-review-20261114/sources.json).

## 사용자가 알려 준 조건과 미확인 값

사용자는 PocketPal 모델을 **Qwen3.5-4B-Q4_0**, 변경 설정은 GPU 사용량을 높인 것뿐이라고 밝혔다. 이는 사용자 보고이며 설치된 앱/파일을 도구로 검사한 결과가 아니다. 앱 버전·가중치 SHA·실제 effective 생성 설정/system prompt는 미확인이다. 현재 공개 소스 기본값이 설치 버전/기존 저장 설정과 같다고 가정하지 않는다. 예를 들어 현재 소스에는 예전 n_predict1024를 새 기본값으로 옮기는 migration도 있다.

현재 PC 원본/adapter 실험은 **Qwen3.5-2B의 NF4**다. Android CHLOE의 [모델 명세](../../app/src/main/assets/conversation-models.json)는2B/4B **Q4_K_M**을 지원하며 파일별 크기/SHA를 고정한다. 실제 폰에서 현재 선택한 CHLOE 모델은 이번에 확인하지 않았다. 그러므로 PocketPal4B Q4_0 대 PC2B NF4는 모델 크기·파일·양자화·실행 경로가 다르며 앱만의 비교가 아니다. CHLOE Android4B를 사용하더라도 Q4_K_M과 Q4_0 파일을 동일 모델 artifact로 취급하면 안 된다.

## 소스로 확인한 차이

CHLOE 쪽은 이 PR의 Android 소스와 별도 PC 실험 설정이다. 설치된 APK의 실제 동작을 측정했다는 뜻이 아니다.

| 항목 | PocketPal 조사 커밋의 기본/경로 | CHLOE 현재 소스/PC 실험 |
| --- | --- | --- |
| 사용자 발화 길이 | CHLOE 전용220자 spoken_text 계약 없음 | persona에220자 이하, schema maxLength220, Kotlin 소비 측에서도 초과 거부 |
| 최대 생성 | n_predict=-1, EOS까지. 실제 문맥/stop/취소/자원 한계는 있음 | Android/PC 모두 max384토큰. JSON 메타데이터도 이 예산에 포함 |
| 샘플링 | temperature0.7/top_k40/top_p0.95/min_p0.05/seed-1 | 현재 Android temp0/seed42, PC greedy/seed42 |
| thinking | 기본 enable_thinking=true. 음성 응답 경로는 off hint를 적용 | 현재 Android/PC off |
| 문맥 | 기본 n_ctx2048, session 메시지를 역할별로 조립 | Android n_ctx2048, 최대4과거 턴 또는 합계1200 UTF-16문자; PC 해당 고정 과거만 제공 |
| GPU | n_gpu_layers 등 설정 가능, 실제 backend/device 지원에 좌우됨 | Android 소스 n_gpu_layers0 고정. PC 실험은 CUDA |
| 표시 | content/reasoning_content와 종료/제한/문맥 상태를 별도로 전달 | JSON을 파싱해 발화/음성 메타데이터를 소비하며 실패 출력은 안내로 대체 |

PocketPal의 출력/샘플링/thinking 기본값은 [completionSettingsVersions.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/utils/completionSettingsVersions.ts#L21-L48), 문맥/GPU 기본값은 [contextInitParamsVersions.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/utils/contextInitParamsVersions.ts#L217-L240)에서 확인했다. 이 표는 설치된 폰 설정을 읽어낸 것이 아니다.

CHLOE의 길이와 이력 제한은 [ConversationEngine.kt](../../app/src/main/java/ai/chloe/voicelab/conversation/ConversationEngine.kt), schema는 [conversation-schema.json](../../app/src/main/assets/conversation-schema.json),384토큰/문맥/CPU/greedy/thinking/JSON 경로는 [llm_jni.cpp](../../llm/src/main/cpp/llm_jni.cpp)에서 확인했다.220자 초과를 단순히 잘라 표시하는 것이 아니라 소비 검증이 거부할 수 있다는 차이도 있다.

이 설정 차이는 **긴 답변**에 대한 구체적인 설명 후보다. CHLOE는 짧은 음성 발화를 목표로 JSON의 발화 부분에220자 예산을 부여하지만 PocketPal 일반 채팅 기본값은 같은 계약을 요구하지 않는다. 출력 상한/샘플링/thinking을 달리하면 생성 분량/스타일이 달라질 수 있다. 그러나 소유자·문맥 정확성의 향상을 보장하지 않으며, GPU layer 수를 높이는 것은 가중치 학습/모델 크기 변경이 아니다. 실제 속도/발열/품질 효과는 폰에서 측정하지 않았다.

## 템플릿과 이력에서 참고할 점

PocketPal 기본 HF 모델 설정은 custom template를 비워 GGUF 템플릿을 쓰도록 두며 system prompt도 기본 빈 값이다. 별도의 Pal/system 설정이 있으면 우선 적용할 수 있다. 따라서 사용자의 실제 prompt를 모르는 상태에서 PocketPal에는 system prompt가 전혀 없다고 단정하지 않는다. [chat.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/utils/chat.ts#L439-L472), [systemPromptResolver.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/utils/systemPromptResolver.ts#L19-L37).

일반 chat 준비는 session의 메시지를 role 구조로 조립해 messages API에 전달한다. 이전 thinking의 문맥 포함 여부와 현재 thinking 허용을 별도로 다루며 음성 응답은 thinking off hint를 적용한다. 로컬 engine은 native content/reasoning_content와 stopped_eos/stopped_limit/context_full 등을 따로 반환한다. “생성 텍스트 전체”와 “사용자에게 말할 content”를 구분하는 구조는 참고하기 좋다. [useChatSession.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/hooks/useChatSession.ts#L131-L209), [completionEngines.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/api/completionEngines.ts#L16-L54).

ModelStore는 EOS metadata와 custom/GGUF 템플릿을 참고해 stop token을 수집한다. 모델별 템플릿/stop이 실제 요청에 반영되는지 확인하는 접근은 CHLOE의 parser/grammar prefill/lazy trigger 검증과 함께 활용할 수 있다. [ModelStore.ts](https://github.com/a-ghorbani/pocketpal-ai/blob/33aca612c793dcaa728a5bb4f2243ac3371c6e6a/src/store/ModelStore.ts#L3347-L3400).

CHLOE도 이미 GGUF 기반 upstream chat session/parser를 사용한다. 따라서 PocketPal의 화면/framework를 가져오거나 템플릿 함수만 교체하면 해결된다고 볼 근거는 없다. PC의 [기존 단일요인 대조](local-llm-runtime-ablation-report.md)에서는 JSON 제약 해제/템플릿 변경만으로 공통 내용 오류가 해결되지 않았고, [공식 text-only 경로 대조](local-llm-text-path-report.md)도 wrapper와 동일했다. 해당 PC 결과를 다른 GGUF·폰 runtime 전체에 일반화하지 않는다.

## 적용 후보와 검증 경계

다음 비교를 한다면 기존 자산을 보존하면서 **같은 GGUF SHA·질문·과거·system·템플릿·thinking·샘플링·출력 한도**를 양쪽에 맞추고 실제 effective 요청/종료 상태를 기록하는 것이 먼저다.220자 음성 계약과 긴 화면 답변은 별도 조건으로 비교해야 한다. 같은 파일을 가져올 수 있는 비교 앱 쪽에서 맞추면 기존 CHLOE 모델을 교체할 필요도 없다. 이후 모델4B/2B, thinking, 길이, GPU를 한 번에 하나씩 분리해야 한다.

소스 참고의 우선 후보는 유효 설정의 재현 가능한 기록, content/reasoning 분리, 종료/문맥 포화 표시, 모델별 template/stop 검증이다. 긴 화면 설명과 짧은 TTS 발화를 분리하는 설계도 검증 후보이나 이번에 구현하지 않았다. 일반적인 assistant 인칭 문제를 이름 치환이나 더 긴 출력만으로 해결했다고 보고하지 않는다.

**완료:** 공식 공개 소스/라이선스/고정 커밋 조사, CHLOE 코드와 비교, 사용자 보고 조건 구분. **미실행:** PocketPal 설치/실행·폰 설정 export/파일 SHA 확인·같은 GGUF 양 앱 실측·4B 다운로드·GPU 성능 측정·코드 포팅/앱 변경. 현재 요청의 다른 이름/물건 소유 실험은 기존 PC2B 조건에서 별도로 수행하며 이 조사 때문에 조건을 바꾸지 않는다.
