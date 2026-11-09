package ai.chloe.voicelab.synthesis

import android.content.*
import android.os.*
import org.json.JSONObject

internal class LocalVoiceEngine(
    private val context: Context,
    private val onEvent: (JSONObject) -> Unit,
) : VoiceEngine {
    private var remote: Messenger? = null
    private var bound = false
    private var pending: Message? = null
    private var requestId = 0
    private var stopping = false
    private val replies = Messenger(Handler(Looper.getMainLooper()) { msg ->
        if (msg.arg1 == requestId) runCatching {
            onEvent(JSONObject(msg.data.getString("json") ?: "{}"))
        }.onFailure { failure(it) }
        true
    })
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            remote = Messenger(service)
            stopping = false
            onEvent(JSONObject().put("type", "connected"))
            pending?.let { send(it) }; pending = null
        }
        override fun onServiceDisconnected(name: ComponentName) {
            remote = null
            onEvent(JSONObject().put("type", if (stopping) "stopped" else "worker_died"))
            stopping = false
        }
        override fun onBindingDied(name: ComponentName) {
            remote = null
            if (bound) context.unbindService(this)
            bound = false
            onEvent(JSONObject().put("type", "worker_died"))
        }
        override fun onNullBinding(name: ComponentName) { onBindingDied(name) }
    }
    private fun failure(error: Throwable) {
        remote = null
        onEvent(JSONObject().put("type", "error").put("message", error.message ?: "서비스 연결 실패"))
    }
    private fun request(what: Int, data: Bundle = Bundle()) {
        check(!stopping) { "추론 프로세스 중지를 기다려 주세요." }
        val msg = Message.obtain(null, what).apply {
            arg1 = ++requestId; replyTo = replies; this.data = data
        }
        if (remote != null) send(msg) else {
            pending = msg
            if (!bound) {
                bound = context.bindService(Intent(context, VoiceWorkerService::class.java), connection, Context.BIND_AUTO_CREATE)
                check(bound) { "추론 서비스 연결 실패" }
            }
        }
    }
    private fun send(msg: Message) { try { remote!!.send(msg) } catch (e: RemoteException) { failure(e) } }
    override fun initialize(modelKey: String, threads: Int) = request(VoiceProtocol.INIT, Bundle().apply { putString("model", modelKey); putInt("threads", threads) })
    override fun synthesize(text: String, outputPath: String, instruction: String, threads: Int) = request(VoiceProtocol.GENERATE, Bundle().apply {
        putString("text", text); putString("output", outputPath); putString("instruction", instruction); putInt("threads", threads)
    })
    override fun stop() {
        ++requestId; pending = null
        stopping = remote != null
        runCatching { remote?.send(Message.obtain(null, VoiceProtocol.STOP)) }.onFailure { stopping = false; failure(it) }
        if (!stopping) onEvent(JSONObject().put("type", "stopped"))
    }
    override fun close() {
        stop()
        if (bound) context.unbindService(connection)
        bound = false; remote = null
    }
}
