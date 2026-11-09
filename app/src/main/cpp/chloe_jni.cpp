#include <jni.h>
#include <android/log.h>
#include <gguf.h>
#include "qwen3_tts.h"
#include "qwen3_tts_c.h"
#include "chloe_backend_policy.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace {
std::unique_ptr<qwen3_tts::Qwen3TTS> engine;
bool instruction_supported = false;
using Clock = std::chrono::steady_clock;
double elapsed(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}
std::string string(JNIEnv* env, jstring input) {
    const char* chars = env->GetStringUTFChars(input, nullptr);
    if (!chars) throw std::runtime_error("Unable to read JNI string");
    std::string result(chars);
    env->ReleaseStringUTFChars(input, chars);
    return result;
}
void fail(JNIEnv* env, const char* message) {
    __android_log_print(ANDROID_LOG_ERROR, "CHLOE.Native", "%s", message);
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), message);
}
// Check actual GGUF metadata; filenames alone never establish CustomVoice support.
void validate_talker(const std::string& path, int expected_hidden) {
    gguf_init_params params{true, nullptr};
    std::unique_ptr<gguf_context, decltype(&gguf_free)> ctx(gguf_init_from_file(path.c_str(), params), gguf_free);
    if (!ctx) throw std::runtime_error("Invalid talker GGUF");
    auto key = [&](const char* name) { return gguf_find_key(ctx.get(), name); };
    auto type = key("qwen3-tts.model_type");
    if (type < 0 || gguf_get_kv_type(ctx.get(), type) != GGUF_TYPE_STRING ||
        std::string(gguf_get_val_str(ctx.get(), type)) != "custom_voice")
        throw std::runtime_error("Only CustomVoice GGUF is accepted; Base is not Sohee");
    auto dim = key("qwen3-tts.talker.embedding_length");
    if (dim < 0 || gguf_get_kv_type(ctx.get(), dim) != GGUF_TYPE_UINT32 || gguf_get_val_u32(ctx.get(), dim) != expected_hidden)
        throw std::runtime_error("Talker hidden size does not match selected model");
    auto names = key("qwen3-tts.codec.speaker_names");
    auto ids = key("qwen3-tts.codec.speaker_ids");
    if (names < 0 || ids < 0 || gguf_get_kv_type(ctx.get(), names) != GGUF_TYPE_ARRAY ||
        gguf_get_kv_type(ctx.get(), ids) != GGUF_TYPE_ARRAY ||
        gguf_get_arr_type(ctx.get(), names) != GGUF_TYPE_STRING ||
        gguf_get_arr_type(ctx.get(), ids) != GGUF_TYPE_INT32 ||
        gguf_get_arr_n(ctx.get(), names) != gguf_get_arr_n(ctx.get(), ids))
        throw std::runtime_error("Missing or invalid CustomVoice speaker map");
    auto data = static_cast<const int32_t*>(gguf_get_arr_data(ctx.get(), ids));
    bool sohee = false;
    for (size_t i = 0; i < gguf_get_arr_n(ctx.get(), names); ++i)
        if (std::string(gguf_get_arr_str(ctx.get(), names, i)) == "sohee" && data[i] == 2864) sohee = true;
    if (!sohee) throw std::runtime_error("Sohee (speaker 2864) is absent; no replacement voice will be used");
    for (int i = 0; i < 5; ++i) {
        auto name = "code_pred.blk." + std::to_string(i) + ".ffn_down.weight";
        auto tensor = gguf_find_tensor(ctx.get(), name.c_str());
        if (tensor < 0 || gguf_get_tensor_type(ctx.get(), tensor) != GGML_TYPE_F32)
            throw std::runtime_error("Missing F32 code-predictor down projection; recreate the stable model pack");
    }
}
void write_wav(const std::string& path, const std::vector<float>& audio, int rate) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    auto u16 = [&](uint16_t v) { char b[2]{char(v), char(v >> 8)}; out.write(b, 2); };
    auto u32 = [&](uint32_t v) { char b[4]{char(v), char(v >> 8), char(v >> 16), char(v >> 24)}; out.write(b, 4); };
    out.write("RIFF", 4); u32(36 + audio.size() * 2); out.write("WAVEfmt ", 8);
    u32(16); u16(1); u16(1); u32(rate); u32(rate * 2); u16(2); u16(16);
    out.write("data", 4); u32(audio.size() * 2);
    for (float sample : audio) {
        if (!std::isfinite(sample)) throw std::runtime_error("Non-finite PCM from decoder");
        u16(static_cast<uint16_t>(static_cast<int16_t>(std::clamp(sample, -1.0f, 1.0f) * 32767.0f)));
    }
    out.flush();
    if (!out.good()) throw std::runtime_error("Could not write complete WAV (storage full?)");
}
}

