# 동일 GGUF Android 앱 비교 도구

이 도구는 기존 APK의 DEX·native 라이브러리·assets·resources.arsc·res/를 유지한 별도 패키지에서 합성 평가를 수행한다. 실제 설치 버전, 방법과 한계, 최종 결과는 [실측 보고서](../../docs/validation/local-llm-matched-apps-report.md)를 따른다. 학습·adapter 적용·모델 변환은 수행하지 않는다.

## 고정 입력과 격리

- `training/configs/matched-apps-plan.json`: 원래 alpha15 direct persona 두 말투, 모델 SHA, 생성 요청값, 평가 기준, 보충/탐색 실험의 추가 시점.
- `training/scripts/matched_app_suite.py`: 기존 50질문과 기존 보충 4질문. 두 앱에 동일한 메시지를 전달한다. 과거 답변의 오류를 전파하지 않도록 회상에는 고정된 사용자 사실과 중립 assistant 이력을 사용한다.
- 시험 패키지는 `ai.chloe.match.chloe`, `ai.chloe.match.pocketpal`, 계측은 `ai.chloe.match.driver`다. 원본 패키지의 설정·로그·모델 경로에는 쓰지 않는다. 원본 signing key 대신 시험 전용 새 key를 사용한다.
- APK·GGUF·원본 데이터 백업·기기 DB·원시 debug/생각 텍스트는 `artifacts/llm-training/` 아래 Git 제외 경로에 보관한다. PR에는 합성 발화 부분·해시·실행 상태·GPT 판정만 기록한다.
- 계정·기존 PocketPal 대화는 시험 앱에 복사하지 않는다. 원본 manifest의 INTERNET 권한은 유지한다. 제거하면 SDK 초기화가 실패하는 것을 사전 점검에서 확인했다. 생성은 기기의 local `llama.rn` 경로다.

## 준비 및 빌드

ADB에서 대상 기기와 `--user 0` 패키지/버전을 확인한다. 원본 APK와 클로이 설정·로그는 먼저 읽기 전용으로 백업한다. 비교 패키지가 이미 있으면 그 데이터와 서명을 확인한 뒤 별도 실험으로 관리한다.

`android_matched_apks.py`는 지정한 원본 APK를 새 파일로 복사하며 manifest의 패키지·provider authority·상대 class 이름·debug/backup만 조정한다. META-INF 서명/버전 metadata는 제외하고, 재서명 시 기존 stamp 인증서도 제거된다. payload 검사에서 이 예외를 명시한다. 원본 APK는 보존한다.

```powershell
python training/scripts/android_matched_apks.py --source SOURCE.apk --output NEW-unsigned.apk --package ai.chloe.match.chloe
# PocketPal base와 각 split도 ai.chloe.match.pocketpal로 동일하게 처리한다.
# Android SDK zipalign -P 16 4 → apksigner sign → apksigner verify 순서로 새 파일에 서명한다.
```

`verify_payloads(source, signed)`로 양쪽의 모든 payload entry 집합과 내용을 비교한다. 서명·manifest 예외 외에 새 entry가 추가된 경우에도 실패한다. 설치는 새 비교 패키지와 같은 시험 key로 서명한 PocketPal split 전체에만 한다.

프레임워크 전용 계측 APK는 NDK나 앱 전체 Gradle 빌드 없이 만든다. 실제 사용한 SDK/JDK 버전은 보고서에 있다. 비밀번호는 시험 key의 값이다.

```powershell
$env:CHLOE_COMPARISON_KEY_PASSWORD = 'YOUR-EXPERIMENT-KEY-PASSWORD'
python training/android-match/build_driver.py --sdk ANDROID_SDK --jdk JDK_DIRECTORY --keystore EXPERIMENT.keystore --output NEW_BUILD_DIRECTORY
```

## 새 시험 DB와 공통 모델

두 비교 앱의 private `files/conversation-models/4b.gguf`에 같은 기존 파일을 복사하고 크기·SHA를 확인한다. 원본 클로이의 모델을 읽어 새 복사본을 만들며 다운로드나 원본 교체를 하지 않는다. `exec-out`의 binary 데이터는 Python `subprocess.run(..., stdout=file.open('xb'))`로 저장한다.

