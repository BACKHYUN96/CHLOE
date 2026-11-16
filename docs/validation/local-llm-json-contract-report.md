# Qwen3.5 JSON 계약 원인 분석 및 수정 · 2026-11-14

**기존 가중치를 유지한 최종 동일 조건 비교220회가 모두 계약을 통과했다. 원본110/110, adapter110/110이다.** 재학습·응답 사후 보정 없이 실제 schema 전달과 byte 기반 생성 제약을 적용한 결과이며, adapter의 자연스러움/말투 우승이나 Android 실행 성공을 뜻하지 않는다.

## 원인과 수정 범위

기존10-step adapter와 원본 checkpoint를 그대로 두고 PC 추론/평가 경로를 수정했다. 재학습·merge·GGUF 변환·Android 변경은 수행하지 않았다. 기존 adapter의 낮은 계약 통과율만으로 학습 실패나 원본 가중치 손상을 결론 내릴 수 없다.

기존 첫4질문×2말투×2후보의16개 로컬 응답을 다시 검사했다. **15/16은 JSON 문법이 유효**했지만, 15개 모두 허용되지 않은 intent를 포함했다. emotion12건, pace9건, energy13건, expressiveness13건의 enum 위반과 tts_instruction 누락2건도 있었다. 별도의 재로드 test 응답은 반복·384-token cap 때문에 JSON을 완성하지 못했다. 기존 json_valid 지표는 문법뿐 아니라 enum/소비자/종료까지 합친 계약 지표였으므로 이를 각각 분리해 진단한다.

PC의 `PersonaManager` 문구에는 “주어진 스키마를 따른다”는 지시만 있었고 실제 허용 enum/필수 키 schema는 메시지나 생성기에 전달되지 않았다. Android는 schema를 llama.cpp grammar에 넣지만 기존 HF 평가는 제약 없는 greedy 생성이었다. 따라서 PC 평가가 앱의 출력 제약을 재현하지 못했다. 승인한 train4개로10step만 수행한 실험을 통해 이 누락이 해결됐다고 가정한 것도 타당하지 않다.

수정은 다음과 같다.

- `legacy`: 이전 누락 조건을 명시적으로 재현한다. 모델/데이터/기존 결과를 수정하지 않는다.
- `schema`: 앱의 실제 schema asset에서 필수 키/enum을 읽어 기존 system persona 뒤에 전달한다. persona/history 원본은 수정하지 않고, tts_instruction 빈 문자열과 소비자의 발화 제한도 명시한다.
- `constrained`(평가 기본값): schema 전달에 더해 byte 기반 decoder로 생성 중 허용 토큰을 JSON Schema로 제한한다. 출력 문자열에서 JSON을 추출하거나 enum을 사후 치환하지 않는다. grammar가 완성되기 전 EOS를 허용하지 않으며, 생성 후 소비자 계약을 다시 확인한다. 토큰 한도·미완성·소비자 위반은 계속 실패로 남기고 대화 기억에 넣지 않는다.
- JSON 문법·schema·소비자·종료를 별도 진단하고, 원문 없이 오류 코드와 필드 경로만 보고서에 남긴다. `--case-ids`로 특정 실패를 재현할 수 있다. `--include-heldout`은 학습에 들어가지 않은 승인 test 질문을 추가한다.

## 구현·환경 호환성

