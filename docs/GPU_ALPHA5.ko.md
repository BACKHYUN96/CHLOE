# alpha5 CPU / Vulkan / 하이브리드 실험판

Sohee 1.7B의 F16 + code predictor down projection 일부 F32, seed 42, 전체 문장 디코딩을 유지한다. 음질을 낮추는 양자화나 스트리밍 변경은 없다. GPU 속도 개선은 아직 기기에서 측정하지 않았다.

## 설치

`CHLOE-Voice-Lab-Performance-0.1.0-alpha5-arm64-debug.apk`를 기존 alpha4 Performance 위에 업데이트한다. applicationId와 서명키가 같아 기존에 가져온 모델은 유지된다. alpha3 원래 앱만 설치되어 있다면 Performance는 별도 앱이며 모델을 가져와야 한다. 기존 [1.7B 안정화 모델 패키지](ALPHA3.ko.md)를 그대로 사용한다. APK에 모델은 포함하지 않는다. 앱에 INTERNET 권한은 없으며 실행 중 서버를 사용하지 않는다.

## 세 버튼

- **CPU로 합성**: 모든 추론을 CPU로 수행한다. 기본 4스레드.
- **GPU 우선으로 합성**: Vulkan GPU에 모델과 지원 연산을 배정한다. ggml이 지원하지 않는 연산은 CPU fallback이다. CPU의 제어·토큰 샘플링·입출력도 남으므로 GPU 단독 실행을 의미하지 않는다.
- **하이브리드 분담으로 합성**: talker / code predictor는 GPU 우선, 오디오 decoder는 CPU다. 전체 음성 코드 생성 후 CPU 디코딩을 시작하는 **순차 분담**으로, 두 단계를 동시에 실행하는 병렬 파이프라인이 아니다.

모드 변경은 이전 worker를 종료해 메모리를 회수한 뒤 모델을 새로 로드하고 자동 합성한다. GPU 탐색·초기화 또는 GPU 가중치 배정 실패 시 CPU로 몰래 전환하지 않고 오류를 표시한다. 이후 CPU 버튼으로 복구할 수 있다. native abort / OOM / 드라이버 오류도 UI와 분리된 `:voice` 프로세스에서 처리되며 UI가 종료 사실을 표시한다.

초기화와 합성 각각 120초 제한이다. 초과하면 worker를 종료한다. 장문은 짧게 나누어 시험한다. 수동 스레드는 모두 남기되 자동 비교는 2·4·6 중 기기가 지원하는 수만 선택한다. 사용자 alpha4 자료에서 8스레드는 회당 약 23분 걸렸기 때문이다. 4·6의 중앙값 차이는 약 1%여서 절대 우열로 단정하지 않는다.

## 휴대전화 비교 절차

1. 1.7B, 4스레드, 같은 짧은 문장과 같은 말투 지시를 고정한다. 예: `안녕하세요? 저는 클로이예요.`
2. CPU → GPU 우선 → 하이브리드 순으로 모드당 최소 2회 생성한다. 첫 회는 로딩/커널 준비 영향이 있으므로 두 번째 이후와 구분한다. 역순으로도 반복하고 기기를 식힌다.
3. 각 결과에서 **측정 JSON**과 WAV를 내보낸다. 자동 재생을 켜면 실제 첫 재생 출력 타임스탬프도 측정할 수 있다. 미지원 기기는 null로 남는다.
4. 생성/RTF, 코드 생성·오디오 디코딩 시간, 초기화 시간, 첫 PCM·첫 출력, PSS·온도·열 상태를 함께 본다. 발음·단어 누락·음색·억양을 먼저 확인하고 출력 길이가 다르면 속도만 비교하지 않는다.
5. JSON `backend_diagnostics`의 transformer/decoder 장치와 단계별 `gpu_nodes`, `cpu_nodes`를 확인한다. 이 수치는 성공한 그래프의 **배정된 연산 노드 누계**다. GPU 사용률·FLOPS·GPU 커널 시간·전체 연산량 비율이 아니다. `simultaneous_parallel`은 false다.
6. `code_generation_ms`는 talker와 code predictor를 포함한 생성 단계, `audio_decode_ms`는 오디오 디코딩의 upstream wall time이다. `model_init_ms`는 별도 측정이며 generation_ms에 포함되지 않는다. `model_reused=false`는 초기화 후 첫 생성, true는 같은 모델의 재사용이다. 캐시가 완전히 차가운 상태를 보장하는 표시는 아니다.

