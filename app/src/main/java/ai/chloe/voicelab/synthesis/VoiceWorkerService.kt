package ai.chloe.voicelab.synthesis

import android.app.Service
import android.content.Intent
import android.os.*
import ai.chloe.voicelab.diagnostics.LabLog
import ai.chloe.voicelab.diagnostics.deviceTelemetry
import ai.chloe.voicelab.lab.CpuThreads
import ai.chloe.voicelab.model.ModelLibrary
import ai.chloe.voicelab.model.ModelSpec
import ai.chloe.voicelab.model.PackManifest
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.system.exitProcess

/** Bound service only; foreground UI owns its lifetime. No microphone or network. */
class VoiceWorkerService : Service() {
    private val executor = Executors.newSingleThreadExecutor()
    private val busy = AtomicBoolean(false)
    private val main = Handler(Looper.getMainLooper())
    private var bridge: NativeBridge? = null
    private var ready = false
    private var loadedSpec: ModelSpec? = null
    private lateinit var log: LabLog
    private var client: Messenger? = null
    @Volatile private var peakPss = 0
    @Volatile private var peakThermal = 0
    private var cpuStartMs = 0L
    private var nativeBytes = 0L
    private var operation = 0
    private var operationStart = 0L
    private var requestId = 0
    private val monitor = object : Runnable {
        override fun run() {
            if (!busy.get()) return
            val info = Debug.MemoryInfo().also { Debug.getMemoryInfo(it) }
            peakPss = maxOf(peakPss, info.totalPss)
            nativeBytes = Debug.getNativeHeapAllocatedSize()
            peakThermal = maxOf(peakThermal, getSystemService(PowerManager::class.java).currentThermalStatus)
            val data = deviceTelemetry(this@VoiceWorkerService).put("pss_kib", info.totalPss).put("peak_pss_kib", peakPss)
                .put("native_heap_bytes", nativeBytes).put("operation", operation)
                .put("elapsed_ms", SystemClock.elapsedRealtime() - operationStart)
                .put("thermal_status", getSystemService(PowerManager::class.java).currentThermalStatus)
            log.record("memory", data)
            send("memory", data)
            main.postDelayed(this, 1000)
        }
    }
    private val incoming = Messenger(Handler(Looper.getMainLooper()) { msg ->
        when (msg.what) {
            VoiceProtocol.STOP -> {
                log.record("stop_worker", JSONObject().put("busy", busy.get()))
                // Upstream buffered synthesis has no safe mid-token cancellation API.
                // Killing only :voice is deliberate: bounded stop, release all native RAM.
                Process.killProcess(Process.myPid()); exitProcess(0)
            }
            VoiceProtocol.INIT, VoiceProtocol.GENERATE -> {
                client = msg.replyTo
                if (!busy.compareAndSet(false, true)) { send("error", JSONObject().put("message", "추론 작업이 이미 진행 중입니다.")); return@Handler true }
                operation = msg.what
                requestId = msg.arg1
                operationStart = SystemClock.elapsedRealtime()
                peakPss = 0
                peakThermal = getSystemService(PowerManager::class.java).currentThermalStatus
                cpuStartMs = Process.getElapsedCpuTime()
                main.post(monitor)
                val threads = msg.data.getInt("threads", 4)
                val text = msg.data.getString("text").orEmpty()
                val instruction = msg.data.getString("instruction").orEmpty()
                val modelKey = msg.data.getString("model").orEmpty()
                val requestedPath = msg.data.getString("output").orEmpty()
                executor.execute {
                    var completion: Pair<String, JSONObject>? = null
                    try {
                        require(CpuThreads.valid(threads, Runtime.getRuntime().availableProcessors())) { "지원 범위를 벗어난 CPU 스레드 수입니다." }
                        val telemetryStart = deviceTelemetry(this)
                        if (operation == VoiceProtocol.INIT) {
                            ready = false
                            loadedSpec = null
                            val spec = ModelSpec.fromKey(modelKey)
                            send("initializing")
                            val native = bridge ?: NativeBridge().also { bridge = it }
                            val logs = File(filesDir, "logs").apply { mkdirs() }
                            val nativeLog = File(logs, "native.log")
                            if (nativeLog.length() > 8 * 1024 * 1024) nativeLog.writeText("")
                            val directory = ModelLibrary(File(filesDir, "models")).directory(spec)
                            val manifest = PackManifest.parse(File(directory, "model-pack.json").readText())
                            require(manifest.spec == spec) { "모델 패키지와 선택한 모델이 다릅니다." }
                            val capabilities = native.initialize(directory.path, spec.talkerFile, spec.hiddenSize, nativeLog.path, threads)
                            loadedSpec = spec
                            ready = true
                            completion = "ready" to JSONObject().put("capabilities", capabilities)
                                .put("init_ms", SystemClock.elapsedRealtime() - operationStart)
                                .put("threads", threads).put("backend", native.backendName())
                        } else {
                            check(ready) { "모델을 먼저 초기화하세요." }
                            require(instruction.codePointCount(0, instruction.length) <= 240)
                            require(loadedSpec!!.supportsInstruction || instruction.isBlank()) { "0.6B는 말투 지시를 지원하지 않습니다." }
                            require(text.isNotBlank() && text.codePointCount(0, text.length) <= 240)
                            val outputRoot = File(filesDir, "audio").apply { mkdirs() }.canonicalFile
                            val output = File(requestedPath).canonicalFile
                            require(output.parentFile == outputRoot && output.name.endsWith(".wav"))
                            val partial = File(output.path + ".partial")
                            send("generating")
                            try {
                                val nativeStartNanos = System.nanoTime()
                                val metrics = bridge!!.synthesize(text.toByteArray(Charsets.UTF_8), partial.path, instruction.toByteArray(Charsets.UTF_8), threads)
                                check(partial.renameTo(output)) { "WAV 저장 실패" }
                                completion = "generated" to JSONObject().put("path", output.path)
                                    .put("generation_ms", metrics[0]).put("audio_seconds", metrics[1])
                                    .put("sample_rate", metrics[2].toInt()).put("samples", metrics[3].toLong())
                                    .put("native_wav_ready_ms", metrics[4])
                                    .put("pcm_ready_nanos", nativeStartNanos + (metrics[0] * 1_000_000).toLong())
                                    .put("worker_total_ms", SystemClock.elapsedRealtime() - operationStart)
                                    .put("peak_worker_pss_kib", peakPss).put("seed", 42)
                                    .put("runtime_commit", VoiceProtocol.RUNTIME_COMMIT)
                                    .put("threads", threads).put("backend", bridge!!.backendName())
                                    .put("available_processors", Runtime.getRuntime().availableProcessors())
                                    .put("worker_cpu_time_ms", Process.getElapsedCpuTime() - cpuStartMs)
                                    .put("telemetry_start", telemetryStart).put("telemetry_end", deviceTelemetry(this))
                                    .put("peak_thermal_status", maxOf(peakThermal, getSystemService(PowerManager::class.java).currentThermalStatus))
                            } finally { partial.delete() }
                        }
                    } catch (e: Throwable) {
                        ready = false
                        log.record("failure", JSONObject().put("type", e.javaClass.name).put("message", e.message.orEmpty()))
                        completion = "error" to JSONObject().put("message", e.message ?: e.javaClass.simpleName)
                    } finally {
                        busy.set(false); main.removeCallbacks(monitor)
                        completion?.let { send(it.first, it.second) }
                    }
                }
            }
        }
        true
    })
    override fun onCreate() { super.onCreate(); log = LabLog(this, "worker") }
    override fun onBind(intent: Intent): IBinder = incoming.binder
    private fun send(type: String, data: JSONObject = JSONObject()) {
        data.put("type", type)
        if (type != "memory") log.record(type, JSONObject(data.toString()))
        runCatching { client?.send(Message.obtain(null, VoiceProtocol.EVENT).apply {
            arg1 = requestId
            this.data = Bundle().apply { putString("json", data.toString()) }
        }) }
    }
    override fun onDestroy() {
        main.removeCallbacks(monitor)
        executor.shutdownNow()
        super.onDestroy()
        // No JNI object destruction races with an in-flight ggml call.
        Process.killProcess(Process.myPid())
    }
}
