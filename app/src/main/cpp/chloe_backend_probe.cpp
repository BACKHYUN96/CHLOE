#include "chloe_backend_policy.h"
#include "qwen3_tts.h"
#include "gguf_loader.h"
#include "ggml-cpu.h"
#include <cmath>
#include <cstdio>
#include <stdexcept>
int main(int argc,char** argv) {
    try {
        chloe::configure(argc>2 ? std::stoi(argv[1]) : 0);
        qwen3_tts::set_cpu_thread_count(4);
        qwen3_tts::set_backend_preference(chloe::gpu_required() ? qwen3_tts::backend_preference::auto_select : qwen3_tts::backend_preference::cpu);
        if(argc>2) {
            qwen3_tts::Qwen3TTS engine;
            if(!engine.load_models(argv[2],"qwen-talker-1.7b-customvoice-f16-stable.gguf"))throw std::runtime_error(engine.get_error());
            qwen3_tts::tts_params params;params.speaker="sohee";params.language_id=2064;params.seed=42;params.n_threads=4;params.max_audio_tokens=256;
            chloe::reset_graph_stats();
            auto result=engine.synthesize("안녕하세요? 저는 클로이예요.",params);
            if(!result.success)throw std::runtime_error(result.error_msg);
            double energy=0;for(float x:result.audio){if(!std::isfinite(x))throw std::runtime_error("nonfinite audio");energy+=x*x;}
            if(result.audio.empty()||energy==0||result.sample_rate!=24000)throw std::runtime_error("invalid audio");
            fprintf(stdout,"samples=%zu code_ms=%lld decode_ms=%lld\n",result.audio.size(),(long long)result.t_generate_ms,(long long)result.t_decode_ms);
        } else {
            auto backend=ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_CPU,nullptr);
            if(!backend)throw std::runtime_error("CPU unavailable");
            auto ctx=ggml_init({2*1024*1024,nullptr,true});
            auto a=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,4),b=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,4);
            auto result=ggml_add(ctx,a,b);auto graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,result);
            auto buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);
            float x[]={1,1,1,1},y[]={2,2,2,2},z[4];ggml_backend_tensor_set(a,x,0,sizeof(x));ggml_backend_tensor_set(b,y,0,sizeof(y));
            auto sched=ggml_backend_sched_new(&backend,nullptr,1,128,false,true);
            if(!ggml_backend_sched_alloc_graph(sched,graph))throw std::runtime_error("allocation failed");
            chloe::note_backend("transformer",backend);chloe::prepare_graph(sched,graph,"talker");
            if(ggml_backend_sched_graph_compute(sched,graph)!=GGML_STATUS_SUCCESS)throw std::runtime_error("graph failed");
            ggml_backend_tensor_get(result,z,0,sizeof(z));for(float v:z)if(v!=3)throw std::runtime_error("CPU reference differs");
            fprintf(stdout,"%s\n",chloe::diagnostics().c_str());
            chloe::reset_graph_stats();
            ggml_backend_sched_free(sched);ggml_backend_buffer_free(buffer);ggml_free(ctx);ggml_backend_free(backend);
        }
        fprintf(stdout,"%s\n",chloe::diagnostics().c_str());return 0;
    } catch(const std::exception& e) {fprintf(stderr,"probe error: %s\n",e.what());return 2;}
}
