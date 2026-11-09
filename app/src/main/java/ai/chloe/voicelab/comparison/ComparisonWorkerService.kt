package ai.chloe.voicelab.comparison

import android.app.Service
import android.content.Intent
import android.os.*
import ai.chloe.voicelab.diagnostics.LabLog
import ai.chloe.voicelab.diagnostics.deviceTelemetry
import ai.chloe.voicelab.model.ModelLibrary
import ai.chloe.voicelab.model.ModelSpec
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Independent native lifetime; comparison crashes never mutate the established voice engine. */
class ComparisonWorkerService : Service() {
    private lateinit var log: LabLog
    private val executor = Executors.newSingleThreadExecutor()
    private val busy = AtomicBoolean(false)
    private var native: ComparisonNative? = null
    private var loaded = ""
    private var initMs = 0L
    private var runs = 0
    private val main = Handler(Looper.getMainLooper())
    private var client: Messenger? = null
    private var request = 0
    @Volatile private var peakPss = 0
    @Volatile private var peakThermal = 0
    private val monitor = object : Runnable {
        override fun run() { if (!busy.get()) return
            peakPss = maxOf(peakPss, Debug.MemoryInfo().also { Debug.getMemoryInfo(it) }.totalPss)
            peakThermal = maxOf(peakThermal, getSystemService(PowerManager::class.java).currentThermalStatus)
            log.record("comparison_memory",JSONObject().put("peak_pss_kib",peakPss).put("peak_thermal_status",peakThermal))
            main.postDelayed(this, 1000)
        }
    }
    private fun send(data: JSONObject) { log.record("comparison_event",JSONObject(data.toString())); runCatching { client?.send(Message.obtain(null, 4).apply { arg1 = request; this.data = Bundle().apply { putString("json", data.toString()) } }) } }
    private val incoming = Messenger(Handler(Looper.getMainLooper()) { msg ->
        if (msg.what == 3) { Process.killProcess(Process.myPid()); return@Handler true }
        if (msg.what != 2) return@Handler true
        if (!busy.compareAndSet(false, true)) return@Handler true
        client = msg.replyTo; request = msg.arg1
        val model = msg.data.getString("model").orEmpty(); val text = msg.data.getString("text").orEmpty()
        val instruction = msg.data.getString("instruction").orEmpty(); val seed = msg.data.getInt("seed")
        val id = msg.data.getString("id").orEmpty()
        peakPss = 0; peakThermal = 0; main.post(monitor)
        executor.execute {
            val started = SystemClock.elapsedRealtime(); val cpu = Process.getElapsedCpuTime()
            val startTelemetry = deviceTelemetry(this)
            var completion: JSONObject? = null
            try {
                require(model in listOf(CUSTOM, DESIGN) && seed >= 0)
                require(text.codePointCount(0, text.length) in 1..240 && instruction.codePointCount(0, instruction.length) <= 500)
                require(id.matches(Regex("[0-9a-f-]{36}")))
                val engine = native ?: ComparisonNative().also { native = it }
                val reused = loaded == model
                if (!reused) {
                    send(JSONObject().put("type", "initializing"))
                    val folder = if (model == CUSTOM) ModelLibrary(File(filesDir, "models")).directory(ModelSpec.LARGE) else File(filesDir, "tts-comparison/design")
                    val talker = if (model == CUSTOM) ModelSpec.LARGE.talkerFile else "qwen-talker-1.7b-voicedesign-f16-stable.gguf"
                    val start = SystemClock.elapsedRealtime(); loaded = ""
                    engine.initialize(folder.path, talker, model == DESIGN)
                    initMs = SystemClock.elapsedRealtime() - start; loaded = model; runs = 0
                }
                send(JSONObject().put("type", "generating"))
                val directory = File(filesDir, "tts-comparison/clips").apply { mkdirs() }
                val partial = File(directory, "$id.wav.partial"); val target = File(directory, "$id.wav")
                try {
                    val generationStart = System.nanoTime()
                    val m = engine.generate(text.toByteArray(Charsets.UTF_8), instruction.toByteArray(Charsets.UTF_8), seed, partial.path)
                    validateWav(partial); check(partial.renameTo(target))
                    val pss = Debug.MemoryInfo().also { Debug.getMemoryInfo(it) }.totalPss
                    val report = JSONObject().put("type", "generated").put("file", target.name)
                        .put("model_init_ms", initMs).put("init_this_request_ms", if (reused) 0 else initMs)
                        .put("model_reused", reused).put("generation_index", runs++)
                        .put("generation_ms", m[0]).put("audio_seconds", m[1]).put("rtf", m[0] / (m[1] * 1000))
                        .put("sample_rate", m[2]).put("samples", m[3]).put("native_wav_ready_ms", m[4])
                        .put("code_generation_ms", m[5]).put("audio_decode_ms", m[6])
                        .put("first_pcm_ready_ms", m[0]).put("streaming_first_chunk_ms", JSONObject.NULL)
                        .put("first_output_ms", JSONObject.NULL).put("physical_speaker_first_sound_ms", JSONObject.NULL)
                        .put("generation_start_nanos", generationStart).put("request_total_ms", SystemClock.elapsedRealtime() - started)
                        .put("peak_pss_kib", maxOf(peakPss, pss)).put("pss_method", "1s sampled worker PSS, not continuous absolute peak")
                        .put("worker_cpu_ms", Process.getElapsedCpuTime() - cpu).put("threads", 4).put("backend", "CPU")
                        .put("gpu_utilization", JSONObject.NULL).put("cpu_utilization_percent", JSONObject.NULL)
                        .put("telemetry_start", startTelemetry).put("telemetry_end", deviceTelemetry(this)).put("peak_thermal_status", maxOf(peakThermal, getSystemService(PowerManager::class.java).currentThermalStatus))
                    completion = report
                } finally { partial.delete() }
            } catch (e: Throwable) { loaded = ""; completion = JSONObject().put("type", "error").put("message", e.message ?: e.javaClass.simpleName) }
            finally { busy.set(false); main.removeCallbacks(monitor) }
            completion?.let(::send)
        }
        true
    })
    override fun onCreate() { super.onCreate();log=LabLog(this,"comparison-worker") }
    override fun onBind(intent: Intent): IBinder = incoming.binder
    override fun onDestroy() { main.removeCallbacks(monitor); executor.shutdownNow(); super.onDestroy(); Process.killProcess(Process.myPid()) }
}