extern "C" JNIEXPORT jstring JNICALL
Java_ai_chloe_voicelab_synthesis_NativeBridge_initialize(JNIEnv* env, jobject, jstring directory, jstring talkerFile, jint hiddenSize, jstring logPath, jint threads, jint profile) {
    try {
        engine.reset();
        instruction_supported = false;
        chloe::configure(profile);
        if (hiddenSize != 1024 && hiddenSize != 2048) throw std::runtime_error("Unsupported model size");
        const std::string name = string(env, talkerFile);
        const std::string expected = hiddenSize == 1024
            ? "qwen-talker-0.6b-customvoice-f16-stable.gguf" : "qwen-talker-1.7b-customvoice-f16-stable.gguf";
        if (name != expected) throw std::runtime_error("Unexpected talker filename");
        // Preserve upstream diagnostics in app-private storage; never send logs over a network.
        static bool redirected = false;
        if (!redirected) {
            auto path = string(env, logPath);
            if (!freopen(path.c_str(), "a", stderr)) throw std::runtime_error("Cannot open native log");
            dup2(fileno(stderr), STDOUT_FILENO);
            setvbuf(stderr, nullptr, _IOLBF, 0);
            redirected = true;
        }
        auto dir = string(env, directory);
        validate_talker(dir + "/" + name, hiddenSize);
        if (threads < 1 || threads > 32) throw std::runtime_error("Invalid CPU thread count");
        if (!qwen3_tts_set_backend_preference(profile == 0 ? QWEN3_TTS_BACKEND_CPU : QWEN3_TTS_BACKEND_AUTO) || !qwen3_tts_set_cpu_threads(threads))
            throw std::runtime_error("CPU backend configuration failed");
        auto candidate = std::make_unique<qwen3_tts::Qwen3TTS>();
        if (!candidate->load_models(dir, name))
            throw std::runtime_error(candidate->get_error());
        auto caps = candidate->get_model_capabilities();
        auto speakers = candidate->get_available_speakers();
        if (caps.model_type != "custom_voice" || !caps.supports_named_speakers ||
            std::find(speakers.begin(), speakers.end(), "sohee") == speakers.end())
            throw std::runtime_error("Loaded runtime cannot resolve Sohee");
        if (hiddenSize == 2048 && !caps.supports_instruction)
            throw std::runtime_error("1.7B instruction capability missing");
        instruction_supported = hiddenSize == 2048 && caps.supports_instruction;
        engine = std::move(candidate);
        const std::string description = std::string(hiddenSize == 1024 ? "0.6B" : "1.7B") + " / Sohee / mode " + std::to_string(profile) + " / CPU fallback " + std::to_string(threads) + " threads";
        return env->NewStringUTF(description.c_str());
    } catch (const std::exception& e) { fail(env, e.what()); }
      catch (...) { fail(env, "Unknown native initialization failure"); }
    return nullptr;
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_ai_chloe_voicelab_synthesis_NativeBridge_synthesize(JNIEnv* env, jobject, jbyteArray text, jstring wavPath, jbyteArray instruction, jint threads) {
    try {
        if (!engine) throw std::runtime_error("Initialize Sohee first");
        std::string utf8(env->GetArrayLength(text), '\0');
        env->GetByteArrayRegion(text, 0, utf8.size(), reinterpret_cast<jbyte*>(utf8.data()));
        if (env->ExceptionCheck()) return nullptr;
        std::string instruct(env->GetArrayLength(instruction), '\0');
        env->GetByteArrayRegion(instruction, 0, instruct.size(), reinterpret_cast<jbyte*>(instruct.data()));
        if (env->ExceptionCheck()) return nullptr;
        if (!instruct.empty() && !instruction_supported) throw std::runtime_error("0.6B does not support instructions");
        qwen3_tts::tts_params params;
        params.instruction = instruct;
        params.language_id = 2064;
        params.speaker = "sohee";
        if (threads < 1 || threads > 32 || !qwen3_tts_set_cpu_threads(threads))
            throw std::runtime_error("Invalid CPU thread count");
        params.n_threads = threads;
        params.seed = 42;
        params.max_audio_tokens = 1024;
        engine->set_progress_callback([](int tokens, int maximum) {
            if (tokens >= maximum)
                throw std::runtime_error("Audio token limit reached; shorten the input or inspect the runtime log");
        });
        // Buffered full decode is the alpha1 quality baseline. No streaming seam tradeoff.
        auto start = Clock::now();
        chloe::reset_graph_stats();
        auto result = engine->synthesize(utf8, params);
        auto pcmReady = elapsed(start);
        if (!result.success) throw std::runtime_error(result.error_msg);
        if (result.audio.empty() || result.sample_rate != 24000)
            throw std::runtime_error("Invalid or empty decoder output");
        if (result.audio.size() >= 1024ULL * 1920)
            throw std::runtime_error("Audio token limit reached; shorten the input and retry");
        write_wav(string(env, wavPath), result.audio, result.sample_rate);
        double metrics[]{pcmReady, double(result.audio.size()) / result.sample_rate,
                         double(result.sample_rate), double(result.audio.size()), elapsed(start), double(result.t_generate_ms), double(result.t_decode_ms)};
        auto output = env->NewDoubleArray(7);
        if (output) env->SetDoubleArrayRegion(output, 0, 7, metrics);
        return output;
    } catch (const std::exception& e) { fail(env, e.what()); }
      catch (...) { fail(env, "Unknown native synthesis failure"); }
    return nullptr;
}

extern "C" JNIEXPORT void JNICALL
Java_ai_chloe_voicelab_synthesis_NativeBridge_release(JNIEnv*, jobject) { engine.reset(); }

extern "C" JNIEXPORT jstring JNICALL
Java_ai_chloe_voicelab_synthesis_NativeBridge_backendName(JNIEnv* env, jobject) {
    char* name = qwen3_tts_get_active_backend_name();
    if (!name) return env->NewStringUTF("unknown");
    jstring value = env->NewStringUTF(name);
    qwen3_tts_free_string(name);
    return value;
}

extern "C" JNIEXPORT jstring JNICALL
Java_ai_chloe_voicelab_synthesis_NativeBridge_backendInfo(JNIEnv* env, jobject) {
    return env->NewStringUTF(chloe::diagnostics().c_str());
}
