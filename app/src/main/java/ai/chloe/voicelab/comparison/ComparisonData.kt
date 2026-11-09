package ai.chloe.voicelab.comparison

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.SecureRandom

internal const val CUSTOM = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
internal const val DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
internal val comparisonModels = listOf(CUSTOM, DESIGN, "openbmb/VoxCPM2", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
internal val dimensions = listOf("한국어 발음", "한국인다운 억양·종결", "일상 대화 자연스러움", "감정 적절성", "여성 음색 자연스러움", "안정성·일관성")
internal const val COMMON_STYLE = "친한 친구와 대화하듯 편안하고 다정하게 말해 주세요. 감정을 과장하지 말고 문장 흐름을 자연스럽게 유지해 주세요. 매 문장 앞에 과장된 들숨을 반복하지 마세요."
internal const val DESIGN_VOICE = "자연스러운 한국어를 구사하는 성인 여성의 따뜻하고 맑은 목소리. 특정 인물을 모방하지 않는 편안한 중간 음역. "
internal data class TestCase(val id: String, val group: String, val text: String)
internal fun testCases(json: String): List<TestCase> {
    val rows = JSONObject(json).getJSONArray("cases")
    return (0 until rows.length()).map { val r = rows.getJSONObject(it); TestCase(r.getString("id"), r.getString("group"), r.getString("text")) }
        .also { require(it.size == 20 && it.map { r -> r.id }.distinct().size == 20) }
}
internal fun safeName(value: String): String { require(value.matches(Regex("[A-Za-z0-9_.-]{1,100}")) && value != "." && value != ".."); return value }
internal fun validateClip(row: JSONObject, cases: List<TestCase>) {
    require(row.getString("model_id") in comparisonModels)
    val c = cases.single { it.id == row.getString("case_id") }
    require(row.getString("text") == c.text)
    require(row.getString("condition") in setOf("controlled", "optimized"))
    require(row.get("seed") is Int || row.get("seed") is Long)
    require(row.getLong("seed") in 0..Int.MAX_VALUE.toLong())
    require(row.getString("platform") in setOf("android", "linux-host", "windows-host", "macos-host"))
    require(row.getString("instruction").codePointCount(0, row.getString("instruction").length) <= 500)
}
internal fun eligiblePairs(clips: List<JSONObject>): List<Pair<JSONObject, JSONObject>> = clips.flatMapIndexed { i, a ->
    clips.drop(i + 1).filter { b -> a.getString("model_id") != b.getString("model_id") &&
        a.getString("case_id") == b.getString("case_id") && a.getString("condition") == b.getString("condition") &&
        a.getInt("seed") == b.getInt("seed") && a.getString("platform") == b.getString("platform") }
        .map { a to it }
}
internal fun blindPair(clips: List<JSONObject>): List<JSONObject>? {
    val pairs = eligiblePairs(clips); if (pairs.isEmpty()) return null
    val random = SecureRandom(); val pair = pairs[random.nextInt(pairs.size)]
    return if (random.nextBoolean()) listOf(pair.first, pair.second) else listOf(pair.second, pair.first)
}
internal fun atomicJson(file: File, value: JSONObject) {
    file.parentFile!!.mkdirs(); val pending = File(file.path + ".tmp")
    pending.writeText(value.toString(2)); check(pending.renameTo(file)) { "JSON 원자 저장 실패" }
}
