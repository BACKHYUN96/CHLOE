# 2026-11-14 말투·내용 블라인드 평가 자료

기존 JSON 계약 수정 후의 원본/10-step adapter 응답으로 사용자 평가용 오프라인 HTML을 만들었다. 추가 추론·재학습·가중치 변경은 없다. 실제 사람 평가는 아직 하지 않았으며 품질 점수와 품질 이득은 미확정이다. 기존 Windows 환경·Android 모델·학습 venv도 보존했다.

## 질문과 비교 조건

[선택 계획](../../training/configs/blind-review-plan.json)은 요청한 다섯 영역에 맞춰 응답의 우열을 보기 전에 고정했다. 전체55질문 평가의 일부이므로 결과를 전체 사용자 대화로 일반화하지 않는다. 문맥 카드2개는 각각10턴이며 나머지는 단일 질문이다.

| 영역 | 고정 질문 ID | 말투 | 카드 / 응답 쌍 |
| --- | --- | --- | --- |
| 반말 | conv01, conv17, conv30, register01 | 반말 | 4 / 4 |
| 존댓말 | 위와 같은4질문 | 존댓말 | 4 / 4 |
| 자기소개 | identity01, identity02 | 각각 두 말투 | 4 / 4 |
| 정직성 | conv31, conv32, conv35, conv38 | 각각 두 말투 | 8 / 8 |
| 문맥 기억 | conv41–conv50 전체 순서 | 각각 두 말투 | 2 / 20 |
| 합계 | | | **22 / 40** |

총80개 응답의 `spoken_text`를 공백·문장·오류까지 그대로 담았다. JSON·자동 계약 점수·모델명 메타데이터·기존 A/B·해시·소스 파일명은 평가 화면에 넣지 않는다. 응답 본문에 후보가 스스로 말한 이름은 품질 평가 대상이므로 수정하지 않는다. 음성/TTS 평가 자료는 아니다.

두 후보는 기존 동일 실행의 seed42, greedy, thinking=false, max384/context2048, NF4/BF16, 동일 tokenizer/persona/schema/XGrammar/종료 토큰/GPU를 사용했다. 질문의 지정 말투는 앱 설정이며 사용자의 말투 전환 요청보다 우선한다. 반말·존댓말 카드에도 이를 명시한다.

문맥은 두 후보 모두 conv41에서 새로 시작하며, 각자 자신의 앞선 유효 발화문으로 최근 최대4턴·사용자+응답 합 UTF-16 1200자 상한을 적용했다. 따라서 **질문·기억 정책·생성 규칙은 같지만 후보별 실제 과거 응답과 토큰열은 다르다.** 전체10턴 기록을 읽을 수 있게 보여 주며 실제 기억 입력에서 오래된 턴이 제외될 수 있다고 안내한다. 공통 정답 대화를 주입한 기억 능력 실험은 아니다. 다른 카드는 매번 새 대화다.

## 블라인드·저장 설계

기존 평가기의 seed42 A/B 대응은 재사용하지 않았다. OS 난수 기반으로 새로 배치하며 단일 질문은 영역/말투 안에서, 문맥 묶음은 두 말투에 걸쳐 위치를 균형 배치했다. A/B 대응은 카드마다 달라질 수 있고 한 문맥 카드 안에서는 유지한다. 카드별 대응표와 원본 응답 파일 해시는 Git 제외 `artifacts/llm-training/blind-review-20261114/`에만 보관한다. 공개 manifest에는 대응표 내용 없이 파일 commitment만 기록한다. 평가 전에 대응표를 열지 않는다.

로컬 전달 폴더 `outputs/CHLOE_Blind_Review_20261114/`에는 `review.html`, `사용방법.txt`, `blank-ratings.json`, 이 세 파일만 담은 ZIP이 있다. 이 폴더는 저장소 밖에 있다. 원문·대응표·가중치·사용자 평가는 PR에 추가하지 않았다.

사용자는 A/B 선호, 비슷함, 둘 다 부적합, 판단 보류를 선택할 수 있다. 자연스러움/내용 적절성/영역 기준의1–5점과 메모는 선택 사항이다. 모든 초기 점수는 null이며 미판정·보류·판정을 구분한다. 점수만 입력해도 임의 우승을 만들지 않는다. 상세 점수 없이 선호만 입력해도 된다.

