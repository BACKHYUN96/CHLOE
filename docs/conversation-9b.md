# Qwen3.5-9B Android 실험 · alpha14

## 범위와 지원 근거

기존 2B/4B 설정·모델/Sohee를 보존하고 9B를 추가 실험 옵션으로 제공한다. 27B는 포함하지 않는다. 동일 조건 비교의 소개/역할/이름 기억/피곤함 4문항을 같은 버튼으로 사용한다.

원본: https://huggingface.co/Qwen/Qwen3.5-9B (Apache-2.0)
변환 배포: unsloth/Qwen3.5-9B-GGUF (모델 API license apache-2.0)
revision: 3885219b6810b007914f3a7950a8d1b469d598a5
파일: Qwen3.5-9B-Q4_K_M.gguf
크기: 5,680,522,464 bytes (5.68GB / 약5.29GiB)
SHA256: 03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8

Hugging Face API에서 revision/크기/LFS SHA를 확인했다. HTTP Range로 최대32MiB만 읽어 GGUF v3/general.architecture=qwen35/general.file_type=15를 확인했다. 큰 tokenizer metadata 뒤의 file_type 위치는10942802였다. 전체 모델을 클라우드에 다운로드하거나 해당 SHA를 재계산한 것은 아니다. 폰에서 가져올 때 전체 크기/SHA를 계산해 고정 manifest와 대조한다. 현재 pinned llama.cpp는 qwen35를 처리하지만 이 9B 파일의 실제 모델 로드·생성·기기 안정성은 미검증이다.

## 폰에서 다운로드와 설치

1. alpha14 APK를 기존 Performance 앱 위에 업데이트한다. 앱 삭제/데이터 초기화 불필요.
2. 아래 고정 revision 링크를 폰 브라우저에서 연다. 다른 Q4 파일이나 분할 모델/mmproj는 받지 않는다.

https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q4_K_M.gguf?download=true

3. 기기에 다운로드 파일과 앱 내부 복사본을 동시에 두므로 약11.36GB + 여유가 필요하다. 약12GB 이상은 준비 예산이며 파일시스템/다운로드 앱에 따라 더 필요할 수 있다. importer는 내부 저장소에 모델 크기+512MiB 여유를 확인한다.
4. Conversation Lab에서 9b 선택 → 로컬 Q4 GGUF 가져오기 → 다운로드한 파일 선택. 해시 계산과 복사에는 시간이 걸린다. 성공 후 2B/4B와 구분된 conversation-models/9b.gguf에 저장된다. 기존 파일 덮어쓰기는 거부한다.
5. 입력6/생성4, 원하는 말투를 설정하고 우선 짧은 인사 한 번으로 모델 로드 확인. 성공 후 동일 조건 비교 시작/다음으로4문항 실행하고 측정 JSON을 내보낸다. 반복 버튼은 초기4문항이 통과한 뒤 검토한다.

다운로드에는 인터넷을 쓰지만 CHLOE 앱의 모델 추론에는 INTERNET 권한/클라우드 API가 없다. 사용자의 데이터/음성을 외부에 올리지 않는다.

## 메모리 및 시간 정책

- 2B/4B context2048/최대384 생성토큰/연산180초 유지.
- 9B context1024/최대384 생성토큰/연산600초. 고정4문항이 이 예산 안에 들어가는지는 실제 token 수로 확인한다. 긴 대화가 예산을 넘으면 오류를 표시하며 조용히 문맥을 잘라내지 않는다.
- 입력 스레드4/6/8 선택, 생성4 고정. 기본4는 변경하지 않는다. 비교할 때 같은 입력6을 선택한다.
- 9B는 LLM/TTS 해제 정책을 강제한다. LLM 요청 전 TTS 중지, TTS 시작 전 LLM 중지. 동시 상주 토글은9B에서 비활성이다. 모델 선택 시 해제 기본값을 켜며2B/4B에서도 안전한 기본 해제 정책을 유지한다.
- 15초 bind/접수 timeout과 중지 버튼은 유지한다. 10분은 성능 목표가 아닌9B 복구 한도다. worker native 종료/OOM은 UI 오류로 처리하지만 OS 전체 메모리 압박의 영향을 방지한다고 보장하지 않는다.
- 모델5.68GB는 전체RAM 사용량이 아니다. 실제 peak/초기 load/반응/발열/품질은 모두 미측정이다. 9B가 반드시 자연스럽거나 실시간이라는 주장도 하지 않는다.

context_tokens/max_generation_tokens/prefill_threads/decode_threads와 model=9b를 기록한다. 9B context는 작으므로2B/4B와 장문 capacity를 동일하게 비교하지 않는다. 짧은 동일 fixture의 실제 입력 token 수/실패/속도를 비교한다. TTS는 기존1.7B Sohee이며 변경하지 않았다.