새 PocketPal 분리본을 한 번 시작한 뒤 정지하고 `databases/RKStorage`, `pocketpalai.db`와 WAL을 읽기 전용으로 복사한다. SQLite backup API로 일관된 fresh chat DB를 만든다. 기존 사용자 DB를 입력으로 쓰지 않는다.

```powershell
python training/android-match/seed_pocket.py --fresh-async-storage FRESH_RK.sqlite --fresh-chat-db FRESH_CHAT.sqlite --chloe-apk ORIGINAL_CHLOE.apk --output NEW_SEED_DIRECTORY
```

생성된 DB는 새 비교 앱에만 넣는다. 앱을 정지하고 자체 WAL 상태까지 함께 관리한다. `ModelStore`의 context 설정, 두 말투 Pal, 세션별 completion 설정과 동일 이력을 미리 넣는다. 실제 native 요청은 `audit_matched_apps.audit_pocket`으로 다시 검사한다. 저장 값만 보고 적용됐다고 판단하지 않는다. seed는 fresh 시작 entry를 재사용하므로 UI의 원래 preset metadata와 GGUF의 실제 architecture를 구분한다.

## 실행과 관찰

`Driver`의 `chloe` 작업은 실제 설치 APK의 `LlmWorker`에 IPC 요청을 보내고 응답을 파일에 즉시 저장한다. `auditApp`은 생성 없이 실제 `ConversationManager.prompt`·`VoiceDirector.parse`를 실행해 고정 입력과 소비 결과를 확인한다. 클로이 UI/TTS 전체가 이 계측의 측정 대상인 것은 아니다.

PocketPal은 실제 채팅 UI를 사용한다. driver의 `serve`는 한국어 입력과 현재 accessibility 정보에 근거한 선택을 수행한다. 새 명령 번호 구간을 시작하고 로컬 `driver-seq.local`도 그 번호로 맞춘다. 큐에는 한 host client만 접근한다. 표시된 세션 이름·Pal·drawer 닫힘을 확인한 뒤에만 질문을 보낸다.

```powershell
adb -s DEVICE shell am instrument -w -e op serve -e serial 50000 ai.chloe.match.driver/ai.chloe.match.driver.PocketDriver
```

다른 터미널의 host client를 같은 device/artifact 경로로 구성한다. 모델 로드 후 `observe.js`를 comparison package의 `files/`에 복사하고 `inject`로 로드한다. 이 관찰자는 원래 argument와 promise/result를 그대로 전달하며 `LlamaContext.completion/getFormattedChat`의 요청·결과를 기기 로그에 기록한다. module 번호1740은 기록한 **1.22.0 APK에만** 해당한다. 다른 APK에 그대로 적용하지 않는다. 진단용 module 탐색·초기 실패는 정규 비교에서 제외하고 재시작 후 확인한 모듈만 접근했다.

```powershell
python training/android-match/capture.py --artifacts ARTIFACT_DIRECTORY --adb ADB_PATH --device DEVICE --start 0 --end 54
```

capture는 이미 저장된 결과를 건너뛴다. 실행이 전송 이후 중단됐다면 API trace와 시험 DB를 먼저 확인한다. 같은 세션에 중복 질문을 보내고 동일 조건으로 집계하지 않는다. 최종 집계는 실제 요청 메시지·schema·seed/temp/한도/thinking 등을 전부 검사한다. `text`의 JSON 꼬리는 **진단용 후보**이며 `content` 또는 실제 앱 소비 결과와 합쳐 성공 처리하지 않는다. quality 점수는 직접 GPT 검토로 별도 작성한다.

`diagnose-grammar.js`는 기본 비교 후 탐색 실험에만 쓴다. template-derived grammar의 root 한 줄을 `response-format`으로 바꾼 새 조건이며, 제품 수정이나 수정되지 않은 PocketPal 결과로 표시하지 않는다. 이력·질문·system·schema·sampling은 유지한다. 별도의 새 합성 세션과 결과 파일을 사용하고 root 변경 이벤트까지 기록한다.

