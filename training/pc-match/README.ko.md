# 별도 PC 4B 실행 도구

## 최소 경로 / 현재 처리 비교 후속

[208개 새 응답과 직접 평가](../../docs/validation/local-llm-route-ablation-report.md)를 추가했다. `RouteBridge.java`, `compare_routes.py`, `training/configs/route-ablation-new-cases.json`은 실험 전용이며 제품 코드는 바꾸지 않는다. 기존54개 고정 system과 새20개/대화5개의 실제 PersonaManager system은 집단별로 구분한다. 경로 사이에는 같은 system/schema/예산/모델을 쓴다. 새 대화는 실제 manager의 최대4쌍/1200 UTF-16자 제한과 자신의 최종 응답을 사용한다. 모든 단계의 반사실적 결과를 최소 경로의 이력에 넣지 않는다.

```powershell
python -X utf8 training/pc-match/compare_routes.py --output NEW_ARTIFACT_DIRECTORY --previous artifacts/llm-training/pc-4b-20261115 --jdk JDK_DIRECTORY --model EXISTING_SAME_4B.gguf --schema app/src/main/assets/conversation-schema.json
python -X utf8 training/scripts/export_route_ablation.py --artifacts NEW_ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

runner는 이전 최종 bridge classpath와 소스가 같은 `6b2ebf0` 기준의 production classes/ordered JSON shim을 재사용하고 실험 bridge만 새로 컴파일한다. 기존54개 입력/소비 동등성을 먼저 확인하고, 요청 순서/소스/모델 해시를 실행 전에 고정한다. **제품 소스를 바꾼 후에는 이전 compiled classes를 그대로 재사용하면 안 된다.** 실제 정책/manager를 새로 컴파일하고 classpath와 동등성 근거를 갱신해야 한다. 이번 실행은 production 소스가 바뀌지 않은 조건이다.

export 전에 `judgments.local.json`에 실제 각 단계 발화에 대한 GPT 직접 판정(6criteria/이유/출처)을 제공해야 한다. `verification.local.json`이 있으면 보존 검사/고의 오류 대조 결과도 포함한다. exporter는 의미 점수를 만들어내지 않고, 누락·설정·이력 혼입·계약·판정 범위와 고정 소스 해시를 검증한다. 소스 해시는 실행 당시 바이트이며 Git의 LF/CRLF 변환만 동등하게 허용한다. 새 출력 폴더만 허용하고 이전 응답은 덮어쓰지 않는다. 이 실험은 JSON/220자 제한을 없앤 자유 출력이나 PocketPal 제품 전체의 재현이 아니다.

[실제 실행/품질/미완료 경계](../../docs/validation/local-llm-pc-4b-report.md)를 먼저 읽는다. 기존 GGUF를 읽기 전용으로 사용하며 학습/변환/adapter 적용 도구가 아니다. 원본 폰 앱과 학습 venv에 설치하지 않는다.

## 구성

- `download_inputs.py`: 공개 build-inputs manifest의 URL/크기/SHA를 검사하며 새 폴더에만 받는다. 모델 파일은 받지 않는다.
- `bootstrap_runtime.py`: WSL 새 root에 tools-env, GNU compiler와 CUDA 파일을 추출한다. apt-get download만 사용하며 apt install/update·전역 pip install은 없다. 학습 freeze/dpkg 목록이 유지되는지 검사한다.
- `CMakeLists.txt`, `worker.cpp`: pinned llama.cpp common chat-session과 같은 tokenize/apply_sampling/finish 순서를 사용하는 CPU/CUDA JSONL worker다. CPU는 empty devices + offload_kqv/op_offload false, GPU는99요청/33레이어 실제 offload다. 별도 실험 바이너리이며 Android JNI 라이브러리를 PC에서 실행하는 것이 아니다.
- `build_ordered_json.py`: 지정한 공개 source jar SHA를 확인하고 JSONObject의 backing map만 순서 보존형으로 바꾼 호환 jar를 만든다. 원본 jar는 유지한다. 출처는 `com.vaadin.external.google:android-json:0.0.20131108.vaadin1`, Apache-2.0 Android JSON 코드다. source jar URL은 Maven Central의 같은 좌표 `-sources.jar`이며 실제 SHA는 코드/manifest에 고정한다.
- `PcPolicyBridge.java`: 실제 production Java 정책과 Kotlin VoiceDirector를 JVM에서 소비한다. Android 전체 UI/TTS 동작을 대신하지 않는다.
- `prepare_comparison.py`: 보존된 합성 입력/기기 감사와 모델 입력54개, 기존 phone 출력79개 소비 동등성을 검사한 뒤 새 PC suite/gate를 만든다. 과거 출력은 이 검증에만 사용하며 새 추론의 응답으로 대체하지 않는다.
- `run_comparison.py`: WSL worker와 JVM bridge를 각각 열어 모든 요청을 새로 생성하고 응답마다 즉시 새 JSONL에 저장한다. 모델은 Windows 원본 파일을 /mnt 경로로 읽는다. 도구 stderr는 별도 로컬 파일이다.

실제 설치 폴더는 WSL `/home/chloetrain/chloe-pc-4b-20261115`, source commit `aa75ff3239f9cc675b081697deda9e1b112345c6`이다. 같은 source archive를 사용했으며 upstream Git build-info unknown은 별도 provenance manifest로 설명한다. CUDA/CPU의 수치/출력이 같다고 가정하지 않는다.

## 재현 순서

1. [고정 다운로드 목록](../../docs/validation/pc-4b-20261115/build-inputs.json)으로 새 다운로드 디렉터리를 만든다.
2. WSL에서 `bootstrap_runtime.py --root NEW_ROOT --downloads MOUNTED_DOWNLOADS --manifest MOUNTED_MANIFEST --training-root EXISTING_TRAINING_ROOT`를 실행한다. 기존 root에 덮어쓰지 않는다.
3. CMake/Ninja는 새 tools-env의 것만 사용한다. host C compiler는 기존 gcc, CXX/CUDA_HOST_COMPILER는 NEW_ROOT/bin/g++, CUDA compiler/Toolkit_ROOT는 NEW_ROOT/cuda다. `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DCMAKE_BUILD_TYPE=Release`와 archive source의 `-DLLAMA_SOURCE=...`를 지정해 새 build 디렉터리에 `chloe_pc` target만 빌드한다. PowerShell에서는 `.cpp`가 포함된 전체 -D 인자를 인용한다. 실제 구성/빌드 로그는 로컬 artifact에 보존돼 있다.
4. JSON source jar를 별도 폴더에 받아 `build_ordered_json.py`로 shim을 만들고 기존 cache를 읽는 `training/scripts/test_grounding_policy.py`에 그 jar를 전달한다. 새 출력 폴더만 사용한다.
5. `prepare_comparison.py`에 JDK, 방금 컴파일한 policy classes, shim jar, 기존 Kotlin stdlib jar를 전달한다. 현재 작업의 보존된 합성 artifacts가 필요하다.
6. 같은 gate를 CPU/CUDA로 각각 실행하고 native 정상 종료·JSON 계약·token ID·실제 offload를 확인한다. 그 뒤 같은 suite108개를 CUDA로 실행한다. GPU와 CPU/폰 결과는 섞지 않는다.

```powershell
python training/pc-match/run_comparison.py --input SUITE.json --output NEW_RESULTS.jsonl --model EXISTING_SAME_4B.gguf --schema app/src/main/assets/conversation-schema.json --bridge-classpath LOCAL_CLASSPATH.txt --jdk JDK_DIRECTORY --backend cuda
python training/scripts/export_pc_4b_results.py --artifacts ARTIFACT_DIRECTORY --output NEW_PUBLIC_DIRECTORY
```

worker의 model/schema 인자는 read-only 입력이다. 출력 JSONL은 새 파일만 허용하며 중복 실행으로 기존 결과를 덮어쓰지 않는다. raw JSON과 실제 최종 speech를 분리하고, quality는 GPT가 직접 읽어 고정한 판정 파일에서만 가져온다. 키워드 채점으로 품질을 만들지 않는다. empty/token-limit/parse 실패는 실패로 남긴다.

## 폰 중단 기록

폰은79/108에서 사용자 요청으로 중단했고 나머지29개와 Android 최종7개는 실행하지 않았다. 원본 파일과 checkpoint는 로컬에 보존돼 있다. `export_turn_guidance_results.py --partial`로39쌍+after 단독1개를 구분한다. 이번 PC108개와 합산하지 않는다. 원본 APK 설치·장기 자기 생성 대화·실제 음성은 별도 미검증 항목이다.
