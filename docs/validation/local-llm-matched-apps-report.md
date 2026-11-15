# 동일 4B GGUF의 PocketPal·CHLOE 기기 비교

2026-11-15 후속: 아래 기록 뒤 [사용자 사실 주체·기능 한계 정책](local-llm-grounding-policy-report.md)을 앱 소스에 구현하고 같은54질문으로 대조했다. 새 추론13+무변경41재사용, 최종 엄격 통과15→21이며 재학습/원본 앱 업데이트는 없었다. 아래는 해당 실험 당시 기록이다.

2026-11-15 실제 기기 수집·직접 GPT 평가 완료. **같은4B GGUF라도 추론 경로의 grammar/prefill 연결이 본문 전달을 깨뜨릴 수 있었다. 그러나 그 연결을 보정한 뒤에도 이름·소유자·정직성·반복 오류가 남았다.** 재학습이나 기존 모델 교체는 하지 않았다.

| 조건 | 기록된 생성 | 공통 JSON/소비 계약 | 전달 본문 품질: 통과 / 부분 / 실패 |
| --- | ---: | ---: | --- |
| 설치 alpha15 CHLOE 경로 | 54 | 54/54 | 15 / 20 / 19 |
| 설치1.22.0 PocketPal 경로, 공통 strict JSON preset | 54 | 0/54 | null — 전달 본문 없음 |
| PocketPal root-only 보정, 별도 탐색 조건 | 54 | 54/54 | 18 / 16 / 20 |

총162개는 두 앱 기본 비교108개와 보정54개다. 보정 첫 진단4개를 다시 더하지 않는다. 제외한 초기 pilot/열 중단 시도까지 포함한 전체 시도 수가162라는 뜻은 아니다. 원래 PocketPal의 raw JSON 꼬리는 발화 성공이나 품질 점수로 세지 않았다.

[집계](matched-apps-20261115/summary.json) · [질문/CHLOE 실제 발화/개별 판정](matched-apps-20261115/responses.json) · [보정된 실제 발화/판정](matched-apps-20261115/corrected.json) · [요청 감사](matched-apps-20261115/input-audits.json) · [쌍별 변화](matched-apps-20261115/paired-overall.json) · [보존/검증](matched-apps-20261115/checks.json) · [고정 소스](matched-apps-20261115/sources.json)

## 비교 범위

2026-11-15 연결된 SM-S948N(S26 Ultra), Android17에서 확인한 실제 설치 버전은 CHLOE0.1.0-alpha15/versionCode15, PocketPal1.22.0/versionCode158이다. 이전 [PocketPal 소스 조사](pocketpal-source-review-report.md)의1.23.0과 구분한다. 잘못 연결됐던 S20+는 본 비교에서 제외했다.

