package ai.chloe.voicelab.comparison

import android.content.*
import android.os.*
import org.json.JSONObject

internal class ComparisonClient(private val context: Context, private val event: (JSONObject) -> Unit) : AutoCloseable {
    private var bound = false
    private var remote: Messenger? = null
    private var pending: Message? = null
    private var serial = 0
    private var stopping = false
    private val replies = Messenger(Handler(Looper.getMainLooper()) { msg ->
        if (msg.arg1 == serial) event(JSONObject(msg.data.getString("json") ?: "{}")); true
    })
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) {
            remote = Messenger(binder); stopping = false
            pending?.let { send(it) }; pending = null
        }
        override fun onServiceDisconnected(name: ComponentName) {
            remote = null; val was = stopping; stopping = false
            event(JSONObject().put("type", if (was) "stopped" else "worker_died"))
        }
        override fun onBindingDied(name: ComponentName) {
            if (bound) context.unbindService(this); bound = false; onServiceDisconnected(name)
        }
    }
    private fun send(message: Message) {
        runCatching { remote!!.send(message) }.onFailure {
            remote = null
            event(JSONObject().put("type", "error").put("message", it.message ?: "추론 서비스 연결 실패"))
        }
    }
    fun generate(model: String, text: String, instruction: String, seed: Int, id: String) {
        check(!stopping) { "추론 프로세스 종료를 기다려 주세요." }
        val msg = Message.obtain(null, 2).apply { arg1 = ++serial; replyTo = replies
            data = Bundle().apply { putString("model", model); putString("text", text); putString("instruction", instruction); putInt("seed", seed); putString("id", id) }
        }
        if (remote != null) send(msg) else { pending = msg
            if (!bound) { bound = context.bindService(Intent(context, ComparisonWorkerService::class.java), connection, Context.BIND_AUTO_CREATE); check(bound) }
        }
    }
    fun stop() {
        ++serial; pending = null; stopping = remote != null
        runCatching { remote?.send(Message.obtain(null, 3)) }
        if (!stopping) event(JSONObject().put("type", "stopped"))
    }
    override fun close() { stop(); if (bound) context.unbindService(connection); bound = false; remote = null }
}
