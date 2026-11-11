package ai.chloe.voicelab.conversation
import android.app.Application
import android.app.ActivityManager
import android.os.SystemClock
import android.view.WindowManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.chloe.voicelab.synthesis.LocalVoiceEngine
import ai.chloe.voicelab.audio.WavPlayer
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

class ConversationVm(app:Application):AndroidViewModel(app){
 var input by mutableStateOf("");var text by mutableStateOf("");var status by mutableStateOf("로컬 GGUF 가져오기 필요");var details by mutableStateOf("");var busy by mutableStateOf(false);var model by mutableStateOf("4b");var polite by mutableStateOf(true);var saveLogs by mutableStateOf(false);var unloadBeforeTts by mutableStateOf(true)
 var compactPrompt by mutableStateOf(true);var prefillThreads by mutableStateOf(4);private var requestedCompact=true;private var requestedThreads=4
 var showDebug by mutableStateOf(false);var debugOutput by mutableStateOf("");private var observedPeak=0;private var requestedModel="";private var requestedRelease=true;private var requestedPolite=true;private var runId="";private var requestedHistory=0
 var workerMemory by mutableStateOf("LLM 자체 PSS 미측정");var memory by mutableStateOf("UI 측 PSS 표본 미측정");private var deadline=0L;private var turn=0
 init{viewModelScope.launch{while(isActive){if(busy){val am=app.getSystemService(ActivityManager::class.java);val pids=am.runningAppProcesses.orEmpty().filter{it.uid==android.os.Process.myUid()}.map{it.pid}.toIntArray();val sum=runCatching{am.getProcessMemoryInfo(pids).sumOf{it.totalPss}}.getOrDefault(0);observedPeak=maxOf(observedPeak,sum);memory="UI 측 PSS 표본 ${sum/1024} MiB · 표본 최대 ${observedPeak/1024} MiB (누락 가능 · 전체/진짜 최대 아님)"};delay(1000)}}}
 private val metricRows=org.json.JSONArray()
 fun export(uri:Uri){val report=JSONObject().put("schema_version",2).put("app_version","0.1.0-alpha12").put("model",model).put("release_before_tts",unloadBeforeTts).put("memory_observation",memory).put("turns",metricRows).put("device",android.os.Build.MODEL).put("physical_first_sound_ms",JSONObject.NULL);viewModelScope.launch{runCatching{withContext(Dispatchers.IO){getApplication<Application>().contentResolver.openOutputStream(uri)!!.use{it.write(report.toString(2).toByteArray())}}}.onFailure{status="측정 내보내기 실패: ${it.message}"}}}
 private val manager=ConversationManager();private var sent="";private var current:DirectedReply?=null;private var output:File?=null;private var styled=true
 private val player=WavPlayer(app,viewModelScope)
 private val llm=AndroidLocalLlmEngine(app){r->if(r.has("progress")){status=when(r.getString("progress")){"accepted"->"LLM 요청 접수 완료";else->"LLM 연산 중…"};return@AndroidLocalLlmEngine};busy=false;if(r.has("error")){deadline=0;current=null;text="";debugOutput="";status=r.optString("error");if(metricRows.length()<120)metricRows.put(JSONObject().put("run_id",runId).put("model",requestedModel).put("release_before_tts",requestedRelease).put("requested_prefill_threads",requestedThreads).put("prompt_version",if(requestedCompact)"compact-v3" else "register-v2-empty-instruction").put("failure_code",r.optString("failure_code","worker_error")).put("request_stage",r.optString("request_stage","unknown")).put("success",false))}else{
  val raw=if(r.optBoolean("truncated"))"" else r.getString("raw");val reply=manager.accept(sent,raw)
  val metric=JSONObject(r.toString()).apply{remove("raw");remove("debug_generated");put("run_id",runId);put("model",requestedModel);put("release_before_tts",requestedRelease);put("polite",requestedPolite);put("history_turns",requestedHistory);put("app_pss_sample_peak_kib",if(observedPeak>0)observedPeak else JSONObject.NULL);put("measurement_scope","ui_visible_processes_partial_1s_samples");put("app_total_peak_pss_kib",JSONObject.NULL);put("prompt_version",if(requestedCompact)"compact-v3" else "register-v2-empty-instruction");put("requested_prefill_threads",requestedThreads);put("evaluation",ConversationEvaluator().structural(reply,requestedPolite));put("success",!reply.fallback)}
  workerMemory=if(r.has("llm_pss_kib"))"LLM 자체 PSS ${r.getLong("llm_pss_kib")/1024} MiB (완료 시점 · 최대 아님)" else "LLM 자체 PSS 미측정"
  if(metricRows.length()<120)metricRows.put(metric);current=reply.takeIf{it.failureCode in setOf("none","invalid_direction","plain_text")};text=reply.spokenText;debugOutput=r.optString("debug_generated").take(8192);details=metric.toString(2)+"\n실제 TTS 지시: "+TtsInstructionMapper().map(reply);status=if(reply.fallback)"대체 경로: ${reply.failureCode} · native: ${r.optString("native_parse_status")}" else "응답 완료 · 음성은 별도 재생"
  if(deadline>0){if(current!=null)speak(true) else deadline=0}
  if(saveLogs)runCatching{val f=File(app.filesDir,"conversation-log.jsonl");if(f.length()>1024*1024)f.writeText("");f.appendText(JSONObject().put("input",sent).put("reply",text).put("metrics",r).toString()+"\n")}.onFailure{status="로그 저장 실패: ${it.message}"}
 }}
 private val voice=LocalVoiceEngine(app){r->when(r.optString("type")){"ready"->current?.let{voiceGenerate(it)};"generated"->{busy=true;status="TTS 생성 완료";player.play(File(r.getString("path")),onFirstFrame={},onFinished={e->viewModelScope.launch{busy=false;status=e?:"재생 완료";if(e!=null)deadline=0;nextStress()}})};"error","worker_died"->{deadline=0;busy=false;status=r.optString("message","TTS 프로세스 종료")}}}
 private fun nextStress(){if(deadline>SystemClock.elapsedRealtime()){val rows=JSONObject(getApplication<Application>().assets.open("conversation-cases.json").bufferedReader().use{it.readText()}).getJSONArray("cases");input=rows.getJSONObject(turn++%rows.length()).getString("input");submit()}else{deadline=0}}
 fun stress(minutes:Int){if(busy)return;deadline=SystemClock.elapsedRealtime()+minutes*60000L;turn=0;nextStress()}
 private fun voiceGenerate(r:DirectedReply){val f=File(getApplication<Application>().filesDir,"audio/conversation.wav");f.parentFile!!.mkdirs();output=f;voice.synthesize(r.spokenText,f.path,if(styled)TtsInstructionMapper().map(r) else "",4)}
 fun submit(){if(busy)return;runCatching{sent=input.trim();requestedCompact=compactPrompt;requestedThreads=prefillThreads;requestedHistory=manager.context.turnCount;workerMemory="이번 요청 LLM 자체 PSS 대기";requestedModel=model;requestedRelease=unloadBeforeTts;requestedPolite=polite;runId=java.util.UUID.randomUUID().toString();observedPeak=0;memory="이번 요청 PSS 표본 대기";current=null;text="";debugOutput="";val prompt=manager.prompt(sent,polite,requestedCompact);if(unloadBeforeTts)voice.stop();busy=true;status="LLM 생성 중…";llm.request(prompt,model,requestedThreads)}.onFailure{busy=false;status=it.message.orEmpty()}}
 fun canSpeak()=current!=null
 fun speak(style:Boolean){if(busy||current==null)return;styled=style;busy=true;status="TTS 초기화 중…";if(unloadBeforeTts)llm.stop();runCatching{voice.initialize("1.7b",4)}.onFailure{busy=false;status=it.message.orEmpty()}}
 fun stop(){deadline=0;llm.stop();voice.stop();player.stop();busy=false;status="중지"}
 fun reset(){stop();manager.context.clear();text="";current=null;debugOutput="";details=""}
 fun import(uri:Uri){if(busy)return;val key=model;busy=true;viewModelScope.launch{try{withContext(Dispatchers.IO){val root=File(getApplication<Application>().filesDir,"conversation-models").apply{mkdirs()};val target=File(root,"$key.gguf");require(!target.exists()){ "기존 모델을 덮어쓰지 않습니다" };val part=File(root,"$key.partial");try{val hash=MessageDigest.getInstance("SHA-256");var total=0L;getApplication<Application>().contentResolver.openInputStream(uri)!!.use{source->part.outputStream().use{out->val h=ByteArray(4);check(source.read(h)==4&&String(h)=="GGUF"){"GGUF 파일 필요"};out.write(h);hash.update(h);total=4;val b=ByteArray(1024*1024);while(true){val n=source.read(b);if(n<0)break;total+=n;require(total<6_000_000_000);hash.update(b,0,n);out.write(b,0,n)}}};val spec=JSONObject(getApplication<Application>().assets.open("conversation-models.json").bufferedReader().use{it.readText()}).getJSONObject(key);val sha=hash.digest().joinToString(""){"%02x".format(it)};require(total==spec.getLong("bytes")&&sha==spec.getString("sha256")){"모델 크기/SHA 불일치 · 지정 Q4_K_M 파일을 확인하세요"};check(part.renameTo(target));File(root,"$key.sha256").writeText(sha)}finally{part.delete()}};status="GGUF 가져오기 완료 · 런타임 검증은 첫 응답 시 수행"}catch(e:Exception){status=e.message.orEmpty()}finally{busy=false}}}
 fun logging(value:Boolean){saveLogs=value;if(!value)File(getApplication<Application>().filesDir,"conversation-log.jsonl").delete()}
 override fun onCleared(){llm.close();voice.close();player.stop()}
}
class ConversationActivity:ComponentActivity(){
 private val vm:ConversationVm by viewModels()
 private val exporter=registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")){it?.let(vm::export)}
 private val picker=registerForActivityResult(ActivityResultContracts.OpenDocument()){it?.let(vm::import)}
 override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);setContent{DisposableEffect(vm.busy){if(vm.busy)window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);onDispose{window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)}};MaterialTheme{Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
 Text("CHLOE Conversation Lab",style=MaterialTheme.typography.headlineSmall);Text(vm.status)
 Row{listOf("4b","2b").forEach{m->FilterChip(selected=vm.model==m,onClick={vm.reset();vm.model=m},enabled=!vm.busy,label={Text("Qwen3.5 $m")})}}
 Button(onClick={picker.launch(arrayOf("*/*"))},enabled=!vm.busy){Text("로컬 Q4 GGUF 가져오기")}
 Row{Switch(vm.polite,{vm.reset();vm.polite=it},enabled=!vm.busy);Text("존댓말 (해제: 반말)")}
 Row{Switch(vm.unloadBeforeTts,{vm.unloadBeforeTts=it},enabled=!vm.busy);Text("TTS 전에 LLM 해제 · 기본 절약 모드")}
 Row{Switch(vm.compactPrompt,{vm.reset();vm.compactPrompt=it},enabled=!vm.busy);Text("간결한 프롬프트 · 해제: alpha11 기준")}
 Text("입력 처리 CPU 스레드 · 답변 생성은 4 고정")
 Row{listOf(4,6,8).forEach{n->FilterChip(selected=vm.prefillThreads==n,onClick={vm.prefillThreads=n},enabled=!vm.busy,label={Text("$n")})}}
 Row{Switch(vm.saveLogs,vm::logging);Text("대화 로그 로컬 저장 · 끄면 삭제")}
 OutlinedTextField(vm.input,{vm.input=it.take(400)},label={Text("한국어 대화")},enabled=!vm.busy,modifier=Modifier.fillMaxWidth())
 Row{Button(onClick=vm::submit,enabled=!vm.busy){Text("답변 생성")};TextButton(onClick=vm::stop){Text("중지")};TextButton(onClick=vm::reset,enabled=!vm.busy){Text("대화 초기화")}}
 Text(vm.text);Text(vm.workerMemory);Text(vm.memory);Text(vm.details);Row{Switch(vm.showDebug,{vm.showDebug=it});Text("진단용 원문 보기 · 로컬 화면만")};if(vm.showDebug)Text(vm.debugOutput);TextButton(onClick={exporter.launch("chloe-conversation-metrics.json")},enabled=!vm.busy){Text("내용 없는 측정 JSON 내보내기")}
 Row{OutlinedButton(onClick={vm.stress(10)},enabled=!vm.busy){Text("10분 반복")};OutlinedButton(onClick={vm.stress(30)},enabled=!vm.busy){Text("30분 반복")}}
 Row{Button(onClick={vm.speak(true)},enabled=!vm.busy&&vm.canSpeak()){Text("스타일 음성")};OutlinedButton(onClick={vm.speak(false)},enabled=!vm.busy&&vm.canSpeak()){Text("기본 음성 비교")}}
 Text("완전 오프라인 · 검색/예약/전화 기능 없음. 스타일 지시는 운율의 정밀 제어가 아닙니다. 기기 성능·정확성은 실측/청취 필요.")
 TextButton(onClick={finish()},enabled=!vm.busy){Text("기존 Voice Lab으로")}
 }}}}
 override fun onStop(){if(!isChangingConfigurations)vm.stop();super.onStop()}
}
