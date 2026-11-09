// Experimental engine in :comparison only. Existing NativeBridge exports are unchanged.
#include <jni.h>
#include <gguf.h>
#include "qwen3_tts.h"
#include "qwen3_tts_c.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <memory>
#include <stdexcept>

namespace {
std::unique_ptr<qwen3_tts::Qwen3TTS> comparison;
bool design = false;
using Clock = std::chrono::steady_clock;
std::string str(JNIEnv* e,jstring s) { const char* p=e->GetStringUTFChars(s,nullptr); if(!p)throw std::runtime_error("JNI string failed"); std::string r(p);e->ReleaseStringUTFChars(s,p);return r; }
std::string bytes(JNIEnv* e,jbyteArray b) {std::string r(e->GetArrayLength(b),'\0');e->GetByteArrayRegion(b,0,r.size(),reinterpret_cast<jbyte*>(r.data()));return r;}
void fail(JNIEnv* e,const std::exception& x){e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),x.what());}
double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
void validate(const std::string& path,bool is_design){
    auto ctx=gguf_init_from_file(path.c_str(),{true,nullptr});if(!ctx)throw std::runtime_error("Invalid GGUF");
    std::unique_ptr<gguf_context,decltype(&gguf_free)> guard(ctx,gguf_free);
    auto k=gguf_find_key(ctx,"qwen3-tts.model_type");
    if(k<0||gguf_get_kv_type(ctx,k)!=GGUF_TYPE_STRING||std::string(gguf_get_val_str(ctx,k))!=(is_design?"voice_design":"custom_voice"))throw std::runtime_error("GGUF model type mismatch; no model substitution");
    k=gguf_find_key(ctx,"qwen3-tts.talker.embedding_length");
    if(k<0||gguf_get_kv_type(ctx,k)!=GGUF_TYPE_UINT32||gguf_get_val_u32(ctx,k)!=2048)throw std::runtime_error("Expected 1.7B hidden size");
    if(!is_design){
        auto names=gguf_find_key(ctx,"qwen3-tts.codec.speaker_names"), ids=gguf_find_key(ctx,"qwen3-tts.codec.speaker_ids");
        if(names<0||ids<0||gguf_get_kv_type(ctx,names)!=GGUF_TYPE_ARRAY||gguf_get_kv_type(ctx,ids)!=GGUF_TYPE_ARRAY||gguf_get_arr_type(ctx,names)!=GGUF_TYPE_STRING||gguf_get_arr_type(ctx,ids)!=GGUF_TYPE_INT32||gguf_get_arr_n(ctx,names)!=gguf_get_arr_n(ctx,ids))throw std::runtime_error("Invalid CustomVoice speaker map");
        auto values=static_cast<const int32_t*>(gguf_get_arr_data(ctx,ids));bool sohee=false;
        for(size_t i=0;i<gguf_get_arr_n(ctx,names);++i)if(std::string(gguf_get_arr_str(ctx,names,i))=="sohee"&&values[i]==2864)sohee=true;
        if(!sohee)throw std::runtime_error("Sohee speaker 2864 unavailable; no substitute voice");
    }
    for(int i=0;i<5;++i){auto n="code_pred.blk."+std::to_string(i)+".ffn_down.weight";auto t=gguf_find_tensor(ctx,n.c_str());if(t<0||gguf_get_tensor_type(ctx,t)!=GGML_TYPE_F32)throw std::runtime_error("Expected F32 CP-down stable pack");}
}
void wav(const std::string& path,const std::vector<float>& audio,int rate){
    std::ofstream f(path,std::ios::binary|std::ios::trunc);
    auto u16=[&](uint16_t v){char b[]{char(v),char(v>>8)};f.write(b,2);};auto u32=[&](uint32_t v){char b[]{char(v),char(v>>8),char(v>>16),char(v>>24)};f.write(b,4);};
    f.write("RIFF",4);u32(36+audio.size()*2);f.write("WAVEfmt ",8);u32(16);u16(1);u16(1);u32(rate);u32(rate*2);u16(2);u16(16);f.write("data",4);u32(audio.size()*2);
    double energy=0;for(float x:audio){if(!std::isfinite(x))throw std::runtime_error("Nonfinite PCM");energy+=x*x;u16(static_cast<uint16_t>(static_cast<int16_t>(std::clamp(x,-1.f,1.f)*32767)));}
    f.flush();if(!f.good()||energy==0)throw std::runtime_error("WAV write failed or silent PCM");
}
}
extern "C" JNIEXPORT jstring JNICALL Java_ai_chloe_voicelab_comparison_ComparisonNative_initialize(JNIEnv* e,jobject,jstring dir,jstring file,jboolean isDesign){
    try{comparison.reset();design=isDesign;auto name=str(e,file);validate(str(e,dir)+"/"+name,design);
        if(!qwen3_tts_set_backend_preference(QWEN3_TTS_BACKEND_CPU)||!qwen3_tts_set_cpu_threads(4))throw std::runtime_error("CPU setup failed");
        auto candidate=std::make_unique<qwen3_tts::Qwen3TTS>();if(!candidate->load_models(str(e,dir),name))throw std::runtime_error(candidate->get_error());
        auto caps=candidate->get_model_capabilities();if(!caps.supports_instruction||caps.model_type!=(design?"voice_design":"custom_voice"))throw std::runtime_error("Runtime capability mismatch");
        if(!design){auto names=candidate->get_available_speakers();if(std::find(names.begin(),names.end(),"sohee")==names.end())throw std::runtime_error("Sohee unavailable");}
        comparison=std::move(candidate);return e->NewStringUTF(design?"CPU / VoiceDesign (no named Sohee)":"CPU / CustomVoice / Sohee");
    }catch(const std::exception& x){fail(e,x);}catch(...){e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),"Unknown comparison initialization failure");}return nullptr;
}
extern "C" JNIEXPORT jdoubleArray JNICALL Java_ai_chloe_voicelab_comparison_ComparisonNative_generate(JNIEnv* e,jobject,jbyteArray text,jbyteArray instruction,jint seed,jstring path){
    try{if(!comparison)throw std::runtime_error("Initialize comparison engine first");qwen3_tts::tts_params p;p.language_id=2064;p.speaker=design?"":"sohee";p.instruction=bytes(e,instruction);p.seed=seed;p.n_threads=4;p.max_audio_tokens=1024;
        if(design&&p.instruction.empty())throw std::runtime_error("VoiceDesign needs a voice description");
        comparison->set_progress_callback([](int n,int maximum){if(n>=maximum)throw std::runtime_error("Token cap reached; result rejected");});
        auto start=Clock::now();auto r=comparison->synthesize(bytes(e,text),p);double pcm=ms(start);
        if(!r.success)throw std::runtime_error(r.error_msg);if(r.audio.empty()||r.sample_rate!=24000)throw std::runtime_error("Invalid comparison PCM");wav(str(e,path),r.audio,r.sample_rate);
        double m[]{pcm,double(r.audio.size())/r.sample_rate,double(r.sample_rate),double(r.audio.size()),ms(start),double(r.t_generate_ms),double(r.t_decode_ms)};
        auto a=e->NewDoubleArray(7);if(a)e->SetDoubleArrayRegion(a,0,7,m);return a;
    }catch(const std::exception& x){fail(e,x);}catch(...){e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),"Unknown comparison synthesis failure");}return nullptr;
}
