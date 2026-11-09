#pragma once
#include "ggml.h"
#include "ggml-backend.h"
#include <string>

namespace chloe {
// 0 CPU, 1 GPU-preferred with CPU operator fallback, 2 GPU transformer + CPU decoder.
void configure(int mode);
bool gpu_required();
bool cpu_decoder();
void note_backend(const char* component, ggml_backend_t backend);
void reset_graph_stats();
void prepare_graph(ggml_backend_sched_t scheduler, ggml_cgraph* graph, const char* component);
std::string diagnostics();
}