브라우저 임시 저장과 명시적 JSON 저장/불러오기를 제공한다. 중간 저장은 미완료로 표시하며, 불러오기는 packet ID·카드 목록·판정 enum·1–5 정수/null·메모 길이를 검사하고 교체 전에 확인한다. 임시 저장이 막혀도 JSON 내보내기를 허용한다. 네트워크 요청은 없고 CSP도 connect-src를 차단한다. 응답/메모는 textContent로 렌더링해 HTML로 실행하지 않는다. 사용자 평가 후 JSON을 채팅에 전달하면 별도 집계할 수 있다. 모델 승격은 자동 실행하지 않는다.

## 생성 재현

Linux clone 루트의 기존 venv를 사용한다. source는 보존된 최종 비교이며 공개 receipt의 summary SHA와 고정 질문/persona/schema SHA를 먼저 검증한다. 응답마다 소비자 계약·원본 JSON 일치·종료 상태를 다시 확인한다. 새 출력/대응표/audit 경로만 허용한다. 아래 예시 경로는 이미 사용했으므로 재실행 시 모두 새로운 이름을 지정한다.

```bash
.venv-llm/bin/python training/scripts/build_blind_review.py \
  --source artifacts/llm-training/contract-20261114/xgrammar-final \
  --output /absolute/path/outside-repo/CHLOE_Blind_Review_NEW \
  --private artifacts/llm-training/blind-review-NEW \
  --audit docs/validation/local-llm-blind-review-NEW/manifest.json
.venv-llm/bin/python -m unittest discover -s training/tests -v
# Node 표준 DOM harness. 실제 브라우저 대신 JavaScript 로직을 검사한다.
node --test training/tests/test_blind_review_ui.cjs
# 생성한 실제 자료에 같은 로직 검사 적용 (이 명령에는 --test를 붙이지 않는다)
node training/tests/test_blind_review_ui.cjs /absolute/path/to/review.html
```

## 실제 검증과 한계

[manifest](local-llm-blind-review-20261114/manifest.json)에 전달 파일 SHA·22카드/40쌍·소스 summary SHA·대응표 commitment가 있고, [checks](local-llm-blind-review-20261114/checks.json)에 실행 결과가 있다.

- 실제 자료80응답이 원본 발화문과 정확히 일치함을 대응표를 이용해 별도 확인했다. ZIP은 평가용3파일만 포함하고 대응표는 포함하지 않는다. 전달 평가표는 모두 null이다.
- WSL 회귀29개 전부 통과. 새5개는 질문/응답 범위·위치 균형·문맥 순서·원문 보존·미평가 상태·새 대응·출력 덮어쓰기/잘못된 소스 거부를 확인한다. 기존24개도 통과했다. Windows는26통과/선택 decoder3개 skip이었다.
- Node DOM harness는 템플릿5개, 실제 전달 HTML5개 모두 통과했다. 렌더링 데이터 수·빈 점수·잘못된 import 거부·임시 저장/reload·중간 export/import round trip·보류 처리·storage 실패를 확인했다. 최초 실제 HTML 검사 호출에 `--test`를 잘못 붙여 HTML이 JS로 해석되는 실패가 있었고, 위의 올바른 명령으로 재실행해 통과했다.
- **실제 브라우저 화면·반응형·인쇄·다운로드 대화상자는 미검증이다.** 도구가 file:// 접근을 프로토콜 정책으로 거부했다. 정책을 우회하지 않았다. Node DOM harness 통과를 브라우저 화면 검증으로 보고하지 않는다.
- 원본 checkpoint/adapter SHA와 학습 venv freeze가 이전 receipt와 같음을 다시 확인했다. Android 코드는 바꾸지 않았고 기기 시험은 실행하지 않았다.

남은 일은 사용자의 블라인드 품질 평가와 점수 회수·집계, 실제 브라우저 표시 확인, 더 넓은 입력에서의 품질 검증이다. 기존 JSON220/220 통과는 자동 구조 검사 결과이며 이번 자료 준비도 사람 품질 개선 증거가 아니다. 긴 학습·merge·GGUF·Android 모델 교체는 수행하지 않았다.
