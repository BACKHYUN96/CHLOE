# Qwen3.5 입력 상태 재사용 조사 · alpha13

## 확인한 소스

pinned llama.cpp aa75ff3239f9cc675b081697deda9e1b112345c6:

- include/llama.h: n_rs_seq 실험적 recurrent rollback snapshots, llama_memory_seq_rm은 부분 삭제 실패 가능, llama_state_seq_get/set_data가 별도 제공된다.
- src/llama-memory-recurrent.cpp: seq_rm은 최근 ubatch에서 보존한 cell.rs_max 이내에서만 제한적 rollback 가능하며 범위를 벗어나면 false다. 임의 토큰 위치의 과거 recurrent 상태를 일반 KV처럼 잘라내는 기능이 아니다.
- CHLOE llm_jni.cpp는 모델별 context를 재사용하지만 매 요청 memory_clear 후 전체 prompt를 decode한다. n_rs_seq를 따로 켜지 않는다.
- 이전 assistant history는 안전한 spoken_text로만 저장한다. 원래 생성한 JSON 토큰열과 다음 템플릿에 들어가는 assistant 본문이 다르므로, 생성 종료 상태 뒤에 새 입력을 단순 연결하면 정확한 다음 프롬프트와 일치하지 않는다.

## 이번 결정

입력 상태 재사용은 활성화하지 않는다. APK에서 성능 기능으로 표시하지 않고 전체 prefill 경로를 유지한다. API 존재만으로 Qwen3.5 상태 복원 검증을 대신하지 않는다. alpha13은 답변 규칙/같은 조건 평가 도구 변경이며 prefill 속도 패치 성공을 주장하지 않는다.

## 실제 구현 전 필요한 검증

1. 두 모델에서 hybrid KV+recurrent 상태의 완전 snapshot/restore와 위치/바이트 수/실패를 검사한다. 토큰 하나만 저장하는 KV 꼬리 삭제로 대체하지 않는다.
2. 생성 직전 prompt 경계 checkpoint를 기준으로 다음 렌더링과 정확히 일치하는 prefix 토큰을 확인한다. tokenizer가 경계에서 합치는 토큰까지 검사한다. history/스키마/persona/모델/말투 변경과 문맥 잘림은 무효화한다.
3. 동일 seed와 greedy 입력에서 full-prefill과 restore 경로의 생성 토큰 및 답변을 비교한다. 이름/자기소개/4턴 이상/문맥 잘림/취소/worker 재시작/모델 변경을 포함한다.
4. snapshot 복사·추가 prefill·복원 시간과 RAM 증가를 모두 포함해 실제 이득을 측정한다. RAM 비용이 크거나 복원 실패 시 완전 clear/full-prefill로 복구한다. 실패 후 hybrid 상태가 부분적으로 바뀐 채 이어가지 않는다.
5. 캐시에는 대화 내용이 있으므로 우선 메모리에만 보관하고 stop/reset/모델 교체 시 폐기한다. 파일/Git/Drive에 자동 저장하지 않는다.

장치/선택 GGUF를 실행할 공간이 없는 현재 환경에서 위 실측을 수행하지 못했다. 로컬 학습 코드와 별도 개발 과제로 유지한다.
