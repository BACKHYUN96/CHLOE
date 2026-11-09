// Fixed CPU/F16 comparison wrapper for the runtime pinned by OpenBMB's Android app.
#include "voxcpm2_runtime.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>

int main(int argc,char** argv){
    if(argc!=6){fprintf(stderr,"usage: chloe-vox-compare BaseLM.gguf Acoustic.gguf text seed output.wav\n");return 2;}
    try {
        using Clock=std::chrono::steady_clock;
        auto ms=[](Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();};
        VoxCPM2Runtime runtime;auto start=Clock::now();
        if(!runtime.init(argv[1],argv[2],0,false))throw std::runtime_error(runtime.last_error());
        runtime.set_n_threads(4);double init_ms=ms(start);
        VoxCPM2GenerateParams p;p.seed=std::stoul(argv[4]);p.cfg_value=2.f;p.inference_timesteps=10;p.max_steps=200;p.temperature=1.f;
        start=Clock::now();auto audio=runtime.generate(argv[3],p);double generate_ms=ms(start);
        if(audio.empty())throw std::runtime_error(runtime.last_error());
        double energy=0;for(float x:audio){if(!std::isfinite(x))throw std::runtime_error("nonfinite PCM");energy+=x*x;}if(energy==0)throw std::runtime_error("silent PCM");
        std::ofstream out(argv[5],std::ios::binary);auto u16=[&](uint16_t v){char b[]{char(v),char(v>>8)};out.write(b,2);};auto u32=[&](uint32_t v){char b[]{char(v),char(v>>8),char(v>>16),char(v>>24)};out.write(b,4);};
        const int rate=runtime.sample_rate();if(rate!=48000)throw std::runtime_error("unexpected sample rate");
        out.write("RIFF",4);u32(36+audio.size()*2);out.write("WAVEfmt ",8);u32(16);u16(1);u16(1);u32(rate);u32(rate*2);u16(2);u16(16);out.write("data",4);u32(audio.size()*2);
        for(float x:audio)u16(static_cast<uint16_t>(static_cast<int16_t>(std::clamp(x,-1.f,1.f)*32767)));out.flush();if(!out.good())throw std::runtime_error("WAV write failed");
        printf("CHLOE_METRICS {\"model_init_ms\":%.3f,\"generation_ms\":%.3f,\"samples\":%zu,\"sample_rate\":%d,\"threads\":4}\n",init_ms,generate_ms,audio.size(),rate);
        return 0;
    }catch(const std::exception& e){fprintf(stderr,"CHLOE VoxCPM2 error: %s\n",e.what());return 1;}
}
