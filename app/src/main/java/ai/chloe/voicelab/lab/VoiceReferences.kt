package ai.chloe.voicelab.lab

import org.json.JSONObject

internal data class VoiceReference(
    val id: String, val label: String, val text: String, val instruction: String,
    val feedback: String, val sourceStudy: String, val wavSha256: String,
)

/** Preserves reviewed instructions; does not feed reference PCM into CustomVoice. */
internal fun voiceReferences(json: String): List<VoiceReference> {
    val root = JSONObject(json)
    require(root.getInt("schema") == 1)
    val refs = root.getJSONArray("references")
    val rejected = root.getJSONArray("rejected").let { rows -> (0 until rows.length()).map { rows.getString(it) }.toSet() }
    return (0 until refs.length()).map { refs.getJSONObject(it) }.filter { it.getBoolean("selectable") }.map {
        require(it.getString("status") in setOf("approved", "approved_with_notes"))
        val id = it.getString("id")
        require(id !in rejected)
        val text = it.getString("text"); val instruction = it.getString("instruction")
        require(text.codePointCount(0, text.length) in 1..240 && instruction.codePointCount(0, instruction.length) in 1..240)
        VoiceReference(id, it.getString("label"), text, instruction, it.getString("feedback"),
            it.getString("source_study"), it.getString("wav_sha256"))
    }.also { require(it.map { row -> row.id }.distinct().size == it.size) }
}
