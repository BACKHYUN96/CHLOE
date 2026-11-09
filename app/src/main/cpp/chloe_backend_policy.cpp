#include "chloe_backend_policy.h"
#include "gguf_loader.h"
#include <array>
#include <cstdint>
#include <sstream>
#include <stdexcept>

namespace chloe {
namespace {
int mode = 0;
struct Stats { uint64_t graphs=0, cpu=0, gpu=0, other=0, unassigned=0, cpu_matmul=0, gpu_matmul=0; };
std::array<Stats,3> stats;
std::string transformer, decoder;
std::string quote(const std::string& value) {
    std::string out="\"";
    for (unsigned char c : value) {
        if (c=='"' || c=='\\') { out+='\\'; out+=c; }
        else if (c<32) out+=' ';
        else out+=c;
    }
    return out+'"';
}
int index(const char* name) { return std::string(name)=="decoder" ? 2 : std::string(name)=="code_predictor" ? 1 : 0; }
}
void configure(int requested) {
    if (requested<0 || requested>2) throw std::runtime_error("Unknown execution mode");
#ifndef QWEN3_TTS_VULKAN_ENABLED
    if (requested!=0) throw std::runtime_error("This APK was built without Vulkan");
#endif
    mode=requested; transformer.clear(); decoder.clear(); reset_graph_stats();
    if (mode!=0 && !ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_IGPU) && !ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_GPU))
        throw std::runtime_error("No usable GPU backend found; choose CPU mode");
}
bool gpu_required() { return mode!=0; }
bool cpu_decoder() { return mode==2; }
void note_backend(const char* component, ggml_backend_t backend) {
    auto device=backend ? ggml_backend_get_device(backend) : nullptr;
    const char* name=device ? ggml_backend_dev_name(device) : "unknown";
    if (std::string(component)=="decoder") decoder=name; else transformer=name;
}
void reset_graph_stats() { stats={}; }
void prepare_graph(ggml_backend_sched_t sched, ggml_cgraph* graph, const char* component) {
    // CPU fallback backends are separate from the shared GPU backend: update them too.
    for (int i=0;i<ggml_backend_sched_get_n_backends(sched);++i) {
        auto backend=ggml_backend_sched_get_backend(sched,i);
        auto device=ggml_backend_get_device(backend);
        if (device && ggml_backend_dev_type(device)==GGML_BACKEND_DEVICE_TYPE_CPU) {
            auto reg=ggml_backend_dev_backend_reg(device);
            auto setter=(ggml_backend_set_n_threads_t)ggml_backend_reg_get_proc_address(reg,"ggml_backend_set_n_threads");
            if (setter) setter(backend,qwen3_tts::get_cpu_thread_count());
        }
    }
    auto& s=stats[index(component)];++s.graphs;
    for (int i=0;i<ggml_graph_n_nodes(graph);++i) {
        auto node=ggml_graph_node(graph,i);
        if (node->op==GGML_OP_NONE || node->op==GGML_OP_VIEW || node->op==GGML_OP_RESHAPE || node->op==GGML_OP_PERMUTE || node->op==GGML_OP_TRANSPOSE) continue;
        auto backend=ggml_backend_sched_get_tensor_backend(sched,node);
        auto device=backend ? ggml_backend_get_device(backend) : nullptr;
        if (!device) { ++s.unassigned; continue; }
        auto type=ggml_backend_dev_type(device);
        bool matmul=node->op==GGML_OP_MUL_MAT || node->op==GGML_OP_MUL_MAT_ID;
        if (type==GGML_BACKEND_DEVICE_TYPE_CPU) { ++s.cpu; if(matmul)++s.cpu_matmul; }
        else if (type==GGML_BACKEND_DEVICE_TYPE_GPU || type==GGML_BACKEND_DEVICE_TYPE_IGPU) { ++s.gpu; if(matmul)++s.gpu_matmul; }
        else ++s.other;
    }
}
std::string diagnostics() {
    std::ostringstream out;
    out<<"{\"profile_id\":"<<mode<<",\"transformer_device\":"<<quote(transformer)<<",\"decoder_device\":"<<quote(decoder)
       <<",\"simultaneous_parallel\":false,\"stages\":{";
    const char* names[]={"talker","code_predictor","decoder"};
    for(int i=0;i<3;++i){const auto& s=stats[i];if(i)out<<',';
        out<<quote(names[i])<<":{\"graphs\":"<<s.graphs<<",\"cpu_nodes\":"<<s.cpu<<",\"gpu_nodes\":"<<s.gpu
           <<",\"other_nodes\":"<<s.other<<",\"unassigned_nodes\":"<<s.unassigned<<",\"cpu_matmul_nodes\":"<<s.cpu_matmul<<",\"gpu_matmul_nodes\":"<<s.gpu_matmul<<'}';}
    out<<"}}";return out.str();
}
}
