package ai.chloe.voicelab.comparison

import android.app.Application
import android.net.Uri
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.chloe.voicelab.lab.voiceReferences
import ai.chloe.voicelab.model.ModelLibrary
import ai.chloe.voicelab.model.ModelSpec
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID

internal data class ComparisonState(
    val model: String = CUSTOM, val caseIndex: Int = 0, val instruction: String = COMMON_STYLE,
    val condition: String = "controlled", val seed: Int = 42, val busy: Boolean = false,
    val importing: Boolean = false, val playing: Boolean = false, val status: String = "오프라인 TTS 비교 실험",
    val error: String? = null, val records: Int = 0, val hasOutput: Boolean = false,
    val blindCondition: String = "controlled", val blind: Boolean = false, val revealed: Boolean = false, val pairText: String = "",
    val hasPair: Boolean = false, val scores: List<List<Int>> = List(2) { List(6) { 0 } },
    val referenceId: String? = null, val notes: String = "", val metrics: String = "미측정", val designInstalled: Boolean = false,
)
internal class ComparisonViewModel(app: Application) : AndroidViewModel(app) {
    val referenceStyles = voiceReferences(app.assets.open("voice-reference-catalog.json").bufferedReader().use { it.readText() })
    val cases = testCases(app.assets.open("tts-comparison-cases.json").bufferedReader().use { it.readText() })
    private val storage = ComparisonStorage(app)
    private val mutable = MutableStateFlow(ComparisonState(hasOutput = storage.allRecords().isNotEmpty(), records = storage.allRecords().size, designInstalled = storage.design.isDirectory))
    val state = mutable.asStateFlow()
    private val player = ComparisonWavPlayer(app, viewModelScope)
    private val engine = ComparisonClient(app, ::event)
    private var records = storage.allRecords()
    private var active: JSONObject? = null
    private var last: JSONObject? = records.maxByOrNull { it.optLong("created_epoch_ms") }
    private var pending = ArrayDeque<Pair<Int, Int>>()
    private var batchId = ""
    private var planned = 0
    private var completed = 0
    private var importJob: Job? = null
    private var playbackToken = 0
    private var pair = emptyList<JSONObject>()
    private var trialId = ""
    private var evaluations = runCatching { JSONObject(File(storage.root,"evaluations.json").readText()).getJSONArray("trials") }.getOrDefault(JSONArray())
    fun available(model: String) = when (model) {
        CUSTOM -> ModelLibrary(File(getApplication<Application>().filesDir, "models")).installed(ModelSpec.LARGE)
        DESIGN -> storage.design.isDirectory
        else -> false
    }
    fun chooseModel(model: String) { if (state.value.busy || state.value.playing) return
        mutable.update { it.copy(model = model, referenceId = null, condition = "controlled", instruction = if (model == DESIGN) DESIGN_VOICE + COMMON_STYLE else COMMON_STYLE) }
    }
    fun chooseCase(index: Int) { if (!state.value.busy && !state.value.playing) mutable.update { it.copy(caseIndex = index, hasPair = if(it.blind) false else it.hasPair) } }
    fun instruction(value: String) { if (!state.value.busy) mutable.update { it.copy(referenceId = null, instruction = value, condition = if (value == (if (it.model == DESIGN) DESIGN_VOICE else "") + COMMON_STYLE) "controlled" else "optimized") } }
    fun applyStyle(id: String) {
        if (state.value.busy) return
        val style = referenceStyles.firstOrNull { it.id == id } ?: return
        mutable.update { it.copy(referenceId=id, condition="optimized", instruction=(if(it.model==DESIGN) DESIGN_VOICE else "") + style.instruction) }
    }
    fun condition(value: String) {
        if (state.value.busy) return
        if (value == "controlled" && state.value.instruction != (if (state.value.model == DESIGN) DESIGN_VOICE else "") + COMMON_STYLE) { fail("수정한 지시는 모델별 조정 조건으로 기록합니다."); return }
        mutable.update { it.copy(condition = value) }
    }
    fun seed(value: Int) { if (!state.value.busy) mutable.update { it.copy(seed = value) } }
    fun blindCondition(value: String) { if (!state.value.busy && !state.value.playing && value in setOf("controlled","optimized")) mutable.update { it.copy(blindCondition=value,hasPair=false) } }
    fun setBlind(value: Boolean) { if (state.value.busy || state.value.playing) return; mutable.update { it.copy(blind = value, hasPair = false, pairText = "", error = null, status = if(value) "블라인드 청취 · 모델 이름 숨김" else "생성·측정 화면") } }
    fun generate(batch: Boolean, repeats: Int = 1) {
        val s = state.value; if (s.busy || s.playing || !available(s.model)) return
        if (s.instruction.codePointCount(0,s.instruction.length)>500) { fail("지시는 500자 이하로 입력하세요."); return }
        if (getApplication<Application>().getSystemService(android.os.PowerManager::class.java).currentThermalStatus >= android.os.PowerManager.THERMAL_STATUS_SEVERE) { fail("기기를 식힌 뒤 실험을 시작하세요."); return }
        pending.clear(); if (batch) cases.indices.forEach { i -> listOf(42,43,44).forEach { pending.add(i to it) } } else repeat(repeats) { pending.add(s.caseIndex to s.seed) }
        batchId = UUID.randomUUID().toString(); planned = pending.size; completed = 0; next()
    }
    private fun next() {
        if (pending.isEmpty()) { saveBatch("completed"); mutable.update { it.copy(busy = false, status = "$completed/$planned 생성 완료") }; return }
        val (index, seed) = pending.removeFirst(); val s = state.value; val c = cases[index]; val id = UUID.randomUUID().toString()
        active = JSONObject().put("id",id).put("case_id",c.id).put("text",c.text).put("seed",seed)
            .put("batch_id",batchId).put("batch_index",completed).put("batch_size",planned).put("model_id",s.model).put("instruction",s.instruction).put("condition",s.condition).put("platform","android")
            .put("style_reference_id",s.referenceId ?: JSONObject.NULL).put("speaker",if(s.model==CUSTOM) "sohee" else JSONObject.NULL).put("precision","f16-f32-cp-down")
            .put("runtime_commit","4562731dc612cb87b4cd1eedac275a17d1078773")
            .put("sampling",JSONObject().put("temperature",0.9).put("top_k",50).put("top_p",1.0).put("repetition_penalty",1.05).put("max_audio_tokens",1024))
            .put("request_start_nanos",System.nanoTime()).put("created_epoch_ms",System.currentTimeMillis()).put("device",Build.MODEL).put("sdk",Build.VERSION.SDK_INT)
        mutable.update { it.copy(busy = true, error = null, status = "${completed+1}/$planned · ${c.id} · seed $seed") }
        runCatching { engine.generate(s.model,c.text,s.instruction,seed,id) }.onFailure { fail(it.message ?: "요청 실패") }
    }
    private fun event(row: JSONObject) {
        when(row.optString("type")) {
            "initializing" -> mutable.update { it.copy(status = "모델 초기화 중 · ${completed+1}/$planned") }
            "generating" -> mutable.update { it.copy(status = "음성 생성 중 · ${completed+1}/$planned") }
            "generated" -> {
                val r = active ?: return
                row.keys().forEach { k -> r.put(k,row.get(k)) }; r.remove("type")
                val audio = storage.audio(r); val hash = MessageDigest.getInstance("SHA-256")
                audio.inputStream().use { input -> val b=ByteArray(65536); while(true) { val n=input.read(b);if(n<0)break;hash.update(b,0,n) } }
                r.put("wav_sha256",hash.digest().joinToString("") { "%02x".format(it) })
                if(!persist(File(storage.clips,"${r.getString("id")}.json"),r)) { active=null; return }; last=r; active=null; completed++
                records=storage.allRecords()
                mutable.update { it.copy(hasOutput=true,records=records.size,metrics="생성 ${r.optLong("generation_ms")} ms · 길이 ${r.optDouble("audio_seconds")}초 · RTF %.2f\n초기화 ${r.optLong("model_init_ms")} ms · 관측 PSS ${r.optLong("peak_pss_kib")/1024} MiB\n첫 청크·실제 스피커 도달 시간 미측정".format(r.optDouble("rtf"))) }
                if (getApplication<Application>().getSystemService(android.os.PowerManager::class.java).currentThermalStatus >= android.os.PowerManager.THERMAL_STATUS_SEVERE) { pending.clear(); saveBatch("thermal_limit"); mutable.update { it.copy(busy=false,status="열 상태가 높아 다음 실행을 중단했습니다.") } }
                else { next(); if (planned == 1 && pending.isEmpty()) play(auto = true) }
            }
            "error", "worker_died" -> fail(row.optString("message","실험 추론 프로세스 종료 · 메모리/런타임 오류 가능"))
            "stopped" -> mutable.update { it.copy(busy=false,status="실험 중지됨 · 완료된 결과는 보존") }
        }
    }
    private fun persist(file: File, data: JSONObject): Boolean = runCatching { atomicJson(file,data) }.fold(
        onSuccess = { true }, onFailure = { e -> pending.clear(); mutable.update { it.copy(busy=false,error="기록 저장 실패: ${e.message}",status="저장 공간을 확인하세요.") }; false })
    private fun saveBatch(status: String) {
        if(batchId.isEmpty()) return
        persist(File(storage.root,"batch-$batchId.json"),JSONObject().put("id",batchId).put("status",status).put("completed",completed).put("planned",planned).put("model_id",state.value.model).put("condition",state.value.condition))
    }
    private fun fail(message: String) {
        if(state.value.busy && !state.value.importing) saveBatch("error")
        pending.clear(); ++playbackToken; active?.let { r -> persist(File(storage.root,"failure-${r.getString("id")}.json"),JSONObject(r.toString()).put("error",message)) }; active=null
        mutable.update { it.copy(busy=false,importing=false,error=message,status="작업 실패") }
    }
    fun stop() { if (state.value.importing) return; if(state.value.busy)saveBatch("cancelled"); pending.clear(); ++playbackToken; active?.let { r -> persist(File(storage.root,"cancelled-${r.getString("id")}.json"),JSONObject(r.toString()).put("status","cancelled")) }; active=null; player.stop(); mutable.update { it.copy(playing=false) }; engine.stop() }
    fun importFolder(uri: Uri, model: Boolean) {
        if (state.value.busy || state.value.playing) return
        mutable.update { it.copy(busy=true,importing=true,error=null,status=if(model) "모델 복사·SHA 검증 중…" else "샘플 복사·SHA 검증 중…") }
        importJob=viewModelScope.launch { try {
            val count=withContext(Dispatchers.IO) { if(model) { storage.importDesign(uri);0 } else storage.importSamples(uri,cases) }
            records=storage.allRecords(); mutable.update { it.copy(records=records.size,designInstalled=storage.design.isDirectory,status=if(model) "VoiceDesign 가져오기 완료" else "$count 샘플 가져오기 완료") }
        } catch(e:Exception) { fail(e.message ?: "가져오기 실패") } finally { mutable.update { it.copy(busy=false,importing=false) } } }
    }
    fun play(index: Int? = null, auto: Boolean = false) {
        if(state.value.busy || state.value.playing) return
        val row=if(index==null)last else pair.getOrNull(index);if(row==null)return
        mutable.update { it.copy(playing=true) }
        val token=++playbackToken
        val started=System.nanoTime()
        player.play(storage.audio(row),onFirstFrame=first@{ nanos ->
            if (token != playbackToken) return@first
            if (auto) {
                row.put("first_output_ms",(nanos-row.getLong("generation_start_nanos"))/1_000_000.0)
                    .put("first_output_from_request_ms",(nanos-row.getLong("request_start_nanos"))/1_000_000.0)
                    .put("first_output_method","AudioTrack hardware timestamp; not acoustic arrival")
                persist(File(storage.clips,"${row.getString("id")}.json"),row)
                mutable.update { it.copy(metrics = it.metrics + "\n첫 하드웨어 출력 %.0f ms (생성 시작 기준)".format(row.getDouble("first_output_ms"))) }
            } else row.put("manual_playback_first_frame_ms",(nanos-started)/1_000_000.0)
        },onFinished={ error -> if(token==playbackToken) mutable.update { it.copy(playing=false,error=error) } })
    }
    fun newPair() {
        if(state.value.playing)return
        pair=blindPair(records.filter { it.getString("case_id")==cases[state.value.caseIndex].id && it.getString("condition")==state.value.blindCondition }).orEmpty(); if(pair.isEmpty()) { mutable.update { it.copy(error="같은 문장·조건·seed·플랫폼의 서로 다른 모델 샘플 2개가 필요합니다.") };return }
        trialId=UUID.randomUUID().toString()
        mutable.update { it.copy(hasPair=true,revealed=false,error=null,pairText=pair[0].getString("text"),notes="",scores=List(2){List(6){0}}) }
        saveTrial()
    }
    fun score(side:Int,dimension:Int,value:Int) { if(side !in 0..1 || dimension !in 0..5 || value !in 1..5 || !state.value.hasPair)return
        mutable.update { s -> s.copy(scores=s.scores.mapIndexed { i,row -> if(i!=side)row else row.mapIndexed { j,n -> if(j==dimension)value else n } }) };saveTrial()
    }
    fun notes(value: String) { mutable.update { it.copy(notes=value.take(2000)) };saveTrial() }
    fun reveal() { mutable.update { it.copy(revealed=true) };saveTrial() }
    fun identity(index:Int) = pair.getOrNull(index)?.let { "${it.getString("model_id")} · ${it.getString("platform")}" }.orEmpty()
    fun auxiliary(index: Int): String {
        val aux = pair.getOrNull(index)?.optJSONObject("asr_auxiliary")?.optJSONObject("measurement") ?: return "보조 CER 미측정"
        val value = aux.optDouble("cer")
        return if(value.isFinite() && value >= 0) "보조 CER %.1f%% · ASR 오류 포함 가능".format(value*100) else "보조 CER 미측정"
    }
    private fun saveTrial() {
        if(pair.isEmpty())return
        val trial=JSONObject().put("id",trialId).put("case_id",pair[0].getString("case_id")).put("text",state.value.pairText).put("condition",pair[0].getString("condition")).put("seed",pair[0].getInt("seed")).put("platform",pair[0].getString("platform"))
            .put("revealed",state.value.revealed).put("notes",state.value.notes).put("scores",JSONArray(state.value.scores.map { JSONArray(it.map { n -> if(n==0)JSONObject.NULL else n }) }))
            .put("clip_ids",JSONArray(pair.map { it.getString("id") })).put("updated_epoch_ms",System.currentTimeMillis())
        if (state.value.revealed) trial.put("identities",JSONArray(pair.map { JSONObject().put("model_id",it.getString("model_id")).put("platform",it.getString("platform")) }))
        val rows=(0 until evaluations.length()).map { evaluations.getJSONObject(it) }.filter { it.getString("id")!=trialId }+trial
        evaluations=JSONArray(rows);persist(File(storage.root,"evaluations.json"),JSONObject().put("schema",1).put("dimensions",JSONArray(dimensions)).put("trials",evaluations))
    }
    fun export(uri:Uri,kind:String) {
        val snapshot=when(kind) {
            "wav" -> null
            "blind" -> JSONObject().put("schema",1).put("dimensions",JSONArray(dimensions)).put("trials",evaluations)
            else -> JSONObject().put("schema",1).put("clips",JSONArray(records)).put("diagnostics",JSONArray(storage.root.listFiles()?.filter { it.isFile && it.extension=="json" && (it.name.startsWith("failure-") || it.name.startsWith("cancelled-") || it.name.startsWith("batch-")) }?.mapNotNull { runCatching { JSONObject(it.readText()) }.getOrNull() }.orEmpty()))
        }
        val file=last?.let(storage::audio)
        viewModelScope.launch { runCatching { withContext(Dispatchers.IO) { getApplication<Application>().contentResolver.openOutputStream(uri,"wt")!!.use { out ->
            if(kind=="wav") checkNotNull(file).inputStream().use { it.copyTo(out) } else out.write(snapshot!!.toString(2).toByteArray())
        } } }.onSuccess { mutable.update { it.copy(status="로컬 내보내기 완료") } }.onFailure { fail(it.message ?: "내보내기 실패") } }
    }
    override fun onCleared() { engine.close();player.stop();super.onCleared() }
}