최종 경로는 [XGrammar0.2.9](https://pypi.org/project/xgrammar/0.2.9/)(Apache-2.0)/apache-tvm-ffi0.1.11이다. 고정 wheel을 별도 artifact 디렉터리에 설치했다. 기존 `.venv-llm`의 freeze는 이전과 동일하다. 기존 학습 requirements나 설치된 Transformers/PEFT/TRL 코드는 변경하지 않았다. 공개 `TokenizerInfo`/`GrammarCompiler` 및 [HF LogitsProcessor](https://github.com/mlc-ai/xgrammar/blob/main/python/xgrammar/contrib/hf.py)를 사용하며, 컴파일한 grammar는 재사용하고 상태가 있는 processor는 매 생성마다 새로 만든다.

처음 시험한 LM Format Enforcer0.11.3 경로는 parser 생성 시점의 ASCII 문자 집합 때문에 한국어를 잘못 중단했다. 이를 수정하고 현대 한글을 추가했지만, conv37의 `🎉`처럼 여러 byte 토큰으로 조립되는 emoji에서도 같은 한계가 남았다. 이 문자 집합 경로를 최종 구현으로 채택하지 않고, byte 수준에서 Unicode를 처리하는 XGrammar로 교체했다. 비교 중단/실패 기록과 초기 구현은 로컬에 보존했다. 실제 Qwen tokenizer의 `슬픔을 느껴 🎉` 스트림·잘못된 enum·미완성 EOS를 검사하는 회귀를 포함한다.

GPU bitmask 적용을 위한 Triton 초기화에 C 컴파일러가 없어 첫 XGrammar 모델 실행은 실패했다. 새 CHLOE 전용 Ubuntu에 `gcc`/`python3.12-dev`를 `--no-upgrade`로 추가했다. Windows, GPU 드라이버, 기존 Python venv 패키지는 변경하지 않았다. 이 실패도 로컬 로그로 남겼다.

거부 테스트를 보완하던 중 XGrammar0.2.9가 `pattern`과 min/maxLength를 함께 받으면 길이를 무시한다는 경고도 확인했다. 생성용 schema에서 이 조건을 `[^{}<>]{1,220}` 하나로 합쳐 동일한 한계를 표현하고,221자·금지 문자·잘못된 enum·비어 있지 않은 tts_instruction이 실제 grammar에서 거부되는지 검증했다. 원본 schema asset과 최종 소비자 검증은 그대로 유지한다. 수정 전 부분 비교는 중단해 보존했고 최종 규칙으로 전체를 다시 실행했다.

모델의 text EOS248044와 chat im_end248046을 모두 사용한다. seed42, greedy, thinking=false, max_new_tokens384, context2048, NF4/BF16, 같은 GPU·tokenizer·persona·입력을 두 후보에 동일 적용한다. 문맥 그룹은 각 후보 자신의 유효 응답으로만 기억을 구성하며4턴/1200자 상한을 유지한다. 이 Python decoder는 Android llama.cpp grammar와 구현/성능이 같다는 뜻이 아니다. Unicode 길이 등 소비자의 더 엄격한 제약은 별도 검증으로 실패 처리한다.

## 재현

Linux clone 루트에서 기존 `.venv-llm`과 원본/adapter를 사용한다. 새 decoder 폴더와 새 결과 경로만 만든다. 기존 출력이 있으면 덮어쓰지 않는다.

```bash
.venv-llm/bin/python -m pip install --no-deps --require-hashes \
  --target artifacts/llm-training/contract-deps-xgrammar-20261114 \
  -r training/requirements.contract.txt
.venv-llm/bin/python -m unittest discover -s training/tests -v
.venv-llm/bin/python training/scripts/evaluate.py \
  --config training/configs/smoke.json --compare-base --include-heldout \
  --contract-mode constrained \
  --output artifacts/llm-training/contract-20261114/xgrammar-final
```

비교용 이전 조건 재현에는 `--contract-mode legacy --limit 4`, schema 전달만 하는 대조에는 `--contract-mode schema --limit 4`를 사용한다. 같은4개 입력과 나머지 생성 조건을 유지한다. 전체 로그·응답은 로컬 artifact에만 보관하고 PR에 포함하지 않는다.

## 실행 결과

| 조건 | 입력 범위 | 원본 계약 통과 | adapter 계약 통과 |
| --- | --- | --- | --- |
| 이전 schema 누락 조건 | 같은 첫4질문×2말투; 보존 응답 소급 진단 | 0/8 | 0/8 |
| 실제 schema 전달만 | 같은 첫4질문×2말투 | 4/8 | 8/8 |
| 최종 byte 제약·소비자 검증 | 고정54질문+이전 실패 test1질문, 각각2말투 | **110/110** | **110/110** |

마지막 행의 말투별 결과는 원본 반말55/55·존댓말55/55, adapter 반말55/55·존댓말55/55다. JSON 문법/schema/소비자 계약/EOS 모두220/220이었다. 최대 생성160tokens, 최대 prompt612tokens로384/2048 제한 안에 들어왔다. 이전 반복 test 질문도 두 후보/두 말투에서 모두 통과했다. 문맥 질문은 각 후보 자신의 이전 유효 응답을 사용하므로 전체 토큰열은 달라질 수 있지만 입력 순서·기억 상한·생성 규칙은 같다.

세 조건을 한데 섞어 학습 효과로 보고하지 않는다. 첫 두 행은 같은4입력에서 schema 누락 효과를 확인한 대조다. 최종 행에서는 두 후보 모두 같은 생성 제약을 적용했으므로 구조적 통과를 강제 decoder와 분리된 adapter 품질 이득으로 해석할 수 없다. 사람의 자연스러움·말투·자기소개·과잉 공감·정직성 점수는 모두 null이고, 블라인드 사람 평가는 미실행이다.

비민감 증거: [비교 집계·55개 case별 통과표·보존 해시](local-llm-contract-20261114/comparison.json), [이전 실패 진단](local-llm-contract-20261114/prior-failure-diagnosis.json), [중단/실패를 포함한 시도 기록](local-llm-contract-20261114/attempts.json), [회귀 검사](local-llm-contract-20261114/checks.json). 원문과 중간 실패 로그는 `artifacts/llm-training/contract-20261114/`에만 보존한다. 최종 실행 반환0, 회귀24개 통과다.

원본 checkpoint SHA `aa33250c4fc64891ddfaba3a314fd9542ea371843c387178b425fbcc5ed680b1`, adapter SHA `661873993a9c70089937a64d9282e21a1ce2b622a5b60764305159c0c98bb025`가 이전과 일치한다. 기존 venv freeze도 같다. 최종 decoder wheel 두 개의 SHA는 집계와 `requirements.contract.txt`에 고정했다.

회귀24개가 통과했다. 실험 decoder의 전체 비교 중단과 문자 집합 수정 전의 실패 로그도 로컬에 보관한다. checkpoint/adapter SHA와 기존 venv 불변을 재검증했다. 장기 학습이나 기존 모델 교체는 수행하지 않는다.

남은 범위는 사람 품질 검토, 더 넓은 입력/Unicode/장시간 검증 및 Android의 실제 llama.cpp 경로 비교다. Python에서220회 통과했다고 모바일 runtime이 검증된 것은 아니다. 이번에는 GGUF 변환·모델 ID 등록·앱 교체·휴대전화 실행을 하지 않았다.
