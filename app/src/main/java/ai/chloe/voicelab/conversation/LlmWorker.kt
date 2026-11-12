package ai.chloe.voicelab.conversation
import android.app.Service
import android.content.*
import android.os.*
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
internal class LlmNative { init{System.loadLibrary("chloe_llm")};external fun generate(path:ByteArray,messages:ByteArray,schema:ByteArray,prefillThreads:Int,contextTokens:Int):ByteArray }
class LlmWorker:Service(){
 private val executor=Executors.newSingleThreadExecutor();private var native:LlmNative?=null
 private val messenger=Messenger(Handler(Looper.getMainLooper()){msg->
  if(msg.what==2){Process.killProcess(Process.myPid());return@Handler true}
  val reply=msg.replyTo;val serial=msg.arg1;val input=msg.data.getString("messages").orEmpty();val size=msg.data.getString("model").orEmpty()
  val prefillThreads=msg.data.getInt("prefill_threads",4)
  fun progress(stage:String){runCatching{reply.send(Message.obtain(null,4).apply{arg1=serial;data=Bundle().apply{putString("result",JSONObject().put("progress",stage).toString())}})}}
  progress("accepted")
  executor.execute {
   progress("inference")
   val result=runCatching {
    require(size in ConversationModelPolicy.keys && input.length<=14000 && prefillThreads in listOf(4,6,8))
    val file=File(filesDir,"conversation-models/$size.gguf");check(file.isFile){"선택한 GGUF를 가져오세요"}
    val engine=native?:LlmNative().also{native=it}
    JSONObject(engine.generate(file.path.toByteArray(),input.toByteArray(),assets.open("conversation-schema.json").use{it.readBytes()},prefillThreads,ConversationModelPolicy.contextTokens(size)).toString(Charsets.UTF_8)).put("llm_pss_kib",Debug.MemoryInfo().also{Debug.getMemoryInfo(it)}.totalPss)
   }.getOrElse{JSONObject().put("error",it.message?:it.javaClass.simpleName)}
   runCatching{reply.send(Message.obtain(null,3).apply{arg1=serial;data=Bundle().apply{putString("result",result.toString())}})}
  };true
 });override fun onBind(intent:Intent)=messenger.binder
}
class AndroidLocalLlmEngine(private val context:Context,event:(JSONObject)->Unit):LocalLlmEngine,AutoCloseable {
 private val handler=Handler(Looper.getMainLooper())
 private val client=LlmRequestClient(
  factory={receive->AndroidLlmChannel(context,receive)},
  schedule={delay,action->val task=Runnable{action()};handler.postDelayed(task,delay);{handler.removeCallbacks(task)}},
  event=event
 )
 override fun request(messages:String,model:String,prefillThreads:Int)=client.request(messages,model,prefillThreads)
 override fun stop()=client.stop()
 override fun close()=client.stop()
}
private class AndroidLlmChannel(private val context:Context,receive:(Int,JSONObject)->Unit):LlmChannel {
 private var remote:Messenger?=null
 private var bound=false
 private var closed=false
 private val replies=Messenger(Handler(Looper.getMainLooper()){m->if(!closed)receive(m.arg1,JSONObject(m.data.getString("result")!!));true})
 private var connected:()->Unit={}
 private var disconnected:()->Unit={}
 private val connection=object:ServiceConnection{
  override fun onServiceConnected(n:ComponentName,b:IBinder){if(!closed){remote=Messenger(b);connected()}}
  override fun onServiceDisconnected(n:ComponentName){if(!closed){remote=null;disconnected()}}
  override fun onBindingDied(n:ComponentName){if(!closed)disconnected()}
  override fun onNullBinding(n:ComponentName){if(!closed)disconnected()}
 }
 override fun bind(connected:()->Unit,disconnected:()->Unit):Boolean {
  check(!closed);this.connected=connected;this.disconnected=disconnected
  bound=context.bindService(Intent(context,LlmWorker::class.java),connection,Context.BIND_AUTO_CREATE)
  return bound
 }
 override fun send(request:LlmRequest){check(!closed);val target=checkNotNull(remote){"LLM 서비스 미연결"};target.send(Message.obtain(null,1).apply{arg1=request.id;replyTo=replies;data=Bundle().apply{putString("messages",request.messages);putString("model",request.model);putInt("prefill_threads",request.prefillThreads)}})}
 override fun close(){
  if(closed)return
  closed=true
  runCatching{remote?.send(Message.obtain(null,2))};remote=null
  if(bound){bound=false;runCatching{context.unbindService(connection)}}
 }
}