분리 앱의 결과·설정·모델 SHA와 원본 보존 상태를 확인하고 보고서에 남긴다. 원본 앱의 업데이트 설치, 모델 merge/export, 재학습은 이 도구의 범위에 포함되지 않는다.

## 조건부 확장과 집계

원래 비교는 CHLOE 54개와 수정 없는 PocketPal 54개다. grammar 보정은 원래 비교 뒤의 별도 탐색 조건이다. 출력 전 고정한 네 질문(conv01, identity01, conv44, conv35)이 모두 공통 소비 계약을 통과할 때만, 같은 질문 목록의 나머지 50개로 확장한다. gate는 내용 점수가 아닌 구조적 통과 여부다. 첫 네 출력을 보정 조건의 54개 중 네 셀로 재사용하며 추가 생성으로 중복 집계하지 않는다. 열/모델명은 평가자가 알므로 독립 블라인드 실험이 아니다.

`audit_matched_apps.py`는 API 요청과 전달된 JSON을 검사한다. 직접 GPT 판정은 별도 파일에 고정한다. 수정 없는 PocketPal의 비어 있는 `content`에는 품질 점수를 주지 않는다. 보정 조건도 실제 반환된 `content.spoken_text`만 평가한다. raw text에서 추출한 후보는 전달 성공이나 평가 자료를 대체하지 않는다.

```powershell
python training/scripts/export_matched_app_results.py --artifacts ARTIFACT_DIRECTORY --judgments DIRECT_GPT_JUDGMENTS.json --output NEW_PUBLIC_DIRECTORY
```

export는 54개 보정 출력과 판정이 준비됐는지 검사하고 새 디렉터리만 생성한다. 평가 과정의 Python API 호출은 판정을 생성하지 않고, GPT가 직접 읽고 기록한 판정의 개수만 집계한다. 기기 화면 회전 등을 임시 변경했다면 기록한 원래 상태로 복구한다. 중단 시에는 캡처와 대기 중인 후속 controller도 모두 정지해 사용자 지시 없이 재시작되지 않게 한다.

## 사용자 사실·기능 제한 후속 비교

[정책 보고서](../../docs/validation/local-llm-grounding-policy-report.md)와 [탐색 과정/최종 계획](../configs/grounding-plan.json)을 따른다. 이 경로는 PocketPal grammar 보정과 별개다. production Java policy를 계측 빌드에도 포함하므로 원본 앱 재설치 없이 같은 native 모델에서 prompt/소비 정책을 검증한다.

새 artifact 디렉터리에 `matched_app_suite.build_suite()`의 각 row를 복사해 `source_id=원래id`, `id=grounded-원래id`, `grounded=true`를 추가한다. JSON의 messages/input/register는 바꾸지 않는다. 그54개 입력을 격리 패키지 files에 복사하고 다음 작업을 쓴다.

```powershell
adb -s DEVICE shell am instrument -w -e op groundAudit -e input SUITE.json -e output NEW_AUDIT.json ai.chloe.match.driver/ai.chloe.match.driver.Driver
```

actual audit의 `byte_identical=false` 또는 `policy_action!=none`인 row만 별도 새 suite로 선택해 기존 `op chloe`에서 생성한다. 나머지는 원래 메시지 바이트/결정 동등성을 감사하고 baseline raw를 명시적으로 재사용한다. model output을 다시 만들었다고 집계하지 않는다. 최종 정책의 소비 응답을 변경했으면 새 audit으로 모델 입력/action 동등성을 다시 확인하고, 정책 reply를 새 native 생성 없이 replay한다. `op auditApp`은 기존 base builder와 최종 raw의 실제 consumer를 생성 없이 검증한다. 최종 CSV 대신 JSON은 raw draft·앱 보정·판정/alias를 구분해 남긴다.

