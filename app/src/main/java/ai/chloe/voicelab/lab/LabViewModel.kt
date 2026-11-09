package ai.chloe.voicelab.lab

import android.app.Application
import android.net.Uri
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.chloe.voicelab.audio.WavPlayer
import ai.chloe.voicelab.diagnostics.LabLog
import ai.chloe.voicelab.model.ModelStore
import ai.chloe.voicelab.model.ModelSpec
import ai.chloe.voicelab.synthesis.LocalVoiceEngine
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject
import java.io.File
import java.util.UUID

internal data class LabState(
    val text: String = koreanSamples.first(),
    val status: String = "모델 폴더를 가져온 뒤 초기화해 주세요.",
    val installed: Boolean = false,
    val model: ModelSpec = ModelSpec.SMALL,
    val installedModels: Set<ModelSpec> = emptySet(),
    val instruction: String = "",
    val ready: Boolean = false,
    val busy: Boolean = false,
    val importing: Boolean = false,
    val playing: Boolean = false,
    val autoPlay: Boolean = true,
    val error: String? = null,
    val memory: String = "미측정",
    val metrics: String = "아직 생성하지 않았습니다.",
    val hasAudio: Boolean = false,
    val hasReport: Boolean = false,
    val pronunciation: Int = 0,
    val intonation: Int = 0,
    val rhythm: Int = 0,
    val notes: String = "",
    val cpuCount: Int = CpuThreads.limit(Runtime.getRuntime().availableProcessors()),
    val threads: Int = 4.coerceAtMost(CpuThreads.limit(Runtime.getRuntime().availableProcessors())),
    val benchmarking: Boolean = false,
    val benchmarkSummary: String = "자동 비교 결과가 없습니다.",
    val hasBenchmark: Boolean = false,
    val backend: String = "초기화 전",
    val referenceId: String? = null,
)

internal class LabViewModel(app: Application) : AndroidViewModel(app) {
    val references = voiceReferences(app.assets.open("voice-reference-catalog.json").bufferedReader().use { it.readText() })
    private val store = ModelStore(app)
    private val preferences = app.getSharedPreferences("voice_lab", 0)
    private val initialSpec = runCatching { ModelSpec.fromKey(preferences.getString("model", if (ai.chloe.voicelab.BuildConfig.PERFORMANCE_EDITION) "1.7b" else "0.6b")!!) }.getOrDefault(ModelSpec.SMALL)
    private val log = LabLog(app, "ui")
    private val mutable = MutableStateFlow(LabState(model = initialSpec, installed = store.installed(initialSpec),
        installedModels = ModelSpec.entries.filter { store.installed(it) }.toSet(),
        threads = preferences.getInt("threads", 4).coerceIn(1, CpuThreads.limit(Runtime.getRuntime().availableProcessors()))))
    val state = mutable.asStateFlow()
    private val engine = LocalVoiceEngine(app, ::event)
    private val player = WavPlayer(app, viewModelScope)
    private var importJob: Job? = null
    private var exportJob: Job? = null
    private var output: File? = null
    private var report: JSONObject? = null
    private var reportFile: File? = null
    private var requestedNanos = 0L
    private var playbackId = 0
    private var benchmarkId = ""
    private var benchmarkTickets = emptyList<CpuTicket>()
    private var benchmarkIndex = 0
    private var originalThreads = 4
    private var benchmarkSnapshot = JSONObject()
    private val benchmarkRows = mutableListOf<JSONObject>()
    private var benchmarkFile: File? = null
    private var benchmarkStatus = "not_started"
    private var benchmarkStartedMs = 0L

