package ai.chloe.voicelab.conversation

import org.json.JSONObject

internal data class LlmRequest(val id:Int,val messages:String,val model:String)
internal interface LlmChannel {
    fun bind(connected:()->Unit, disconnected:()->Unit):Boolean
    fun send(request:LlmRequest)
    fun close()
}

/** Main-thread client. Each released binding is replaced, never reused. */
internal class LlmRequestClient(
    private val factory:((Int,JSONObject)->Unit)->LlmChannel,
    private val schedule:(Long,()->Unit)->(()->Unit),
    private val event:(JSONObject)->Unit
) {
    private var channel:LlmChannel?=null
    private var connected=false
    private var serial=0
    private var pending:LlmRequest?=null
    private var cancelTimeout:(()->Unit)?=null
    private var stage="idle"

    fun request(messages:String,model:String) {
        check(pending==null){"이미 요청을 처리하고 있습니다"}
        val request=LlmRequest(++serial,messages,model)
        pending=request;stage="binding"
        arm(request.id,15_000)
        if(channel==null){
            val c=factory(::receive);channel=c
            try {
                check(c.bind(
                    {if(channel===c){connected=true;pending?.let(::send)}},
                    {if(channel===c)fail("worker_disconnected","LLM 프로세스 연결 종료")}
                )){"LLM 서비스 연결 실패"}
            } catch(e:Exception){fail("bind_failed",e.message.orEmpty())}
        } else if(connected) send(request)
    }
    private fun send(request:LlmRequest) {
        stage="sent";arm(request.id,15_000)
        try{channel!!.send(request)}catch(e:Exception){fail("send_failed",e.message.orEmpty())}
    }
    private fun arm(id:Int,delay:Long){
        cancelTimeout?.invoke()
        cancelTimeout=schedule(delay){if(pending?.id==id)fail("request_timeout","LLM 시간 초과 · 단계: $stage")}
    }
    private fun receive(id:Int,result:JSONObject){
        if(pending?.id!=id)return
        if(result.has("progress")){
            stage=result.getString("progress")
            arm(id,if(stage=="inference")180_000 else 15_000)
            event(result);return
        }
        cancelTimeout?.invoke();cancelTimeout=null;pending=null;stage="idle"
        event(result)
    }
    private fun fail(code:String,message:String){
        val wasPending=pending!=null
        val lastStage=stage
        stop()
        if(wasPending)event(JSONObject().put("error",message).put("failure_code",code).put("request_stage",lastStage))
    }
    fun stop(){
        pending=null;cancelTimeout?.invoke();cancelTimeout=null;connected=false;stage="idle"
        val previous=channel;channel=null
        previous?.close()
    }
}
