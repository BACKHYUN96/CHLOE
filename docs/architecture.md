# CHLOE 아키텍처 · TTS 비교 실험 추가

기존 설계는 [ARCHITECTURE.ko.md](ARCHITECTURE.ko.md), 음성 기준은 [VOICE_REFERENCES.ko.md](VOICE_REFERENCES.ko.md)를 유지한다.

## 경계

- 기존 경로: MainActivity → LabViewModel → VoiceEngine / LocalVoiceEngine → VoiceWorkerService (`:voice`) → NativeBridge → pinned qwen3-tts.cpp. 기존 모델 라이브러리/가져오기/말투 표본은 보존한다.
- 실험 경로: ComparisonActivity → ComparisonViewModel → ComparisonClient → ComparisonWorkerService (`:comparison`) → ComparisonNative. 기존 JNI 함수와 별도 C++ engine 객체를 사용한다. 프로세스 종료가 다른 엔진의 객체를 파괴하지 않는다.
- 저장소: 기존 `files/models/`는 읽어 기준 Sohee를 사용한다. 실험 `files/tts-comparison/design/`는 별도 모델, `clips/`는 WAV와 개별 JSON, root에는 batch/오류/취소/평가 JSON을 둔다. 모델 가져오기는 staging 검사 후 rename으로 게시하며 기존 모델을 덮어쓰지 않는다.
- 평가: ComparisonData는 공통 20문장/조건 검사/블라인드 pair를 정의한다. ComparisonStorage는 SAF·해시·WAV 형식과 경로를 검증한다. ComparisonWavPlayer는 16/24/48kHz를 원래 속도로 재생한다. 원래 24kHz WavPlayer는 변경하지 않는다.
- PC 도구: tts_comparison.py의 Qwen CLI/Vox C++/CosyVoice3 공식 Python CPU 어댑터가 같은 manifest를 만든다. 앱은 미연결 모델도 샘플 import 후 평가할 수 있다. 연구 구현의 존재와 CHLOE 실행 지원은 모델 목록에서 구분한다.

기존 화면에서 실험으로 이동할 때 기존 추론을 중지해 동시 모델 상주를 피한다. 실험은 화면이 활성화된 동안만 실행하며 작업 중 screen-on을 유지한다. 중지/백그라운드 이탈은 `:comparison`을 종료하고 완료 파일과 중단 기록을 보존한다. 모델 오류·native abort·OOM은 Binder 연결 종료로 UI에 알린다.

새 native backend는 기존 qwen3-tts.cpp/ggml을 교체하지 않는다. VoxCPM2 등 다른 ggml fork의 향후 통합은 별도 라이브러리·symbol/ABI·프로세스 경계를 검증한 후 추가한다. 원격 TTS·음성 인식·대화 생성·통화 관리 계층과 묶지 않는다. 앱은 INTERNET/마이크 권한을 추가하지 않는다.

## 재현성과 블라인드 평가

모델 ID/revision/변환 정밀도/음색/스타일/seed/sampling/플랫폼을 오디오마다 기록한다. 공통 조건과 모델별 조정은 분리하며 조건·문장·seed·플랫폼이 다른 파일을 한 A/B pair에 넣지 않는다. 파일명은 내부 UUID로 바꾼다. 점수는 6항목 1~5, 미입력은 null이며 메모와 공개 여부를 함께 저장한다. 공개 전 export는 모델 이름을 감추고 clip ID로 연결한다.

하드웨어 출력 타임스탬프와 실제 음향 도달 시간, buffered PCM과 streaming 청크, 로딩과 재사용, 호스트와 Android를 구분한다. CPU/GPU 비율·온도를 측정하지 못하면 추정값을 넣지 않는다. 안정성 반복은 통화 부하의 대리 시험으로만 해석한다.

모델/사용자 음성/개인 통화는 Git에 넣지 않는다. 실행은 local-only이며 개발 모델 다운로드는 별도 준비 단계다. 외부 음성 업로드는 별도 사용자 동의가 있을 때만 수행한다.

## PC 학습 실험 경계

`voxcpm2_lab.py`는 별도 로컬-PC 사전 점검·KSS 데이터 준비·LoRA 계획/실행 도구다. `voxcpm2_compare.py`는 공식 Python 경로의 adapter off/on 비교를 수행한다. 파일은 Git 제외 `artifacts/voxcpm2-local/`에 둔다. Android 엔진·모델·ABI를 변경하지 않는다. KSS의 비상업 조건과 실제 학습/기기 검증 상태를 `docs/voxcpm2-lora-local.md`에서 구분한다.

## 로컬 대화 엔진

ConversationManager/PersonaManager/DialogueContextManager/VoiceDirector/TtsInstructionMapper/ConversationEvaluator는 TTS와 독립이다. AndroidLocalLlmEngine은 :llm worker 및 별도 static llama.cpp 모듈을 사용하며 기존 LocalVoiceEngine으로 Sohee를 재생한다. 원격 구현은 없다. [설계와 미측정 항목](conversation-engine.md)을 따른다.

## alpha9 대화 출력 경계

LLM native는 pinned llama.cpp의 common_chat_session → apply_sampling/common_sampler → finish를 사용한다. Kotlin에는 파싱된 assistant content만 전달하며, 문법의 prefill/trigger를 수동으로 재구현하지 않는다. 토큰 한도/빈 응답/형식 실패는 명시적인 상태다. 안전한 spoken_text를 복구할 수 없는 실패 안내는 DialogueContextManager와 TTS로 보내지 않는다. 내용 없는 요청별 측정과 opt-in 로컬 진단 원문을 분리한다. [기준 감사와 단계별 통과 조건](CHLOE_BASELINE.ko.md)을 따른다. 새 TTS 어댑터와 STT/VAD는 이번 단계에 구현하지 않았다.

## LLM 연결 수명 · alpha10

AndroidLocalLlmEngine은 순수 Kotlin LlmRequestClient(요청 ID·진행 상태·타임아웃)와 AndroidLlmChannel(Binder binding)을 조합한다. stop은 채널 참조를 무효화한 뒤 프로세스 중지/바인딩 해제를 수행한다. 새 요청은 해제된 채널을 재사용하지 않는다. worker의 접수/연산 진행 이벤트는 완료 이벤트와 구분하고, 완료 전 busy를 풀지 않는다. 기존 native/TTS 경계와 모델 설정은 유지한다.

## alpha11 관측과 말투

PersonaManager는 UI 말투 설정을 명시하고 VoiceDirector는 생성 결과를 자동 치환하지 않는다. ConversationEvaluator의 register_warning은 보조 신호이며 자연스러움 점수를 대체하지 않는다. LLM native chat-template 객체만 모델 수명 동안 재사용하고 세션/샘플러는 매 요청 분리한다. 단계별 지연과 history_turns를 기록한다. UI 가시 프로세스 PSS 표본과 worker 자체 완료 PSS를 나누며 실제 앱 전체 최대 PSS는 미측정(null)이다.

## alpha12 입력 처리 비교

ConversationEngine request의 prefillThreads는 기본4, 허용4/6/8이며 LlmRequestClient → Binder payload → LlmWorker → 독립 LLM JNI로 전달한다. 단일 토큰 생성 스레드는4 고정이다. persona compact/alpha11 선택은 추론 설정과 별도 기록한다. 모델/KV/음질을 묵시적으로 바꾸지 않으며, 입력 처리 시간 단축과 생성 품질은 기기에서 각각 검증한다.