```powershell
python training/scripts/test_grounding_policy.py --gradle-cache GRADLE_MODULE_CACHE --jdk JDK_DIRECTORY --json-jar JSON_20240303.jar --output NEW_JVM_TEST_DIRECTORY
python training/scripts/export_grounding_results.py --artifacts ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

JVM 명령은 실제 policy Java·ConversationEngine Kotlin·두 test class를 컴파일해 실행한다. 기존 cache를 읽고 새 출력 디렉터리만 만든다. org.json은 앱에 선언된20240303 테스트 의존성이다. export는 직접 GPT 판정 파일을 읽어 집계하며 판단을 생성하지 않는다. 현재 결과는 새 native13개, alias41개, 재현 reference6개이고 중간 pilot2+10개는 별도 제외했다. final policy의 앱 전체 UI/TTS 배포를 대신하지 않는다.

## 요약 주체·관련 이력 후속 비교

[후속 계획](../configs/summary-relevance-plan.json)과 [실제 결과](../../docs/validation/local-llm-summary-relevance-report.md)를 따른다. 기준선은 원래 alpha15가 아닌 직전 policy의 최종54개다. `groundAudit`의 실제 model message 배열·decision/reply를 직전 감사와 비교해 모델 입력이 바뀐 것만 생성한다. 기준선이 이미 system 보강을 포함하므로 original input과의 `byte_identical`만 보고 alias를 판정하지 않는다.

```powershell
python training/scripts/export_summary_relevance_results.py --artifacts ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

producer는 원래 질문과 base system 유지, model view가 원문 발화의 순서 보존 부분집합인지, user/assistant 쌍 생략인지, actual consumer 일치를 검사한다. 의미 판정은 직접 GPT가 작성한 파일에서 읽는다. 현재 결과는7생성 중6선택·1중간후보제외와 이전48출력 재사용이다. 생성 당시 입력과 최종 정책 입력이 같은 중간4개는 재생성하지 않았다. 이 재사용을 새 모델 실행으로 세지 않는다. 원본 세션은 보존하고 모델 view에서만 불필요한 fact/ack 쌍을 빼며, 근거가 완전한 요약만 앱 결정으로 처리한다. 이전 policy의 재현은 snapshot 참조와 원래 SHA 검사를 계속 사용한다.

## 발화 정리 replay

production `ReplyEconomyPolicy.java`도 driver에 컴파일한다. `op economyAudit`, `input`=직전 최종 JSON 배열 파일, `output`=새 파일명으로 actual VoiceDirector의 before/after를 검사한다. native 생성은0회다. `groundAudit` 결과는 직전과 완전히 같은지 확인한다. Kotlin manager 통합은 JVM81개(3 test class)로 별도 검사하며 전체 APK/UI/TTS 증거로 쓰지 않는다.

```powershell
python training/scripts/export_reply_economy_results.py --artifacts ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

export는 동결된 입력/기존 판정/실제 소비/비발화 JSON 메타데이터/삭제 전용 관계를 검사한다. 품질 판정은 GPT가 작성한 파일에서 읽고 자동 생성하지 않는다. [결과와 제한](../../docs/validation/local-llm-reply-economy-report.md)을 따른다.

## 질문 echo·미완성·규칙 노출 replay

production `ReplyIntegrityPolicy.java`도 driver에 컴파일한다. `op integrityAudit`, `input`=직전 economy 최종 JSON 배열, `output`=새 파일명으로 처리한다. 유지된 응답은 alpha15 실제 VoiceDirector로 전후 parse하고, `blocked`는 final_raw=null/unusable_reply로 구분한다. Kotlin manager의 실패 안내/이력/TTS eligibility는 JVM97개(4 test class)에서 별도 검증한다. 제품 전체 UI/TTS 검증을 대신하지 않는다.

```powershell
python training/scripts/export_reply_integrity_results.py --artifacts ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

export는 동결 요청·실제 전후 소비·삭제 관계·차단 상태를 검사하고, 차단을 성공 점수로 올리는 판정을 거부한다. GPT 직접 판정과 무변경50개 재사용을 구분한다. [실제 결과/경계](../../docs/validation/local-llm-reply-integrity-report.md)를 따른다.
