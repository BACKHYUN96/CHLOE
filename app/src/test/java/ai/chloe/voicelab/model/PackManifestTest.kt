package ai.chloe.voicelab.model

import ai.chloe.voicelab.synthesis.VoiceProtocol
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PackManifestTest {
    private fun manifest() = JSONObject().put("schema", 1)
        .put("model_id", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
        .put("tokenizer_id", "Qwen/Qwen3-TTS-Tokenizer-12Hz")
        .put("runtime_commit", VoiceProtocol.RUNTIME_COMMIT).put("precision", "f16-f32-cp-down")
        .put("model_revision", "a".repeat(40)).put("tokenizer_revision", "b".repeat(40))
        .put("files", JSONArray(listOf(VoiceProtocol.TALKER, VoiceProtocol.TOKENIZER).map {
            JSONObject().put("name", it).put("size", 1_000_000).put("sha256", "a".repeat(64))
        }))
    @Test fun acceptsExpectedPair() { assertEquals(2, PackManifest.parse(manifest().toString()).files.size) }
    @Test fun rejectsBaseEvenWithCorrectFilenames() {
        assertThrows(IllegalArgumentException::class.java) {
            PackManifest.parse(manifest().put("model_id", "Qwen/Qwen3-TTS-12Hz-0.6B-Base").toString())
        }
    }
    @Test fun rejectsTheUnstablePureF16Package() {
        assertThrows(IllegalArgumentException::class.java) {
            PackManifest.parse(manifest().put("precision", "f16").toString())
        }
    }
    @Test fun rejectsTraversalAndDuplicatedFiles() {
        val doc = manifest()
        doc.getJSONArray("files").getJSONObject(0).put("name", "../../escape.gguf")
        assertThrows(IllegalArgumentException::class.java) { PackManifest.parse(doc.toString()) }
        doc.getJSONArray("files").getJSONObject(0).put("name", VoiceProtocol.TOKENIZER)
        assertThrows(IllegalArgumentException::class.java) { PackManifest.parse(doc.toString()) }
    }
    @Test fun rejectsUnboundedSizeAndMissingIntegrity() {
        val doc = manifest()
        doc.getJSONArray("files").getJSONObject(0).put("size", Long.MAX_VALUE)
        assertThrows(IllegalArgumentException::class.java) { PackManifest.parse(doc.toString()) }
        doc.getJSONArray("files").getJSONObject(0).put("size", 1_000_000).put("sha256", "")
        assertThrows(IllegalArgumentException::class.java) { PackManifest.parse(doc.toString()) }
    }
}
