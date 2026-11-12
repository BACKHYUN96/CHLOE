# LLM GPU Lab · alpha15

## 목표와 근거

Galaxy S26 Ultra에서 품질/응답속도/문맥을 우선한다. 전력·발열은 측정 대상으로 두며 사용량 자체를 목표로 만들지 않는다. OS 열 보호/루팅/클럭 강제/불필요한 부하 생성은 하지 않는다. PC 서버나 로컬 PC 학습 코드와 분리한 Android LLM 실험이다.

조사한 PocketPal 소스:
- https://github.com/a-ghorbani/pocketpal-ai/blob/main/package.json : llama.rn 0.13.0-rc.9 의존성.
- https://github.com/a-ghorbani/pocketpal-ai/blob/main/src/utils/deviceCapabilities.ts : Android Adreno+i8mm+dotprod의 OpenCL 경로 명시.
- https://github.com/a-ghorbani/pocketpal-ai/blob/main/src/store/ModelStore.ts : n_gpu_layers/no_gpu_devices 설정과 capability 검사.
- llama.rn 조사 ref d3190c58c83a58fb892aea5718399664c96d3c9a 의 android/src/main/rnllama/CMakeLists.txt : OpenCL/Adreno kernels/ICD link 경로.

이것은 조사 당시 공개 소스이며 사용자가 설치한 PocketPal의 정확한 버전/선택 backend를 복원한 것은 아니다. 사용자 화면의 Q4_0과 CHLOE Q4_K_M도 다르다. GPU92%나25W만으로 어느 앱이 더 효율적이거나 빠른지 확정하지 않는다.

이번 CHLOE 경로는 pinned llama.cpp aa75ff3239f9cc675b081697deda9e1b112345c6의 Vulkan이다. OpenCL을 복제한 구현이라고 부르지 않는다. Vulkan은 기존 Q4_K_M과 현재 hybrid 모델 연산 경로를 유지한 채 Android 표준 GPU API로 비교하기 위해 선택했다. upstream ggml-vulkan.cpp에 GATED_DELTA_NET/SSM_SCAN/SSM_CONV 지원 분기가 있지만 기기·shape별 지원 여부와 실제 가속은 별도 검증이다. Adreno OpenCL/양자화별 최적화는 후속 별도 비교이며 이번 APK에 포함하지 않는다.

## 모드와 실행

- CPU: n_gpu_layers=0, 빈 device 목록, context의 op_offload/offload_kqv=false. Vulkan registry는 자동 probe하지 않고 CPU 경로로 시작한다.
- GPU16레이어: 요청 n_gpu_layers=16, Vulkan GPU 지정. 남은 레이어/지원하지 않는 연산은 CPU와 분담될 수 있다.
- GPU최대: 요청 n_gpu_layers=-1, Vulkan GPU 지정. 이는 모든 연산을 GPU로만 실행한다는 뜻이 아니다. offloadable layer 수와 지원 op에 의해 배치가 정해진다.

CPU는 Vulkan을 초기화하지 않도록 registry 자동 등록을 막고, GPU 선택 시에만 명시적으로 Vulkan backend를 추가한다. 모드 전환은 이전 worker/대화 문맥을 초기화한다. native load key는 파일+오프로딩+context이며 설정이 다른 객체를 재사용하지 않는다. backend 미탐지/오프로딩 보고0/초기화 실패는 오류로 반환하며 CPU로 몰래 대체하지 않는다. native abort/OOM은 worker 연결 종료로 UI에 전달한다. 실패 시 부분 로드 객체도 해제한다.

GPU 선택 시 worker 연산 watchdog600초, CPU는 기존2B/4B180초·9B600초다. 첫 GPU 실행은 driver shader/pipeline 준비가 길 수 있다. 중지 버튼은 worker 종료 경로다. 600초가 정상 응답 목표라는 뜻은 아니다.

기존 모델 파일, Q4_K_M, persona, schema, greedy/seed42, 입력4/6/8 선택과 답변 CPU4, 모델별 context/출력384 한도는 유지한다. 실제 CPU/GPU 소수점 연산 차이로 생성 문장은 달라질 수 있으며, 다른 문장을 얻었다고 양자화가 바뀐 것은 아니다. TTS JNI/모델/말투 설정은 건드리지 않는다.

## 상주와 문맥

2B/4B는 기본 TTS 전 LLM 해제 off로 두어 상주를 요청한다. 9B 선택 시에는 기존대로 해제 on으로 시작하지만 사용자가 off를 선택할 수 있다. 9B 강제 해제 정책을 alpha15에서 명시적 선택으로 변경했다. 상주는 LLM 추론과 TTS 추론을 동시에 실행하는 병렬 파이프라인이 아니다. 메모리 상주 여부만 바꾸며 자동 TTS 순서와 worker 경계는 같다. GPU모델+TTS의 동시 상주/peak RAM/기기 성공은 미검증이다.

'대화 초기화'는 worker와 문맥을 함께 정리한다. '문맥만 비우기 · 모델 유지'는 Kotlin history/현재답변/비교 진행만 비우고 로드된 LLM을 유지한다. 다음 native 요청은 여전히 memory_clear/full-prefill한다. KV prefix cache를 새로 구현한 것이 아니다. 이 기능으로 같은 입력의 cold/warm load 비용을 나눠 볼 수 있다. 화면 이탈/중지/모드 변경은 기존처럼 worker를 종료한다. 대화 기록은 모델 상주와 분리돼 유지되지만 대화 초기화하면 제거한다.