    fun setThreads(value: Int) {
        if (state.value.busy || state.value.playing || state.value.benchmarking || !CpuThreads.valid(value, state.value.cpuCount)) return
        preferences.edit().putInt("threads", value).apply()
        mutable.update { it.copy(threads = value) }
    }
    fun startBenchmark() {
        val s = state.value
        if (!s.ready || s.busy || s.playing || s.benchmarking) return
        if (s.text.isBlank() || s.text.codePointCount(0, s.text.length) > 240 || s.instruction.codePointCount(0, s.instruction.length) > 240) {
            error("문장과 말투 지시 길이를 확인하세요.", true); return
        }
        if (getApplication<Application>().getSystemService(android.os.PowerManager::class.java).currentThermalStatus >= android.os.PowerManager.THERMAL_STATUS_SEVERE) {
            error("기기를 식힌 뒤 비교를 시작하세요. 현재 열 상태가 높습니다.", true); return
        }
        benchmarkId = UUID.randomUUID().toString()
        benchmarkTickets = cpuTickets(s.cpuCount); benchmarkIndex = 0; originalThreads = s.threads
        benchmarkRows.clear(); benchmarkStatus = "running"
        benchmarkStartedMs = android.os.SystemClock.elapsedRealtime()
        benchmarkSnapshot = JSONObject().put("input", s.text).put("instruction", s.instruction).put("model_variant", s.model.key)
            .put("cpu_count", s.cpuCount).put("seed", 42).put("precision", "f16-f32-cp-down")
            .put("rounds", 2).put("backend_requested", "CPU").put("app_version", ai.chloe.voicelab.BuildConfig.VERSION_NAME)
            .put("application_id", ai.chloe.voicelab.BuildConfig.APPLICATION_ID)
            .put("device", Build.MODEL).put("sdk", Build.VERSION.SDK_INT)
        benchmarkFile = File(getApplication<Application>().filesDir, "reports/benchmark-$benchmarkId.json").also { it.parentFile!!.mkdirs() }
        mutable.update { it.copy(benchmarking = true, hasBenchmark = true, benchmarkSummary = "준비 1회 + 스레드별 2회 · 재생 생략 · 수분 걸릴 수 있습니다.") }
        log.record("cpu_benchmark_started", JSONObject().put("benchmark_id", benchmarkId).put("planned_runs", benchmarkTickets.size))
        saveBenchmark()
        nextBenchmark()
    }
    private fun nextBenchmark() {
        if (!state.value.benchmarking) return
        val ticket = benchmarkTickets[benchmarkIndex]
        mutable.update { it.copy(threads = ticket.threads) }
        generateInternal()
    }
    private fun recordBenchmark() {
        benchmarkRows += JSONObject(checkNotNull(report).toString())
        benchmarkIndex++
        val heat = benchmarkRows.last().optInt("peak_thermal_status")
        if (heat >= android.os.PowerManager.THERMAL_STATUS_SEVERE) {
            finishBenchmark("thermal_limit")
        } else if (benchmarkIndex >= benchmarkTickets.size) {
            finishBenchmark("completed")
        } else {
            saveBenchmark()
            val id = benchmarkId
            viewModelScope.launch { delay(350); if (state.value.benchmarking && benchmarkId == id) nextBenchmark() }
        }
    }
    private fun finishBenchmark(status: String) {
        if (!state.value.benchmarking) return
        benchmarkStatus = status
        log.record("cpu_benchmark_finished", JSONObject().put("benchmark_id", benchmarkId).put("status", status).put("runs", benchmarkRows.size))
        mutable.update { it.copy(benchmarking = false, threads = originalThreads) }
        saveBenchmark()
    }
    private fun saveBenchmark() {
        val observations = benchmarkRows.map { CpuObservation(it.getInt("threads"), it.getDouble("generation_ms"),
            it.getDouble("audio_seconds"), it.getLong("samples"), it.optBoolean("benchmark_warmup")) }
        val summaries = cpuSummaries(observations)
        val sameLength = observations.filter { !it.warmup }.map { it.samples }.distinct().size <= 1
        val document = JSONObject().put("schema", 1).put("benchmark_id", benchmarkId).put("status", benchmarkStatus)
            .put("conditions", benchmarkSnapshot).put("runs", org.json.JSONArray(benchmarkRows))
            .put("elapsed_ms", android.os.SystemClock.elapsedRealtime() - benchmarkStartedMs)
            .put("same_output_length", sameLength).put("first_output_method", "No playback in automatic comparison; use single synthesis with autoplay for output latency")
            .put("summaries", org.json.JSONArray(summaries.map { JSONObject().put("threads", it.threads).put("count", it.count)
                .put("median_generation_ms", it.medianMs).put("best_generation_ms", it.bestMs).put("median_rtf", it.medianRtf) }))
        runCatching {
            benchmarkFile?.let { target ->
                val temporary = File(target.path + ".tmp")
                try {
                    temporary.writeText(document.toString(2))
                    check(temporary.renameTo(target)) { "비교 기록 교체 실패" }
                } finally { temporary.delete() }
            }
        }.onFailure { e ->
            mutable.update { it.copy(error = "성능 기록 저장 실패: ${e.message}") }
        }
        val rows = summaries.joinToString("\n") { "${it.threads} 스레드 · ${it.count}회 · 중앙값 %.0f ms · 최저 %.0f ms · RTF %.2f".format(it.medianMs, it.bestMs, it.medianRtf) }
        val phase = when (benchmarkStatus) { "completed" -> "비교 완료"; "thermal_limit" -> "높은 열 상태로 다음 실행 중단"; "running" -> "비교 중"; else -> "비교 중단 ($benchmarkStatus)" }
        mutable.update { it.copy(benchmarkSummary = "${benchmarkSnapshot.optString("model_variant")} · 마지막 비교: ${benchmarkSnapshot.optString("input").take(30)}\n$phase · ${benchmarkRows.size}/${benchmarkTickets.size}회 (준비 포함)\n$rows\n" +
            if (sameLength) "음질 확인 후 스레드를 선택하세요. 순서·발열 영향을 포함한 관측값입니다." else "출력 길이가 달라졌습니다. 발음·누락 여부를 확인한 뒤 속도를 비교하세요.") }
    }


