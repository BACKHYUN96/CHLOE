#include <jni.h>
#include "llama.h"
#include "chat.h"
#include "sampling.h"
#include <chrono>
#include <stdexcept>
#include <vector>
#include <string>
static llama_model* model=nullptr;
static llama_context* ctx=nullptr;
static std::string loaded;
static common_chat_templates_ptr templates;
using Clock=std::chrono::steady_clock;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
static std::string bytes(JNIEnv* e,jbyteArray a){std::string s(e->GetArrayLength(a),'\0');e->GetByteArrayRegion(a,0,s.size(),(jbyte*)s.data());return s;}
extern "C" JNIEXPORT jbyteArray JNICALL Java_ai_chloe_voicelab_conversation_LlmNative_generate(JNIEnv* e,jobject,jbyteArray path,jbyteArray messages,jbyteArray schema){
 try {
 auto start=Clock::now();double load=0;auto name=bytes(e,path);
 if(name!=loaded){templates.reset();if(ctx)llama_free(ctx);ctx=nullptr;if(model)llama_model_free(model);model=nullptr;loaded.clear();llama_backend_init();auto p=llama_model_default_params();p.n_gpu_layers=0;model=llama_model_load_from_file(name.c_str(),p);if(!model)throw std::runtime_error("GGUF load failed");
 char arch[128]{};llama_model_meta_val_str(model,"general.architecture",arch,sizeof(arch));if(std::string(arch)!="qwen35")throw std::runtime_error("Expected Qwen3.5 dense text GGUF");
 char ft[64]{};llama_model_meta_val_str(model,"general.file_type",ft,sizeof(ft));if(std::string(ft)!="15")throw std::runtime_error("Require Q4_K_M file type 15");
 auto c=llama_context_default_params();c.n_ctx=2048;c.n_batch=256;c.n_threads=4;c.n_threads_batch=4;ctx=llama_init_from_model(model,c);if(!ctx)throw std::runtime_error("Context allocation failed");loaded=name;load=ms(start);}
 llama_memory_clear(llama_get_memory(ctx),true);
 auto templateStart=Clock::now();bool templateCached=bool(templates);
 if(!templates)templates=common_chat_templates_init(model,"");
 common_chat_templates_inputs in;in.messages=common_chat_msgs_parse_oaicompat(common_json::parse(bytes(e,messages)));in.enable_thinking=false;in.chat_template_kwargs["enable_thinking"]="false";in.json_schema=bytes(e,schema);
 auto vocab=llama_model_get_vocab(model);common_chat_session session(templates.get(),vocab,in);double templateMs=ms(templateStart);auto tokenizeStart=Clock::now();std::vector<llama_token> tokens;
 for(const auto& part:session.prompt().parts){std::vector<llama_token> t(part.text.size()+32);int n=llama_tokenize(vocab,part.text.data(),part.text.size(),t.data(),t.size(),tokens.empty(),!part.is_input);if(n<0){t.resize(-n);n=llama_tokenize(vocab,part.text.data(),part.text.size(),t.data(),t.size(),tokens.empty(),!part.is_input);}if(n<0)throw std::runtime_error("Tokenization failed");tokens.insert(tokens.end(),t.begin(),t.begin()+n);}
 int n=tokens.size();if(n<=0||n+384>2048)throw std::runtime_error("Context budget exceeded; reset conversation");
 double tokenizeMs=ms(tokenizeStart);auto generation=Clock::now();for(int i=0;i<n;i+=256){int count=std::min(256,n-i);auto batch=llama_batch_get_one(tokens.data()+i,count);if(llama_decode(ctx,batch))throw std::runtime_error("Prefill failed");}
 // Use upstream chat sampling: lazy triggers, preserved tokens and grammar prefill
 // must agree with the template parser. A bare grammar sampler loses these.
 double prefillMs=ms(generation);auto samplerStart=Clock::now();
 common_params_sampling sampling;sampling.temp=0.0f;sampling.seed=42;
 session.apply_sampling(sampling);
 common_sampler_ptr sampler(common_sampler_init(model,sampling));
 if(!sampler)throw std::runtime_error("Sampler initialization failed");
 double samplerMs=ms(samplerStart);auto decodeStart=Clock::now();
 std::string output;common_chat_input generatedInput;double first=-1;int generated=0;bool ended=false;
 for(int i=0;i<384;++i){
  auto token=common_sampler_sample(sampler.get(),ctx,-1);
  common_sampler_accept(sampler.get(),token,true);
  if(first<0)first=ms(generation);
  char piece[256];int size=llama_token_to_piece(vocab,token,piece,sizeof(piece),0,true);
  if(size<0)throw std::runtime_error("Token piece too long");
  generatedInput.append(std::string(piece,size),token);
  if(llama_vocab_is_eog(vocab,token)){ended=true;break;}
  output.append(piece,size);++generated;
  auto b=llama_batch_get_one(&token,1);if(llama_decode(ctx,b))throw std::runtime_error("Decode failed");
 }
 double decodeMs=ms(decodeStart);
 std::string content,parseStatus="token_limit";
 if(ended){try{content=session.finish(generatedInput).content;parseStatus=content.empty()?"empty_content":"ok";}catch(const std::exception&){parseStatus="template_parse_failed";}}
 size_t debugEnd=std::min<size_t>(output.size(),8192);
 if(debugEnd<output.size())while(debugEnd>0&&(static_cast<unsigned char>(output[debugEnd])&0xc0)==0x80)--debugEnd;
 double total=ms(generation);auto s=common_json{{"template_cached",templateCached},{"template_ms",templateMs},{"tokenize_ms",tokenizeMs},{"prefill_ms",prefillMs},{"sampler_ms",samplerMs},{"decode_ms",decodeMs},{"decode_tokens_per_second",decodeMs>0?generated*1000.0/decodeMs:0},{"native_request_ms",ms(start)},{"raw",content},{"debug_generated",output.substr(0,debugEnd)},{"native_parse_status",parseStatus},{"generated_bytes",output.size()},{"prompt_tokens",n},{"chat_format",common_chat_format_name(session.format())},{"grammar_lazy",sampling.grammar_lazy},{"grammar_prefill_bytes",sampling.generation_prompt.size()},{"runtime_revision","aa75ff3239f9cc675b081697deda9e1b112345c6"},{"load_ms",load},{"first_token_ms",first},{"generation_ms",total},{"tokens",generated},{"tokens_per_second",generated*1000.0/total},{"truncated",!ended},{"schema_grammar",!session.grammar().empty()}}.dump();auto a=e->NewByteArray(s.size());e->SetByteArrayRegion(a,0,s.size(),(jbyte*)s.data());return a;
 }catch(const std::exception& x){e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),x.what());return nullptr;}
}
