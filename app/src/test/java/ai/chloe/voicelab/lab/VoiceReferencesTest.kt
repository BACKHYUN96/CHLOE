package ai.chloe.voicelab.lab

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class VoiceReferencesTest {
    private val catalog = File("src/main/assets/voice-reference-catalog.json").readText()
    @Test fun onlyReviewedUsableReferencesAreSelectable() {
        assertEquals(setOf("surprise_01_A", "surprise_01_B", "surprise_01_C", "surprise_02_A", "explanation_03_A"),
            voiceReferences(catalog).map { it.id }.toSet())
        assertFalse(voiceReferences(catalog).any { it.id == "surprise_03_D" || it.id == "daily_03_A" })
    }
    @Test fun selectableInstructionsAndHashesMatchOriginalGenerationRecords() {
        voiceReferences(catalog).forEach { ref ->
            val filename = if (ref.sourceStudy.endsWith("01")) "results.json" else "report.json"
            val report = JSONObject(File("../docs/validation/${ref.sourceStudy}/$filename").readText())
            val clips = report.getJSONArray("clips")
            val clip = (0 until clips.length()).map { clips.getJSONObject(it) }.single { it.getString("clip_id") == ref.id }
            val cases = report.getJSONArray("cases")
            val case = (0 until cases.length()).map { cases.getJSONObject(it) }.single { it.getString("id") == clip.getString("case_id") }
            assertEquals(clip.getString("wav_sha256"), ref.wavSha256)
            assertEquals(case.getString("text"), ref.text)
            assertEquals(case.getJSONObject("instructions").getString(clip.getString("style")), ref.instruction)
        }
    }
    @Test(expected = IllegalArgumentException::class)
    fun rejectionCannotBePromotedToSelectablePreset() {
        val root = JSONObject(catalog)
        root.getJSONArray("rejected").put("surprise_01_A")
        voiceReferences(root.toString())
    }
}