두 앱 모두 기존 클로이의 **Qwen3.5-4B Q4_K_M**,2,740,937,888bytes, SHA256 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`의 복사본을 사용한다. 사용자가 평소 PocketPal에서 사용한4B Q4_0과 동일 파일이라고 주장하지 않는다. 그 파일과 기존2B 원본·10-step adapter는 유지한다. 이번에 학습·adapter 적용·merge·GGUF 변환·모델 다운로드는 하지 않는다.

기존 앱의 APK를 백업하고 별도 패키지 두 개를 새 시험 key로 서명했다. 원본 DEX/native/assets/resources.arsc/res/의 entry 집합과 바이트를 검사했다. 바뀐 범위는 manifest·APK 서명과 META-INF metadata다. source APK의 signing stamp는 재서명 과정에서 제거된다. 원본 패키지의 설치·설정·대화·모델을 덮어쓰지 않는다. 클로이의 private 설정·로그 백업은 Git 제외 경로에 보관한다.

체크아웃의 Android alpha11을 폰에 설치하지 않고 실제 alpha15 APK를 사용했다. alpha15 참조 소스는 [`f7870d9`](https://github.com/BACKHYUN96/CHLOE/tree/f7870d935a698d8eadf7c06373a19ff7e75ec33c)이며, 소스 재빌드로 APK의 provenance를 증명했다는 뜻은 아니다. 실제 비교는 APK·native payload SHA로 고정한다. PocketPal 참조 소스는 [`8932367`](https://github.com/a-ghorbani/pocketpal-ai/tree/8932367e9f4a373945993ae0a472c8768d5c0578), 사용 라이브러리는 llama.rn0.13.0-rc.9, 관찰한 build11960/commit8642541이다. 클로이는 native 응답에 runtime `aa75ff3239f9cc675b081697deda9e1b112345c6`을 보고한다.

## 공통 요청과 측정 경계

기존50질문을 실행 전에 고정했고, 기존 보충4질문도 새 보충 출력을 보기 전에 추가했다. 보충 추가는 첫 기본 실행 이후이므로54개 전부를 처음부터 사전 등록한 것으로 표시하지 않는다. 모든 질문은 두 앱에 같은 말투·system·실제 JSON Schema·이력으로 전달한다. 원래50개는 변경하지 않았으며 전체 입력 생성기와 추가 시점은 [계획](../../training/configs/matched-apps-plan.json)에 있다.

| 항목 | 공통 요청 |
| --- | --- |
| 모델 | 같은4B Q4_K_M bytes/SHA |
| 말투 | 홀수 반말·짝수 존댓말, 앱 alpha15 direct persona |
| 생성 | temp0, seed42, 최대384토큰, thinking=false |
| 문맥·연산 | context2048, batch256, threads4, GPU layers0 요청 |
| 출력 | 같은 JSON Schema, spoken_text220자 이하, tts_instruction 빈 문자열 |
| 이력 | 독립 질문. 회상은 올바른 사용자 사실과 중립 assistant 이력을 고정. 생성 답변을 다음 조건에 재사용하지 않음 |

두 앱의 native 구현·커널·템플릿/grammar 연동은 서로 다르며 그 차이 자체가 측정 대상이다. 전체 렌더링 토큰·logits의 동등성이나 모든 내부 옵션의 동등성을 증명한 실험은 아니다. 첫 PocketPal 확인1건은 클로이 실행과 겹쳤고, 이후에는 클로이 종료 후 수집했다. 처리속도·전력·발열 우열을 비교하지 않는다.

클로이는 실제 Worker IPC에서 생성하고, 이후 실제 APK의 `ConversationManager.prompt`와 `VoiceDirector.parse`를54개 전부 실행했다. 고정 메시지가 실제 builder와54/54 일치했고 소비자54/54가 fallback 없이 통과했다. PocketPal은 실제 채팅 UI와 `LlamaContext` API 호출·원시 결과·저장/표시를 관찰한다. 클로이의 UI/TTS 전체 실행과 PocketPal의 core만을 같은 단계로 오인하지 않는다. 음성 합성·음성 자연스러움 비교는 하지 않는다.

## grammar 문제의 원인 후보와 검증

첫 PocketPal 응답은 요청값에 `enable_thinking=false`와 같은 schema가 들어갔고 실제 formatter도 닫힌 think prefill을 만들었다. 그러나 원시 `text`는 assistant 구분자부터 다시 시작하고 사고 블록을 포함했으며 `content`는 비어 있었다. 따라서 설정 저장 실패와 실제 생성/파싱 실패를 구분해야 한다.

관찰한 template-derived grammar의 root는 assistant 시작 구문부터 요구한다. [llama.rn JSIParams.cpp](https://github.com/mybigday/llama.rn/blob/27783c86cea93ac534fba303d9be5cf335d2e945/cpp/jsi/JSIParams.cpp)는 전달된 grammar 문자열을 USER 종류로 다룬다. 반면 [vendored sampling.cpp](https://github.com/mybigday/llama.rn/blob/27783c86cea93ac534fba303d9be5cf335d2e945/vendor/llama.cpp/common/sampling.cpp)는 output-format/tool grammar에만 generation prompt를 미리 소비시키고 USER grammar에는 적용하지 않는다. 이미 prompt에 들어간 assistant prefix를 sampler가 다시 생성하도록 강제하는 경로와 실측이 일치한다. [rn-completion.cpp](https://github.com/mybigday/llama.rn/blob/27783c86cea93ac534fba303d9be5cf335d2e945/cpp/rn-completion.cpp)의 content parser에는 그 중복 프레임이 넘어간다. 이는 소스와 관찰에서 얻은 원인 추론이다. 원래54개 수집 후, 출력 전에 정한4개 root-only 진단이 전부 공통 계약을 통과했다. 그 전에 선언한 구조적 gate에 따라 같은 조건을 나머지50개로 확장했다. 첫4개는 보정54개에 포함되며 새 생성으로 다시 세지 않는다.

클로이는 `common_chat_session.apply_sampling`과 같은 session의 `finish`를 사용한다. JSON grammar·prefill·parser가 한 session의 계약을 따른다. PocketPal 소스 전체를 가져오거나 두 앱의 이름만 바꾸는 것보다, 이 연동을 먼저 검증해야 한다.

## 직접 평가와 남은 범위

GPT가 실제 합성 발화를 읽고 관련성/자연스러움, 말투, 이름/역할, 문맥 소유자, 정직성, 지시문 침입을 판정한다. 작성자와 평가자가 같고 앱 구분도 알고 있으므로 독립 블라인드 평가나 사람 평가로 부르지 않는다. `text`에서 얻은 JSON 후보는 실제 앱 발화와 구분한다. 전달된 내용이 없는 경우 대화 품질은 null이며 임의의0점이나 성공으로 바꾸지 않는다. JSON/EOS/stop 성공과 의미·말투의 성공도 따로 센다.

기존 PocketPal의 평소 Q4_0·기본 sampling·thinking/무제한 생성 정책을 재현한 비교는 아니다. 이 실험의 엄격 JSON 조건에서 생긴 실패를 PocketPal 기본 대화 전체의 열등함으로 일반화하지 않는다. 클로이의220자/384토큰 정책은 긴 대답에 직접 영향을 주지만, 길이만 늘리면 역할·소유자·정직성 문제까지 해결된다는 증거는 없다.

실제 생성과 품질 판정은 모두 완료했다. 재현 도구는 [계측 안내](../../training/android-match/README.ko.md)를 따른다.

## 실측 결과와 원인 범위

수정 없는 PocketPal은 실제 completion 요청의 메시지·schema·temperature/seed/n_predict/thinking/jinja/반복 penalty가54/54 맞았다. 하지만 assistant 프레임 재시작54/54, 생성 사고 블록54/54, 전달 본문0/54였다. 토큰 한도 중단은9개뿐이므로 나머지도 전부 한도 탓이었다고 설명할 수 없다. EOS/stopword와 한도 중단은 구분해 기록했다.

root 한 줄만 바꾼 조건은 메시지와 요청값 감사54/54 통과, 본문/공통 계약54/54, EOS54/54, 토큰 한도 중단0이다. 프레임 재시작과 생성 사고 블록은 각각54→0이다. 이 개입은 **동일 preset에서 grammar 시작점과 prefill의 불일치가 전달 실패를 일으킨다는 원인 가설을 강하게 지지한다.** 제품 native 패치를 검증했거나 기본 PocketPal의 모든 오류 원인을 증명한 것은 아니다.

두 경로의 실제 발화는11/54개가 정확히 같았다. 같은 질문/이력/발화인11개에는 이미 고정한 직접 판정을 명시적으로 재사용했다. CHLOE54와 보정54의108판정은97개의 서로 다른 입력/발화 그룹에 대응한다. 외부 judge API나 키워드 점수로 판정을 만들지 않았다.

보정 PocketPal을 CHLOE와 질문별로 비교하면 등급 상승9개·하락7개·동일38개다. 전체 엄격 통과는15→18이지만 실패도19→20이다. 단일 phone/seed, 서로 다른 runtime에서 나온 작은 비블라인드 표본이므로 보정 runtime 승격 근거로 삼지 않는다. 원래 PocketPal의 미전달 출력을 의미 품질0점으로 놓고 상승률을 만들지 않는다.

| 직접 평가 항목 | CHLOE 통과 / 부분 / 실패 | 보정 PocketPal 통과 / 부분 / 실패 |
| --- | --- | --- |
| 내용/흐름,54개 | 17 / 20 / 17 | 22 / 16 / 16 |
| 고정 말투,54개 | 51 / 2 / 1 | 49 / 2 / 3 |
| 정직성,54개 | 44 / 3 / 7 | 44 / 3 / 7 |
| 이름/역할,적용17개/21개 | 8 / 5 / 4 | 13 / 4 / 4 |
| 명시적 회상,3개 | 2 / 0 / 1 | 2 / 0 / 1 |
| 규칙 처리/노출,7개 | 2 / 1 / 4 | 4 / 1 / 2 |

발화가 자발적으로 이름/역할을 언급하면 그 항목을 적용하므로 이름/역할의 적용 분모는 다르다. 비적용을 통과에 더하지 않는다. 회상 분모3도 작은 진단 표본이다. conv46은 종/이름 요약, conv50은 앱 이름이 클로이 자신의 이름과 같은 shortcut 가능성이 있어 소유자 추론 일반 성공을 뜻하지 않는다. 엄격 통과는 적용 항목 전부 pass, fail 하나라도 있으면 실패, 나머지는 부분이다.

### 질문별 차이

- **이름/역할:** identity01에서 CHLOE는 사용자 이름 처리 규칙을 두 차례 반복했다. 보정 PocketPal은 클로이라고 소개했으나 불필요하게 사용자 이름을 되물었다. identity02의 개발자에게 자기소개는 양쪽 통과다. conv17은 보정 경로에서도 사용자를 클로이라고 부르고 반복했다.
- **문맥 소유자:** conv44는 두 경로 모두 사용자 고양이를 “내 고양이”라고 하고 클로이와 이름을 섞었다. conv45도 사용자를 보리로 불렀다. conv48의 보정 응답은 보리님 호칭은 없앴지만 무관한 고양이 이름 반응이 남았다. 중립 이력에서도 오류가 생겨 이전 assistant 오답 전파만으로 설명되지 않는다.
- **말투:** conv41의 고정 반말은 둘 다 실패했고 보정 경로는 conv08/39에서도 존댓말로 이탈했다. conv42는 보정 쪽이 존댓말을 유지하면서 자연스럽게 대화를 이어, 경직된 거절이 줄었다.
- **정직성/도구:** 현재 날씨를 조회 없이 단정하고 일정·전화 실행을 암시하는 오류가 양쪽에 있었다. 반면 주가 한계 고지·거짓말 요청 거절은 양쪽 통과했다. 본문/형식 복구가 기능 한계 인식을 해결하지 않았다.
- **내용/반복:** 보정 쪽은 커피의 감각 경험을 꾸미지 않았고 양자화 설명도 자연스러웠다. 반대로 취침 인사를 기상 인사로 오독하고 LLM/TTS 설명 뒤 이름을 물었다. 전화 답변은 EOS에 도달해도 반복이 심했다. conv13에는 양쪽 모두 길이 메모 또는 tts_instruction 같은 내부 정보가 발화로 나왔다.
- **사실 정확도:** 보정 conv24는 “자주 충전하면 … 한 번에 오래 충전”을 권했다. 리튬이온의 부분 충전과 누적 충전 사이클을 설명하는 [제조사 안내](https://www.apple.com/batteries/why-lithium-ion/)와 맞지 않는 일반화다. 이 항목은 내용 정확도로 감점했고 의도적 거짓말로 단정하지 않았다.

같은 모델 bytes와 system/history를 두 native 경로에 넣고도 공통 소유자/기능/반복 오류가 남았다는 점은, 현재 문제를 wrapper 하나로만 설명할 수 없다는 근거다. **모델 자체와 공유 prompt의 상대적 기여, 한국어 소유어 처리와 토큰화의 기여는 이번 대조로 분리되지 않았다.**

## 실행·보존·회귀

- 원본 앱 두 개는 업데이트/초기화/삭제하지 않았다. 설치 APK5개의 사후 SHA가 원래 백업과5/5 같고, 클로이4B SHA도 위 값 그대로다. 원본 클로이 설정/로그3파일의 tar member 내용 SHA가 전후 일치한다. 원본 PocketPal private DB는 non-debuggable이라 해시 비교할 수 없었으며 패키지 격리로 보호했다.
- WSL2B checkpoint SHA `aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1`, 10-step adapter SHA `661873993a9c70089937a64d9282e21a1ce2b622a5b60764305159c0c98bb025`를 읽기 전용으로 재확인했다. 이4B 시험에 adapter를 적용하지 않았다.
- 재서명한5APK의 원본과 payload entry 집합/내용이73/853/46/1/61개 각각 일치한다. metadata/manifest/서명 예외는 위 방법과 checks에 명시했다. APK·weights·keystore·DB·사용자 로그·raw reasoning은 Git에 넣지 않는다.
- 발열로 중단된 conv33은 읽기 전용 DB/WAL 백업 후 aborted 세션으로 보존하고 새 빈 세션으로 재개했다. 기존32출력은 재생성하지 않았다. 열 중단 직후 DB snapshot은 실패했으므로 사용하지 않았고, 재연결 후 일관된 SQLite snapshot을 썼다.
- 사용자 재개 지시 뒤 쿨러 조건에서 수집했다. 시험 중 임시 portrait lock을 적용했고 종료 후 원래 `wm user-rotation free`로 복구 확인했다. 비교 앱 프로세스는 정지했다. 시험 앱/모델 복사본과 원시 합성 결과는 재현용 로컬 자료로 보관한다.
- Windows/WSL의 현재 Windows checkout 회귀는 각각119검사 중116통과·3skip, exit0이다. optional tokenizer/xgrammar 의존성이 없는 환경의 skip이다. 별도 기존 Linux venv의 JSON 계약7개는7/7통과·skip0다. 새 matched 검사4개가 전체119개에 포함된다.
- Android SDK36/build-tools35.0.0/JDK21.0.12.101로 계측 APK를 실제 빌드·서명 검증했다. 제품 전체 Gradle/release 빌드나 음성 재생 시험을 했다는 의미가 아니다. 포착한107개의 PocketPal completion context는 GPU=false/devices=[]/threads4로 같았고 최초1개에는 그 context 이벤트가 없어108/108 관측이라고 부르지 않는다.
- 첫 기본 호출의 동시 실행, 발열 중단/쿨러/회전 변화, native 라이브러리 차이 때문에 속도·전력·온도 우열은 집계하지 않는다. 여러 seed·문맥 길이·GPU 기본값 동등성을 검증하지 않았다.

## 개선 방향과 적용 경계

1. **추론 경로의 계약을 먼저 지킨다.** template-derived grammar를 USER grammar로 취급하면서 prefill 소비가 달라지는 경로를 검증했다. 클로이의 session 단위 grammar/prefill/parser 연결은 유지한다. 비교용 root 문자열 교체는 production 수정으로 배포하지 않는다. 제대로 된 수정은 grammar 종류·lazy trigger·preserved token·parser를 함께 다뤄야 하며 thinking on/off, 일반 text, tool/JSON 각각의 회귀가 필요하다.
2. **사용자 사실과 발화 주체를 분리한다.** 중립 assistant 이력이 있어도 보리를 자신의 고양이로 답한다. 사실 저장 시 주체/관계/값을 구분하고 생성에는 출처가 보이는 사실을 주는 방향을 다음 실험으로 삼는다. 앞선2B의 이름 소유격 결과는 소재별 실패가 있었으므로 일괄 이름 치환을 채택하지 않는다. 이4B 결과도2B adapter의 효과 증거가 아니다.
3. **기능 실행 가능 여부를 모델의 말에 맡기지 않는다.** 날씨·일정·전화 등의 실제 도구가 없는 조건에서 가능한 것처럼 말하는지를 따로 평가한다. 구현 시 도구 등록/권한 상태를 기준으로 실행 약속을 제한하고, 실제 완료 확인 없이는 성공 발화를 만들지 않는 경로가 필요하다.
4. **이름/말투 prompt는 후속 최소 대조로 줄인다.** 사용자의 이름을 묻지 않은 질문에도 이름 처리 문구가 침입하거나 사용자와 클로이를 혼동한다. 길고 반복적인 이름 규칙을 더 추가하기보다 작은 고정 prompt 대조와 독립 질문으로 검증한다. 이번에는 prompt 기본값을 변경하지 않았다.
5. **긴 답변과 음성 발화 한도를 구분한다.** 현재220자/384토큰은 PocketPal의 평소 긴 대답 경험과 다르다. 별도 설명 모드와 음성 청크 분할은 후보지만 길이를 늘리면 역할·소유자·정직성이 좋아진다는 뜻은 아니다. 먼저 같은 질문의 품질과 잘림/반복을 검증한 뒤 도입한다.

이번 PR은 실험 도구와 증거를 추가한다. 앱 기본 prompt·native runtime·모델 allowlist·가중치·학습 데이터/step은 바꾸지 않는다. 제품 패치, 기존 PocketPal Q4_0 기본 preset, GPU 효과, 여러 seed/폰/독립 평가자, 실제 음성 재생과 장기 self-generated 대화는 미실행이다.
