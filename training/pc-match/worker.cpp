// Same chat-session/tokenization/sampling/finish sequence as llm_jni.cpp.
// CPU/CUDA are separate PC conditions; no ARM/GPU numerical equivalence claim.
#include "llama.h"
#include "chat.h"
#include "sampling.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
using Clock=std::chrono::steady_clock;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static llama_model *model=nullptr;
static llama_context *ctx=nullptr;
static common_chat_templates_ptr templates;
static common_json generate(const std::string &path,const std::string &messages,const std::string &schema,int layers){
 auto start=Clock::now();double load=0;
 if(!model){llama_backend_init();auto p=llama_model_default_params();p.n_gpu_layers=layers;
  static ggml_backend_dev_t cpu_only[]={nullptr};if(layers==0)p.devices=cpu_only;
  model=llama_model_load_from_file(path.c_str(),p);if(!model)throw std::runtime_error("GGUF load failed");
  char arch[128]{},ft[64]{};llama_model_meta_val_str(model,"general.architecture",arch,sizeof(arch));llama_model_meta_val_str(model,"general.file_type",ft,sizeof(ft));
  if(std::string(arch)!="qwen35"||std::string(ft)!="15")throw std::runtime_error("Expected qwen35 Q4_K_M type 15");
  auto c=llama_context_default_params();c.n_ctx=2048;c.n_batch=256;c.n_threads=4;c.n_threads_batch=4;c.offload_kqv=layers!=0;c.op_offload=layers!=0;
  ctx=llama_init_from_model(model,c);if(!ctx)throw std::runtime_error("Context allocation failed");load=ms(start);}
 llama_memory_clear(llama_get_memory(ctx),true);
 auto templateStart=Clock::now();bool cached=bool(templates);if(!templates)templates=common_chat_templates_init(model,"");
 common_chat_templates_inputs in;in.messages=common_chat_msgs_parse_oaicompat(common_json::parse(messages));in.enable_thinking=false;in.chat_template_kwargs["enable_thinking"]="false";in.json_schema=schema;
 auto vocab=llama_model_get_vocab(model);common_chat_session session(templates.get(),vocab,in);double templateMs=ms(templateStart);auto tokenizeStart=Clock::now();std::vector<llama_token> tokens;
 for(const auto &part:session.prompt().parts){std::vector<llama_token> t(part.text.size()+32);int n=llama_tokenize(vocab,part.text.data(),part.text.size(),t.data(),t.size(),tokens.empty(),!part.is_input);if(n<0){t.resize(-n);n=llama_tokenize(vocab,part.text.data(),part.text.size(),t.data(),t.size(),tokens.empty(),!part.is_input);}if(n<0)throw std::runtime_error("Tokenization failed");tokens.insert(tokens.end(),t.begin(),t.begin()+n);}
 int n=tokens.size();if(n<=0||n+384>2048)throw std::runtime_error("Context budget exceeded");
 double tokenizeMs=ms(tokenizeStart);auto generation=Clock::now();for(int i=0;i<n;i+=256){auto b=llama_batch_get_one(tokens.data()+i,std::min(256,n-i));if(llama_decode(ctx,b))throw std::runtime_error("Prefill failed");}
 double prefillMs=ms(generation);auto samplerStart=Clock::now();common_params_sampling sampling;sampling.temp=0.0f;sampling.seed=42;session.apply_sampling(sampling);
 common_sampler_ptr sampler(common_sampler_init(model,sampling));if(!sampler)throw std::runtime_error("Sampler initialization failed");
 double samplerMs=ms(samplerStart);auto decodeStart=Clock::now();std::string output;common_chat_input generatedInput;double first=-1;int count=0;bool ended=false;
 for(int i=0;i<384;i++){auto token=common_sampler_sample(sampler.get(),ctx,-1);common_sampler_accept(sampler.get(),token,true);if(first<0)first=ms(generation);char piece[256];int size=llama_token_to_piece(vocab,token,piece,sizeof(piece),0,true);if(size<0)throw std::runtime_error("Token piece too long");generatedInput.append(std::string(piece,size),token);if(llama_vocab_is_eog(vocab,token)){ended=true;break;}output.append(piece,size);count++;auto b=llama_batch_get_one(&token,1);if(llama_decode(ctx,b))throw std::runtime_error("Decode failed");}
 double decodeMs=ms(decodeStart);std::string content,status="token_limit";
 if(ended){try{content=session.finish(generatedInput).content;status=content.empty()?"empty_content":"ok";}catch(const std::exception&){status="template_parse_failed";}}
 return common_json{{"runtime_revision","aa75ff3239f9cc675b081697deda9e1b112345c6"},{"platform","wsl2-x86_64"},{"requested_gpu_layers",layers},{"backend_requested",layers?"cuda":"cpu"},{"temperature",0},{"seed",42},{"context_tokens",2048},{"max_generation_tokens",384},{"prefill_threads",4},{"decode_threads",4},{"template_cached",cached},{"template_ms",templateMs},{"tokenize_ms",tokenizeMs},{"prefill_ms",prefillMs},{"sampler_ms",samplerMs},{"decode_ms",decodeMs},{"first_token_ms",first},{"load_ms",load},{"native_request_ms",ms(start)},{"tokens",count},{"prompt_tokens",n},{"prompt_token_ids",tokens},{"raw",content},{"native_parse_status",status},{"truncated",!ended},{"schema_grammar",!session.grammar().empty()},{"grammar_lazy",sampling.grammar_lazy},{"grammar_prefill_bytes",sampling.generation_prompt.size()},{"chat_format",common_chat_format_name(session.format())}};
}
int main(int argc,char **argv){
 if(argc!=4){std::cerr<<"Usage: chloe_pc MODEL SCHEMA GPU_LAYERS\n";return 2;}
 std::ifstream file(argv[2]);std::string schema((std::istreambuf_iterator<char>(file)),{});if(schema.empty())return 2;
 for(std::string line;std::getline(std::cin,line);){try{auto request=common_json::parse(line);auto result=generate(argv[1],request.at("messages").dump(),schema,std::stoi(argv[3]));std::cout<<common_json{{"id",request.at("id")},{"result",result}}.dump()<<std::endl;}catch(const std::exception &e){std::cout<<common_json{{"error",e.what()}}.dump()<<std::endl;}}
 templates.reset();if(ctx)llama_free(ctx);if(model)llama_model_free(model);llama_backend_free();return 0;
}