    init {
        log.record("launch", JSONObject().put("version", ai.chloe.voicelab.BuildConfig.VERSION_NAME).put("device", Build.MODEL))
        File(app.filesDir, "audio").listFiles()?.filter { it.name.endsWith(".partial") }?.forEach { it.delete() }
    }
    fun applyReference(id: String, includeText: Boolean) {
        val s = state.value
        if (s.busy || s.playing || s.benchmarking || !s.model.supportsInstruction) return
        val reference = references.firstOrNull { it.id == id } ?: return
        mutable.update { it.copy(instruction = reference.instruction,
            text = if (includeText) reference.text else it.text, referenceId = reference.id,
            status = "${reference.label} 말투 적용 · 새 문장의 품질은 별도 확인이 필요합니다.") }
    }
    fun setText(value: String) { if (!state.value.busy && !state.value.benchmarking) mutable.update { it.copy(text = value) } }
    fun setAutoPlay(value: Boolean) { mutable.update { it.copy(autoPlay = value) } }
    fun setInstruction(value: String) {
        if (!state.value.busy && !state.value.benchmarking && state.value.model.supportsInstruction) mutable.update { it.copy(instruction = value, referenceId = null) }
    }
    fun selectModel(spec: ModelSpec) {
        if (state.value.busy || state.value.playing || state.value.benchmarking || state.value.model == spec) return
        stopPlayback()
        output = null; report = null; reportFile = null
        mutable.update { it.copy(ready = false, busy = true) }
        engine.stop()
        preferences.edit().putString("model", spec.key).apply()
        mutable.update { it.copy(model = spec, installed = store.installed(spec), instruction = "", referenceId = null, error = null,
            hasAudio = false, hasReport = false, metrics = "선택한 모델의 측정 결과가 없습니다.", memory = "미측정",
            pronunciation = 0, intonation = 0, rhythm = 0, notes = "", status = "${spec.label} 선택됨 · 초기화해 주세요.") }
    }
    fun rate(kind: String, value: Int) = mutable.update {
        when (kind) {
            "pronunciation" -> it.copy(pronunciation = value)
            "intonation" -> it.copy(intonation = value)
            else -> it.copy(rhythm = value)
        }
    }
    fun notes(value: String) { mutable.update { it.copy(notes = value) } }
    fun importModels(uri: Uri) {
        if (state.value.busy || state.value.ready || state.value.benchmarking) return
        stopPlayback()
        mutable.update { it.copy(busy = true, importing = true, error = null, status = "모델 패키지 검사 중…") }
        importJob = viewModelScope.launch {
            try {
                val selected = state.value.model
                withContext(Dispatchers.IO) { store.import(uri, selected) { progress -> mutable.update { it.copy(status = progress) } } }
                mutable.update { it.copy(installed = store.installed(it.model),
                    installedModels = ModelSpec.entries.filter { spec -> store.installed(spec) }.toSet(),
                    status = "${selected.label} 가져오기 완료. 초기화를 눌러 주세요.") }
                log.record("model_imported")
            } catch (e: CancellationException) {
                mutable.update { it.copy(status = "모델 가져오기를 중지했습니다.") }
                throw e
            } catch (e: Exception) { error(e.message ?: "모델 가져오기 실패") }
            finally { mutable.update { it.copy(busy = false, importing = false) } }
        }
    }
    fun initialize() {
        if (!state.value.installed || state.value.busy) return
        stopPlayback()
        mutable.update { it.copy(busy = true, ready = false, error = null, status = "추론 서비스 연결 중…") }
        runCatching { engine.initialize(state.value.model.key, state.value.threads) }.onFailure { error(it.message ?: "초기화 실패") }
    }
    fun generate() { if (!state.value.benchmarking) generateInternal() }
    private fun generateInternal() {
        val s = state.value
        if (!s.ready || s.busy) return
        if (s.text.isBlank() || s.text.codePointCount(0, s.text.length) > 240) { error("한국어 문장을 1~240자 입력하세요.", keepReady = true); return }
        if (s.instruction.codePointCount(0, s.instruction.length) > 240) { error("말투 지시를 240자 이내로 입력하세요.", keepReady = true); return }
        stopPlayback()
        output = null; report = null; reportFile = null
        requestedNanos = System.nanoTime()
        val file = File(getApplication<Application>().filesDir, "audio/${UUID.randomUUID()}.wav")
        mutable.update { it.copy(busy = true, error = null, status = if (s.benchmarking) "CPU 비교 ${benchmarkIndex + 1}/${benchmarkTickets.size} · ${s.threads} 스레드" else "Sohee 음성 생성 중…", hasAudio = false,
            hasReport = false, metrics = "생성 중…", pronunciation = 0, intonation = 0, rhythm = 0, notes = "") }
        log.record("generation_requested", JSONObject().put("characters", s.text.codePointCount(0, s.text.length)))
        runCatching { engine.synthesize(s.text, file.path, s.instruction, s.threads) }.onFailure { error(it.message ?: "생성 요청 실패") }
    }
    private fun event(data: JSONObject) {
        when (data.optString("type")) {
            "initializing" -> mutable.update { it.copy(status = "${it.model.label} F16 모델 초기화 중…") }
            "ready" -> mutable.update { it.copy(busy = false, ready = true, backend = data.optString("backend", "unknown"), status = "${it.model.label} Sohee 준비 완료 · 초기화 ${data.optLong("init_ms")} ms") }
            "generating" -> mutable.update { it.copy(status = if (it.benchmarking) "CPU 비교 ${benchmarkIndex + 1}/${benchmarkTickets.size} · ${it.threads} 스레드" else "Sohee 음성 생성 중…") }
            "memory" -> mutable.update { it.copy(memory = "추론 PSS ${"%.1f".format(data.optInt("pss_kib") / 1024.0)} MiB · 관측 최대 ${"%.1f".format(data.optInt("peak_pss_kib") / 1024.0)} MiB · ${data.optLong("elapsed_ms") / 1000}초 · 열 상태 ${data.optInt("thermal_status")} · 배터리 온도 ${data.opt("battery_temperature_c")}°C") }
            "generated" -> {
                output = File(data.getString("path"))
                val generation = data.getDouble("generation_ms")
                val seconds = data.getDouble("audio_seconds")
                report = JSONObject(data.toString()).apply {
                    put("app_version", ai.chloe.voicelab.BuildConfig.VERSION_NAME)
                    put("application_id", ai.chloe.voicelab.BuildConfig.APPLICATION_ID)
                    put("model_variant", state.value.model.key).put("instruction", state.value.instruction)
                    val reference = references.firstOrNull { it.id == state.value.referenceId }
                    put("style_reference", reference?.let { JSONObject().put("id", it.id).put("source_study", it.sourceStudy)
                        .put("wav_sha256", it.wavSha256).put("application", "instruction_only").put("reference_pcm_used", false) } ?: JSONObject.NULL)
                    remove("path"); remove("pcm_ready_nanos"); remove("type")
                    put("audio_id", output!!.nameWithoutExtension)
                    put("input", state.value.text).put("speaker", "sohee").put("language", "Korean")
                    put("precision", "f16-f32-cp-down").put("mode", "buffered")
                    put("rtf", realTimeFactor(generation, seconds))
                    put("first_pcm_ready_ms", (data.getLong("pcm_ready_nanos") - requestedNanos) / 1_000_000.0)
                    put("wav_received_ms", (System.nanoTime() - requestedNanos) / 1_000_000.0)
                    put("first_output_ms", JSONObject.NULL)
                    put("first_output_method", "AudioTrack hardware timestamp; null if unavailable or manual playback")
                    put("device", Build.MODEL).put("sdk", Build.VERSION.SDK_INT)
                    put("fingerprint", Build.FINGERPRINT).put("abi", Build.SUPPORTED_ABIS.firstOrNull())
                    put("created_at_epoch_ms", System.currentTimeMillis())
                    put("model_pack", JSONObject(File(store.directory(state.value.model), "model-pack.json").readText()))
                }
                if (state.value.benchmarking) {
                    val ticket = benchmarkTickets[benchmarkIndex]
                    report!!.put("benchmark_id", benchmarkId).put("benchmark_warmup", ticket.warmup).put("benchmark_round", ticket.round)
                }
                val reports = File(getApplication<Application>().filesDir, "reports").apply { mkdirs() }
                reportFile = File(reports, output!!.nameWithoutExtension + ".json")
                updateReport()
                mutable.update { it.copy(busy = false, hasAudio = true, hasReport = true, status = "WAV 생성 완료 · 24 kHz / PCM16 / 모노") }
                if (state.value.benchmarking) recordBenchmark() else if (state.value.autoPlay) play(auto = true)
            }
            "error" -> error(data.optString("message", "추론 오류"))
            "worker_died" -> {
                ++playbackId; player.stop()
                error("추론 프로세스가 종료됐습니다. 메모리 부족 또는 네이티브 오류일 수 있습니다. 모델을 다시 초기화하세요.")
            }
            "stopped" -> mutable.update { it.copy(busy = false, ready = false, status = "중지됨 · 생성하려면 모델을 다시 초기화하세요.") }
        }
    }
    fun play(auto: Boolean = false) {
        val file = output ?: return
        if (state.value.busy || state.value.benchmarking) return
        val id = ++playbackId
        mutable.update { it.copy(playing = true, error = null, status = "WAV 재생 중…") }
        player.play(file, onFirstFrame = { nanos ->
            if (id == playbackId && auto) {
                val delay = (nanos - requestedNanos) / 1_000_000.0
                if (delay >= 0) { report?.put("first_output_ms", delay); updateReport() }
            }
        }, onFinished = { message ->
            if (id == playbackId) {
                report?.put("playback_error", message ?: JSONObject.NULL)
                updateReport()
                mutable.update { it.copy(playing = false, status = if (message == null) "WAV 재생 완료" else "재생 오류", error = message) }
                log.record("playback_finished", JSONObject().put("error", message ?: JSONObject.NULL))
            }
        })
    }
    private fun stopPlayback() { ++playbackId; player.stop(); mutable.update { it.copy(playing = false) } }
    fun stop() {
        finishBenchmark("stopped")
        stopPlayback()
        if (state.value.importing) { importJob?.cancel(); return }
        mutable.update { it.copy(ready = false, busy = true, status = "추론 프로세스 중지 중…") }
        engine.stop()
    }
    fun saveEvaluation() {
        val s = state.value
        report?.put("evaluation", JSONObject().put("pronunciation_1_5", s.pronunciation.takeIf { it > 0 } ?: JSONObject.NULL)
            .put("intonation_1_5", s.intonation.takeIf { it > 0 } ?: JSONObject.NULL)
            .put("rhythm_1_5", s.rhythm.takeIf { it > 0 } ?: JSONObject.NULL).put("notes", s.notes))
        updateReport()
        mutable.update { it.copy(status = "청취 평가를 내부 저장소에 저장했습니다.") }
    }
    private fun updateReport() {
        val r = report ?: return
        runCatching { reportFile?.writeText(r.toString(2)) }.onFailure { error(it.message ?: "측정 기록 저장 실패", true) }
        val outputMs = if (r.isNull("first_output_ms")) "미측정" else "%.0f ms".format(r.getDouble("first_output_ms"))
        mutable.update { it.copy(metrics = "${r.optInt("threads")} 스레드 · ${r.optString("backend")}\n생성 %.0f ms · 오디오 %.2f초 · RTF %.2f\n첫 PCM 준비 %.0f ms · WAV 수신 %.0f ms\n첫 재생 출력 $outputMs (기기 타임스탬프)".format(
            r.getDouble("generation_ms"), r.getDouble("audio_seconds"), r.getDouble("rtf"),
            r.getDouble("first_pcm_ready_ms"), r.getDouble("wav_received_ms"))) }
    }
    fun export(uri: Uri, kind: String) {
        if (exportJob?.isActive == true) return
        val text = if (kind == "benchmark") benchmarkFile?.takeIf { it.exists() }?.readText() else report?.toString(2)
        val source = output
        exportJob = viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    getApplication<Application>().contentResolver.openOutputStream(uri, "wt")!!.use { stream ->
                        if (kind == "wav") checkNotNull(source).inputStream().use { it.copyTo(stream) }
                        else stream.write(checkNotNull(text).toByteArray(Charsets.UTF_8))
                    }
                }
                mutable.update { it.copy(status = "${kind.uppercase()} 내보내기 완료") }
            } catch (e: Exception) { error(e.message ?: "내보내기 실패", true) }
        }
    }
    private fun error(message: String, keepReady: Boolean = false) {
        finishBenchmark("error")
        mutable.update { it.copy(busy = false, ready = keepReady && it.ready, playing = false, error = message, status = "작업 실패") }
        log.record("error", JSONObject().put("message", message))
    }
    override fun onCleared() { finishBenchmark("closed"); engine.close(); player.stop(); super.onCleared() }
}