## 측정 해석

- requested_gpu_mode, requested_gpu_layers: 요청값.
- backend, gpu_description: 선택 backend와 Vulkan GPU 설명.
- offloaded_layers_reported/offloadable_layers_reported: pinned runtime의 'offloaded N/M layers to GPU' 로그에서 추출한 모델 배치 보고. 미보고는 null이다.
- gpu_placement_confirmed: GPU 요청+양수 배치 보고. 이것은 모든 연산이 GPU에서 실행됐거나 GPU 사용률이 일정 이상이라는 증거가 아니다.
- gpu_execution_utilization_percent: 앱이 계측하지 못하므로 null. CPU 온도/전체 시스템 전력도 만들어내지 않는다.
- thermal_status_start/end: Android PowerManager 열 상태 enum. 배터리/CPU 온도(섭씨)가 아니다.
- load_ms/native_request_ms/client_request_ms: 모델/드라이버 초기 준비와 Binder/전체 대기를 나누어 본다. 기존 first_token_ms는 load를 제외하고 prefill 시작부터 첫 샘플까지다. 스피커 소리 지연이 아니다.
- prefill_ms/decode_ms/decode TPS와 기존 전체 분모 TPS는 분리한다. warm load0와 cold를 혼합해 개선율을 계산하지 않는다.

개인 입력/응답/추론 원문은 내용 없는 JSON에 추가하지 않는다. 로그 callback은 배치 숫자만 수집한다. TTS는 그대로이며 모델/음성을 새로 다운로드하거나 업로드하지 않는다.

## 폰 시험

1. alpha15를 Performance 앱 위에 업데이트. 모델은 그대로 사용.
2. 우선4B/입력6/같은 말투/persona로 CPU에서 짧은 문장1회. CPU기준을 남긴다.
3. GPU최대로 변경(문맥 초기화됨)하고 정확히 같은 문장. GPU장치·양수 reported layers·prefill/전체/client 시간을 확인한다. 실패하면 오류를 저장하고 CPU를 직접 선택해 복구한다.
4. GPU16레이어도 같은 조건으로 비교한다. 지원하지 않는 op가 많으면 최대 오프로딩이 더 느릴 수 있다.
5. cold 첫1회 후 문맥만 비우기로 같은 문장을 다시 생성해 warm을 분리한다. 필요하면 모드 순서를 바꾸고 반복한다.
6. 효과가 있는 모드에서 동일조건4문항, TTS후 재요청, 상주 on/off를 각각 비교한다. 9B는4B 실행이 확인된 후 선택한다.

새 폰 실측, GPU 사용률, 전력, 실제 가속, 품질 일관성,10/30분은 미측정이다. Q4_0 모델을 몰래 받거나 기존 모델을 덮어쓰지 않는다. PocketPal과 비교하려면 버전/같은 모델·양자화/문맥/출력 길이/streaming 표시 조건까지 맞춰야 한다. 이번 패치는 텍스트 streaming을 추가하지 않았으므로 문장 완성 후 표시 방식은 같다.

## 빌드

Android SDK35/NDK28.2.13676358/JDK17/CMake3.22.1 및 host glslc, Vulkan C++ headers, SPIRV-Headers CMake config가 필요하다. 시스템 Vulkan loader(libvulkan.so)는 NDK로 링크한다. 드라이버를 APK에 복제하지 않는다. SDK 파일은Git에 넣지 않는다.

이 환경에서 사용한 Vulkan-Headers409c16be502e39fe70dd6fe2d9ad4842ef2c9a53, SPIRV-Headers6efe5ae6b7c6ad29da3f2cc3f164b9c3d72b78b1, NDK glslc shaderc2022.3. Vulkan/GLSL 확장 support test 결과는 CMake에서 결정한다. pinned upstream은 SPIRV 패키지를 찾지만 include target 연결이 없어 부모 CMake에서 find_package 및 ggml-vulkan의 target link를 보완했다. external submodule은 변경하지 않았다.

```bash
./gradlew --max-workers=2 -PperformanceEdition=true \
 -PllmVulkanSdk=/path/to/sdk-prefix \
 -PllmSpirvHeaders=/path/to/directory-containing-SPIRV-HeadersConfig.cmake \
 -PllmVulkanHeaders=/path/to/include-containing-vulkan \
 -PllmGlslc=/path/to/host/glslc \
 :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

Windows SDK에는 Include/Bin/Lib 등 다른 경로가 있을 수 있으므로 실제 설치 경로를 넣는다. Vulkan SDK는 공식 LunarG/Khronos 배포를 사용한다. Vulkan 디버그 layer/validation은 최종 추론 성능 설정에 켜지 않는다.

## 이번 빌드 환경 정리

디스크 여유 확보를 위해 작업 도구가 과거에 생성한 Vulkan TTS 빌드 캐시와 CPU LLM 이전 빌드 캐시, 이미 Drive 업로드가 검증된 이전 APK 로컬 사본을 정리했다. alpha14 설치본/모델/음성/사용자 파일은 보존했다. 처음 SPIRV config 경로와 imported target 범위/include 연결에서 실패했으며 보완 후 최종 전체 빌드·단위 테스트·native 정책 테스트·16KB 검사에 통과했다. 소스/셰이더 컴파일 성공을 기기 실행 성공으로 해석하지 않는다.
