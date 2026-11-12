#include "gpu_policy.h"
#include <cassert>
int main(){
 // Mobile integrated GPUs must be accepted as well as dedicated GPUs.
 assert(chloe_vulkan_gpu(GGML_BACKEND_DEVICE_TYPE_IGPU,"Vulkan"));
 assert(chloe_vulkan_gpu(GGML_BACKEND_DEVICE_TYPE_GPU,"Vulkan"));
 assert(!chloe_vulkan_gpu(GGML_BACKEND_DEVICE_TYPE_CPU,"Vulkan"));
 assert(!chloe_vulkan_gpu(GGML_BACKEND_DEVICE_TYPE_GPU,"OpenCL"));
 assert(!chloe_vulkan_gpu(GGML_BACKEND_DEVICE_TYPE_GPU,nullptr));
 int n=-1,m=-1;
 assert(chloe_offload_report("llama_model: offloaded 16/33 layers to GPU\n",n,m) && n==16 && m==33);
 assert(chloe_offload_report("offloaded 0/33 layers to GPU",n,m) && n==0);
 assert(chloe_offload_report("offloaded 33/33 layers to GPU",n,m) && n==33);
 assert(!chloe_offload_report("offloading 16 repeating layers to GPU",n,m));
 assert(!chloe_offload_report("offloaded 34/33 layers to GPU",n,m));
 assert(!chloe_offload_report(nullptr,n,m));
}
