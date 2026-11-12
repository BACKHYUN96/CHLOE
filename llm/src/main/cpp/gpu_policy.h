#pragma once
#include "ggml-backend.h"
#include <cstdio>
#include <cstring>

inline bool chloe_vulkan_gpu(enum ggml_backend_dev_type type,const char* backend) {
 return (type==GGML_BACKEND_DEVICE_TYPE_GPU || type==GGML_BACKEND_DEVICE_TYPE_IGPU) && backend && std::strcmp(backend,"Vulkan")==0;
}
inline bool chloe_offload_report(const char* line,int& layers,int& total) {
 if(!line)return false;
 const char* p=std::strstr(line,"offloaded ");int n=0,m=0;
 if(!p || std::sscanf(p,"offloaded %d/%d layers to GPU",&n,&m)!=2 || n<0 || m<=0 || n>m)return false;
 layers=n;total=m;return true;
}
