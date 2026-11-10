package ai.chloe.voicelab.conversation
import android.app.Service
import android.content.*
import android.os.*
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
internal class LlmNative { init{System.loadLibrary("chloe_llm")};external fun generate(path:ByteArray,messages:ByteArray,schema:ByteArray):ByteArray }
class LlmWorker:Service(){
 private val executor=Executors.newSingleThreadExecutor();private var native:LlmNative?=null
 private val messenger=Messenger(Handler(Looper.getMainLooper()){msg->
  if(msg.what==2){Process.killProcess(Process.myPid());return@Handler true}
  val reply=msg.replyTo;val serial=msg.arg1;val input=msg.data.getString("messages").orEmpty();val size=msg.data.getString("model").orEmpty()
  executor.execute {
   val result=runCatching {
    require(size in listOf("4b","2b") && input.length<=14000)
    val file=File(filesDir,"conversation-models/$size.gguf");check(file.isFile){"선택한 GGUF를 가져오세요"}
    val engine=native?:LlmNative().also{native=it}
    JSONObject(engine.generate(file.path.toByteArray(),input.toByteArray(),assets.open("conversation-schema.json").use{it.readBytes()}).toString(Charsets.UTF_8)).put("llm_pss_kib",Debug.MemoryInfo().also{Debug.getMemoryInfo(it)}.totalPss)
   }.getOrElse{JSONObject().put("error",it.message?:it.javaClass.simpleName)}
   runCatching{reply.send(Message.obtain(null,3).apply{arg1=serial;data=Bundle().apply{putString("result",result.toString())}})}
  };true
 });override fun onBind(intent:Intent)=messenger.binder
}
class AndroidLocalLlmEngine(private val context:Context,private val event:(JSONObject)->Unit):LocalLlmEngine,AutoCloseable {
 private var remote:Messenger?=null;private var bound=false;private var serial=0;private var pending:Message?=null;private var stopping=false
 private val replies=Messenger(Handler(Looper.getMainLooper()){m->if(m.arg1==serial)event(JSONObject(m.data.getString("result")!!));true})
 private val connection=object:ServiceConnection{
  override fun onServiceConnected(n:ComponentName,b:IBinder){remote=Messenger(b);stopping=false;pending?.let{send(it)};pending=null}
  override fun onServiceDisconnected(n:ComponentName){remote=null;if(!stopping)event(JSONObject().put("error","LLM 프로세스 종료/OOM 가능 · 재시도하세요"));stopping=false}
  override fun onBindingDied(n:ComponentName){if(bound)context.unbindService(this);bound=false;onServiceDisconnected(n)}
 }
 private fun send(m:Message){runCatching{remote!!.send(m)}.onFailure{event(JSONObject().put("error",it.message))}}
 override fun request(messages:String,model:String){val m=Message.obtain(null,1).apply{arg1=++serial;replyTo=replies;data=Bundle().apply{putString("messages",messages);putString("model",model)}};if(remote!=null)send(m) else{pending=m;if(!bound){bound=context.bindService(Intent(context,LlmWorker::class.java),connection,Context.BIND_AUTO_CREATE);check(bound)}}}
 override fun stop(){stopping=true;++serial;pending=null;runCatching{remote?.send(Message.obtain(null,2))};remote=null}
 override fun close(){stop();if(bound)context.unbindService(connection);bound=false}
}