화면의 GPU 사용률 상승만으로 추론 가속 여부를 판단하지 않는다. GPU는 행렬 연산에 유리할 수 있지만 작은 순차 토큰 처리·동기화·CPU fallback·드라이버 지원 때문에 CPU보다 느릴 수 있다. 하이브리드는 GPU decoder의 지원/속도가 좋지 않을 때 대안이 되는지 확인한다. 결과에 따라 가장 빠르고 음질이 유지되는 경로를 채택한다.

## 빌드 재현

기본 SDK/NDK/JDK는 alpha4와 동일하다. NDK 28.2.13676358, SDK CMake 3.22.1의 ninja 및 호스트 C/C++ 컴파일러가 필요하다. Windows는 Visual Studio C++ Build Tools 및 NDK windows shader-tools가 필요하며 이번 환경에서는 Linux 빌드만 검증한다.

빌드 PC에서 아래 Khronos 의존성을 준비한다. 앱 실행 중 다운로드하지 않는다.

```sh
git clone https://github.com/KhronosGroup/Vulkan-Headers.git ../Vulkan-Headers
git -C ../Vulkan-Headers checkout 409c16be502e39fe70dd6fe2d9ad4842ef2c9a53
git clone https://github.com/KhronosGroup/SPIRV-Headers.git ../SPIRV-Headers
git -C ../SPIRV-Headers checkout 6efe5ae6b7c6ad29da3f2cc3f164b9c3d72b78b1
cmake -S ../SPIRV-Headers -B ../spirv-build -DCMAKE_INSTALL_PREFIX=../vulkan-sdk
cmake --install ../spirv-build
# Linux 예시: SDK/NDK 경로는 각 PC에 맞게 지정
export PATH="$ANDROID_HOME/cmake/3.22.1/bin:$PATH"
./gradlew -PperformanceEdition=true -PvulkanEnabled=true \
  -PvulkanHeadersDir=/absolute/path/Vulkan-Headers \
  -PspirvHeadersDir=/absolute/path/vulkan-sdk \
  :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
```

`vulkanHeadersDir`은 소스 루트, `spirvHeadersDir`은 설치 prefix다. Windows는 `gradlew.bat`, 절대 경로 및 환경변수 구문을 사용한다. Vulkan을 끄면 `-PvulkanEnabled=false`로 헤더 의존성 없이 CPU APK를 빌드하며 GPU 버튼은 비활성화된다. 이때 GPU 요청을 native에서도 거부한다.

upstream qwen3-tts.cpp/ggml 커밋은 변경하지 않았다. `BackendOverlay.cmake`가 빌드 디렉터리에 복사본을 만들고 정확한 패치 위치 개수를 검증한다. GPU 강제 선택, CPU decoder 분담, fallback CPU 스레드 전달, 그래프 배정 측정만 삽입한다. 의존성이 바뀌어 위치가 일치하지 않으면 빌드가 실패한다.

Vulkan-Headers v1.4.313 및 SPIRV-Headers의 라이선스/고지는 `third_party/licenses/{vulkan-headers,spirv-headers}`에 보관한다. qwen3-tts.cpp/ggml MIT 및 Qwen 모델 Apache-2.0 조건도 그대로 적용된다. 모델 파일은 저장소·소스 ZIP에 넣지 않는다.

## 남은 검증

S26 Ultra의 Vulkan 초기화, 세 모드 반복 생성·전환, 오류 후 CPU 복구, 타임아웃과 중지, 백그라운드 이탈, 실제 속도·음질·발열은 연결된 기기가 없어 미실행이다. 현재 APK가 최대 하드웨어 성능을 달성했다고 주장하지 않는다. GPU/NPU 전문 커널, 동시 스트리밍 파이프라인, 원격 서버는 구현하지 않았다. 실제 빌드·호스트 검사 결과는 `validation/gpu-alpha5/build.json`에 기록한다.
