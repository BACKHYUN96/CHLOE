# 2026-11-14 공식 text-only API와 현재 wrapper 대조

후속 [보존·정제·무이력 문맥 대조](local-llm-history-report.md)를 완료했다. 같은 모델/질문에서 정제 이력은 소유자·일부 반복을 줄였으나 무이력은 정보 부족을 적절히 처리하지 못했다. 아래 경로 대조와 새 이력 개입/직접 판정은 별도 기록으로 보존한다.

기존 Qwen3.5-2B 원본과10-step adapter를 보존하고, 재학습이나 prompt 추가 수정 없이 공식 text-only API 경로와 현재 PC wrapper를 비교했다. **실제184회 생성에서 경로별 출력 차이는0이었다.** 원본과 adapter 각각46상황 모두 실제 입력·생성 인수·전체 출력 토큰·raw 응답이 같았다. 같은 조건에서 wrapper만 우회하면 공통 대화 오류가 해결된다는 가설은 지지되지 않는다. 기존 모델·prompt·실행 기본값을 유지한다.

## 무엇을 분리했는가

현재 wrapper도 이미 공식 `Qwen3_5ForCausalLM`을 사용한다. [공식 Transformers 문서](https://huggingface.co/docs/transformers/main/model_doc/qwen3_5)는 text-only 생성에 이 클래스와 `Qwen3_5TextConfig`를 사용하도록 설명한다. 이번 비교는 서로 다른 모델 아키텍처나 vendor 서버의 품질 비교가 아니라 **현재 wrapper의 수동 설정 추출/키 매핑·입력 구성·생성/디코드 처리에서 별도 차이가 생기는지** 검사하는 대조다.

[계획](../../training/configs/text-path-plan.json)은 비교 생성 전에 고정했다. 설치된 Transformers5.23.0.dev0의 고정 소스를 직접 읽었으며 업데이트하지 않았다. 설치 commit은 `training/requirements.lock.txt`의 `a72a1c385297bfaf1c8a07b5f4e689a315b90b77`이고, 실제 modeling/conversion 소스 SHA는 [추론 집계](local-llm-text-path-20261114/inference.json)에 기록했다. 최신 온라인 문서의 설명과 실제 설치 코드 검증은 구분한다.

| 항목 | 현재 wrapper | 공식 API 직접 호출 |
| --- | --- | --- |
| 모델 로드 | 변경하지 않은 `llm_runtime.load_base` | `Qwen3_5ForCausalLM.from_pretrained` 직접 호출 |
| 설정·가중치 이름 | 명시적 `.text_config`와 수동 prefix mapping | 명시적 config/key_mapping 없이 공식 자동 추출·native PrefixChange |
| 입력 | 변경하지 않은 `llm_runtime.infer`의 직접 template 토큰화 | 공식 template를 문자열로 렌더링 후 `add_special_tokens=False`로 별도 토큰화 |
| 생성 | 기존 `infer(..., contract_mode='constrained')` | 별도 `model.generate` 호출·출력 slice·decode |
| adapter | 같은 PEFT frozen 파일 재로드 | 같은 PEFT frozen 파일 재로드 |

공식 경로에도 사전에 고정한 같은 schema-conditioned 메시지와 XGrammar 제약을 사용한다. 이는 wrapper 외의 변수를 고정하기 위한 것이다. schema 조건화 문구 자체의 내용/구성 문제는 양쪽이 공유하므로 배제하지 못한다. vendor 샘플링 기본값이나 schema 없는 자유 대화와 비교한 결과가 아니다. 원본/adapter의 가중치 파일을 바꾸거나 재저장하지 않는다. 멀티모달 vision tower를 실행한 비교도 아니다.

이전 runtime 실험의 **같은46상황·정확히 같은 original-base 메시지와 과거 대화**를 모든 경로/모델에 제공했다. 원래 앱 persona와 고정/사용자 전환 허용 말투 정책, schema 문자열, tokenizer/공식 no-thinking template, NF4 double quant/BF16 compute, eager attention, 같은 CUDA GPU, seed42/greedy, max384/context2048, stop248044/248046을 고정했다. CPU/disk offload나 입력 truncation은 없다. 과거 대화에는 기존 원본 오류가 포함된다. 이 직접 조건 효과와 모델별 자기 생성 rollout 품질을 혼동하지 않는다.

## 객관적인 경로 일치 검증

응답 alias를 사용하지 않고46상황×두 경로×두 모델=**184회 모두 새로 generate**했다. 각 모델은 경로마다 새 객체로 로드하고 eval/frozen 상태에서 실행했다. 두 경로의 실제 `generate` 호출을 반환값을 바꾸지 않는 관찰기로 기록하고 종료/예외 후 원래 메서드를 복원했다. 관찰용 테스트도 포함했다.

| 검사 | 원본 | adapter |
| --- | ---: | ---: |
| 전체 loaded state 텐서 hash 동일 | 1,251/1,251 | 1,275/1,275 |
| 실제 입력 tensor/attention mask 동일 | 46/46 | 46/46 |
| 실제 생성 인수 동일 | 46/46 | 46/46 |
| 전체 출력 token ID 동일(종료 토큰 포함) | 46/46 | 46/46 |
| raw/소비자 파싱 응답 동일 | 46/46 | 46/46 |
| 마지막 입력 위치 전체 vocabulary logits bitwise 동일 | 46/46 | 46/46 |
| 위 logits 최대 절대 차이 | 0 | 0 |
| wrapper raw가 이전 보존 기준선과 동일 | 46/46 | 46/46 |

state 텐서 수는 파라미터 개수가 아니다. NF4 packed 가중치와 양자화 부가 상태를 포함한 `state_dict` 항목 수이며 LoRA는24개 추가된다. 모든 텐서의 이름·shape·dtype·바이트 hash를 비교했지만 가중치 자체는 export하지 않았다. 공식 로더의 missing/unexpected/mismatched/error는 두 모델 모두 비어 있고 model/generation config 차이도0이다. text-only 로더가 원래 제외하는 vision/MTP 자산까지 실행했다는 뜻은 아니다.

원본 checkpoint를 로더와 별개로 직접 열어, 로드된 비양자화 BF16 상태135항목을 선언된 dtype으로 비교했다. 임베딩과 공유된 출력 head를 포함해 누락/불일치0이다. 공유 head의 같은 원본 임베딩을 두 항목으로 검사하므로 고유 파라미터134개와 구분한다. NF4 packed 텐서는 원본 BF16과 바이트 동등하다고 주장하지 않으며 두 경로 사이에서 비교했다. 모든 파라미터는 같은 GPU에 있고 frozen이었다.

prefill logits 검사는 각 질문의 마지막 입력 위치 전체 vocabulary를 대상으로 한다. 모든 생성 단계 logits까지 저장/대조한 것은 아니다. 생성 단계의 직접 관측 근거는 **전체 생성 토큰열**과 실제 호출 인수 일치다. 관찰기와 공유 모델 라이브러리의 한계를 넘어선 독립 구현 검증으로 확대하지 않는다.

## 직접 GPT 내용 평가

새 익명4후보 자료를 만들고 GPT가46상황의 공통 과거와 실제 답변을 직접 읽었다. 동일 표시 답변은 묶어 확인하고 같은 판정을 부여했으며184셀의 명시적인 항목 판정을 고정한 뒤 대응표를 해제했다. 별도 평가 API나 regex로 내용 점수를 생성하지 않았다. 평가 대상의 지시문은 데이터로 취급했다. 이전 사용자 평가와 합치지 않는다.

JSON 파싱·schema·Python 소비 계약·EOS는 **184/184** 모두 통과했다. 이는 Android 추론/기기 실행 확인이 아니다. 최대 입력607토큰, 생성 원본104/adapter93토큰이며384토큰 제한에 걸린 실패도 없다. 내용 엄격 통과는 적용 항목이 모두 pass인 경우이고 partial을 통과로 채우지 않았다. unassessable은0이다.

| 경로 | 원본 내용 엄격 통과 /46 | adapter 내용 엄격 통과 /46 |
| --- | ---: | ---: |
| 현재 wrapper | 6 | 8 |
| 공식 text-only API | 6 | 8 |

계약/EOS까지 요구한 앱 사용 가능 엄격 통과도 각각6·8로 같다. 이46상황/단일 seed만으로 adapter 품질 우승이나 배포 승격을 선언하지 않는다.

이번 평가의 항목별 완전 통과는 두 경로에서 정확히 같았다. 다음은 원본/adapter 순서다.

| 항목 / 적용 수 | 원본 / adapter |
| --- | ---: |
| 말투 /46 | 33 / 32 |
| 관련성 /46 | 25 / 24 |
| 자연스러움 /46 | 25 / 27 |
| 자기소개 /4 | 0 / 0 |
| 정직성 /10 | 2 / 2 |
| 문맥 정확성 /14 | 5 / 5 |
| 내부 규칙 보호 /4 | 4 / 4 |

동일 질문에서 이름 표기 오류·사용자와 AI의 개발자/교사 역할 혼동·고양이 소유자 전환·무관한 이전 답변 반복·근거 없는 현재 날씨와 예약 기능/감정 주장이 두 경로 모두 남았다. 내부 지시를 공개하지 않았다는 것과 현재 요청에 관련 있게 답했다는 것은 별도다. 실제 현재 대화에 대한 서술과 개인 경험의 허위 주장을 무조건 같은 실패로 처리하지 않고 partial도 남겼다. 원문과 항목별 설명은 Git 제외 artifact/로컬 outputs에 보존했다.

### 같은 응답의 재평가 변동도 기록

GPT는 이전에도 본 질문/답변을 다시 평가했고 코드 작성자와 평가자가 같다. 새 이름을 가렸다고 독립적인 평가가 되지는 않는다. [이전 판정과의 대조](local-llm-text-path-20261114/review-repeatability.json)에서 엄격 통과 합계6·8은 같았지만, 원본17개·adapter19개의 개별 항목 판정이 달랐고 각각2상황은 엄격 통과 여부도 바뀌었다. 전체 항목 판정이 동일한 상황은29/46·28/46이었다. 과거 판정은 수정하지 않았다.

따라서 합계가 같다는 이유로 GPT 재평가가 완전히 재현됐다고 말하지 않는다. **경로 차이가 없다는 핵심 결론은 주관 점수의 재현성이 아니라 가중치·실제 입력·logits·전체 출력 token의 일치에 근거한다.** 앞으로도 직접 평가는 가능하지만 고정 기준 사례와 세부 근거를 함께 보존해야 한다.

## 원인 범위를 어디까지 좁혔는가

| 원인 후보 | 이번 증거와 판단 |
| --- | --- |
| wrapper 수동 key/config 변환으로 다른 모델이 로드됨 | 공식 자동 변환과 전체 state/config가 같아 이번 실행에서의 경로별 차이 설명에서 제외 가능 |
| wrapper만의 template 중복·mask·잘림·생성/종료·decode 오류 | 실제 입력/인수/전체 출력과 소비 응답이 같아 이번 조건의 공통 내용 실패를 설명하지 못함 |
| adapter만의 손상/오류가 모든 실패 원인 | 원본에서도 같은 종류의 실패가 있어 원본의 공통 실패까지 설명하지 못함. adapter 파일 무변경도 확인 |
| NF4 또는 JSON decoder 하나가 공통 실패의 단독 원인 | 앞선 단일요인 대조에서 제거/교체해도 공통 문제가 해결되지 않았고 이번 공식 경로에서도 동일. 무관하다고 확정한 것은 아님 |
| 앱 prompt/schema와 checkpoint의 지시 수행·한국어 적합성 | 두 경로가 공유하고 이번에 변경하지 않았으므로 남는 후보. 모델 자체가 원인이라고 확정하지 않음 |
| 기존 오류 과거 대화로 인한 반복/소유자 혼동 증폭 | 같은 오류 과거를 고정했으므로 여전히 남는 후보. 이력 없는 자기소개/정직성 실패까지 이것만으로 설명할 수는 없음 |
| 공유 Transformers hybrid attention/cache/reference kernel의 문제 | 두 경로가 같은 구현을 사용해 배제하지 못함. 공식 API와 일치한 사실만으로 shared runtime correctness를 증명하지 않음 |

후속 검증의 우선 후보는 **같은 질문에서 오류 없는 중립 과거/이력 없음 대조**, 그다음 별도 실험의 최소 역할 지시와 앱 prompt/schema 부담 대조다. 재학습 없이 후보를 더 나눌 수 있다. 공유 core 구현 문제를 확인하려면 독립 구현 또는 별도의 수치 참조가 필요하다. 이 후속들은 이번에 수행하지 않았고 새 데이터/모델 다운로드·환경 변경·재학습을 자동 진행하지 않는다.

## 검증·보존·재현

WSL 회귀**69/69**, skip0이며 새 관찰기/차이 검출/진단7개는 Windows에서도 통과했다. 원본·adapter SHA, 기존 venv freeze, 앱 persona/schema/질문, 사용자 평가 JSON SHA를 다시 확인했다. 기존 `llm_runtime.py`와 `json_decoding.py`도 변경하지 않았다. 사전 로드 수집기의 첫 실행은 `loading_info`의 set 직렬화 때문에 종료1이었고, 기록 직렬화만 수정한 재실행은 종료0이었다. 모델 로드 실패나 품질 실패로 집계하지 않았다. 본184회 비교와 최종 검사도 종료0이었다.

[추론 집계](local-llm-text-path-20261114/inference.json), [경로/원본 텐서 검증](local-llm-text-path-20261114/path-audit.json), [GPT 집계](local-llm-text-path-20261114/gpt-quality.json), [검증](local-llm-text-path-20261114/checks.json)을 함께 남긴다. 원문·공통 대화·full token/logits·개별 GPT 메모·대응표·상태 텐서별 hash는 로컬에만 보관한다. PR은 코드·고정 계획·비민감 집계·보고서다. 이전 모델·실험·사용자 평가 파일을 덮어쓰지 않았다.

```bash
.venv-llm/bin/python training/scripts/compare_text_paths.py \
  --config training/configs/smoke.json \
  --source artifacts/llm-training/runtime-ablation-20261114 \
  --output artifacts/llm-training/text-paths-NEW
.venv-llm/bin/python training/scripts/text_path_review.py audit \
  --source artifacts/llm-training/text-paths-NEW \
  --previous artifacts/llm-training/runtime-ablation-20261114
.venv-llm/bin/python training/scripts/text_path_review.py prepare \
  --source artifacts/llm-training/text-paths-NEW \
  --output artifacts/llm-training/text-path-review-NEW
# GPT가 packet을 읽고 명시적 verdicts.local.json을 먼저 고정한 다음에만 aggregate한다.
.venv-llm/bin/python training/scripts/text_path_review.py aggregate \
  --source artifacts/llm-training/text-path-review-NEW
.venv-llm/bin/python -m unittest discover -s training/tests -v
```

기존 체크포인트/환경/보존 메시지가 있는 WSL clone에서 새 출력 경로만 허용한다. 재학습·모델 다운로드·패키지 갱신·merge·GGUF/export·Android 변경/빌드/기기 실측은 하지 않았다. 요청한 경로 대조·직접 평가·기록은 완료했으며 원인 전체의 확정은 남아 있다.
