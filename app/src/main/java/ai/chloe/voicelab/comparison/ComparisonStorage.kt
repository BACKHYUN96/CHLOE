package ai.chloe.voicelab.comparison

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

internal class ComparisonStorage(private val context: Context) {
    val root = File(context.filesDir, "tts-comparison").apply { mkdirs() }
    val clips = File(root, "clips").apply { mkdirs() }
    val design = File(root, "design")
    private fun read(doc: DocumentFile, limit: Int): String = context.contentResolver.openInputStream(doc.uri)!!.use {
        val data = it.readBounded(limit + 1); require(data.size <= limit); data.toString(Charsets.UTF_8)
    }
    fun records(): List<JSONObject> = clips.listFiles()?.filter { it.extension == "json" }?.mapNotNull { runCatching { JSONObject(it.readText()) }.getOrNull() }.orEmpty()
    private fun copy(doc: DocumentFile, dest: File, expected: String, cap: Long) {
        require(expected.matches(Regex("[0-9a-f]{64}")))
        val hash = MessageDigest.getInstance("SHA-256"); var total = 0L
        context.contentResolver.openInputStream(doc.uri)!!.use { source -> dest.outputStream().use { target ->
            val b = ByteArray(1024 * 1024)
            while (true) { check(!Thread.currentThread().isInterrupted); val n = source.read(b); if (n < 0) break; total += n; require(total <= cap); hash.update(b, 0, n); target.write(b, 0, n) }
        } }
        require(hash.digest().joinToString("") { "%02x".format(it) } == expected) { "파일 SHA-256 불일치" }
    }
    fun importSamples(uri: Uri, cases: List<TestCase>): Int {
        val tree = DocumentFile.fromTreeUri(context, uri) ?: error("폴더 열기 실패")
        val manifest = JSONObject(read(tree.findFile("comparison-manifest.json") ?: error("comparison-manifest.json 필요"), 4_000_000))
        require(manifest.getInt("schema") == 1)
        val rows = manifest.getJSONArray("clips"); require(rows.length() in 1..500)
        val stage = File(root, "import-${UUID.randomUUID()}").apply { mkdirs() }
        var total = 0L
        try {
            for (i in 0 until rows.length()) {
                val row = JSONObject(rows.getJSONObject(i).toString()); validateClip(row, cases)
                val name = safeName(row.getString("file")); require(name.endsWith(".wav"))
                val id = UUID.randomUUID().toString(); val wav = File(stage, "$id.wav")
                copy(tree.findFile(name) ?: error("WAV 없음: $name"), wav, row.getString("wav_sha256"), 20_000_000)
                total += wav.length(); require(total <= 400_000_000)
                validateWav(wav)
                row.put("id", id).put("file", wav.name).put("imported", true)
                File(stage, "$id.json").writeText(row.toString(2))
            }
            // Single directory rename publishes all imported clips together.
            val pack = File(clips, "pack-${UUID.randomUUID()}")
            check(stage.renameTo(pack)); return rows.length()
        } finally { stage.deleteRecursively() }
    }
    fun allRecords(): List<JSONObject> = records() + clips.listFiles()?.filter { it.isDirectory }?.flatMap { dir -> dir.listFiles()?.filter { it.extension == "json" }?.mapNotNull { f -> runCatching { JSONObject(f.readText()).put("pack", dir.name) }.getOrNull() }.orEmpty() }.orEmpty()
    fun audio(row: JSONObject) = if (row.has("pack")) File(File(clips, safeName(row.getString("pack"))), safeName(row.getString("file"))) else File(clips, safeName(row.getString("file")))
    fun importDesign(uri: Uri) {
        require(!design.exists()) { "VoiceDesign 모델이 이미 있습니다. 기존 모델은 덮어쓰지 않습니다." }
        val tree = DocumentFile.fromTreeUri(context, uri) ?: error("폴더 열기 실패")
        val m = JSONObject(read(tree.findFile("design-pack.json") ?: error("design-pack.json 필요"), 100_000))
        require(m.getString("model_id") == DESIGN && m.getString("runtime_commit") == "4562731dc612cb87b4cd1eedac275a17d1078773")
        require(m.getString("precision") == "f16-f32-cp-down")
        val files = m.getJSONArray("files"); require(files.length() == 2)
        val names = (0 until 2).map { files.getJSONObject(it).getString("name") }.toSet()
        require(names == setOf("qwen-talker-1.7b-voicedesign-f16-stable.gguf", "qwen-tokenizer-12hz-f16.gguf"))
        val stage = File(root, "design-${UUID.randomUUID()}").apply { mkdirs() }
        try { for (i in 0 until 2) { val r = files.getJSONObject(i); val name = r.getString("name"); val size = r.getLong("size"); require(size in 1..5_000_000_000L)
            copy(tree.findFile(name) ?: error("모델 파일 없음"), File(stage, name), r.getString("sha256"), size); require(File(stage, name).length() == size) }
            File(stage, "design-pack.json").writeText(m.toString(2)); check(stage.renameTo(design))
        } finally { stage.deleteRecursively() }
    }
}
// Imported samples intentionally accept canonical mono PCM16 WAV, not arbitrary codecs.
internal fun validateWav(file: File) {
    file.inputStream().use { input ->
        val h = input.readBounded(44); require(h.size == 44)
        fun s(a: Int, n: Int) = String(h, a, n, Charsets.US_ASCII)
        fun u16(a: Int) = (h[a].toInt() and 255) or ((h[a+1].toInt() and 255) shl 8)
        fun u32(a: Int) = (0..3).sumOf { (h[a+it].toLong() and 255) shl (8*it) }
        require(s(0,4)=="RIFF" && s(8,4)=="WAVE" && s(12,4)=="fmt " && u32(16)==16L && s(36,4)=="data")
        require(u16(20)==1 && u16(22)==1 && u16(34)==16 && u32(24) in setOf(16000L,24000L,48000L))
        require(u32(4)+8==file.length() && u32(28)==u32(24)*2 && u16(32)==2)
        require(u32(40)>0 && u32(40)%2==0L && u32(40)+44==file.length())
    }
}

private fun InputStream.readBounded(maximum: Int): ByteArray {
    val result = java.io.ByteArrayOutputStream(); val buffer = ByteArray(minOf(maximum, 8192)); var left = maximum
    while (left > 0) { val n = read(buffer, 0, minOf(left, buffer.size)); if (n < 0) break; result.write(buffer, 0, n); left -= n }
    return result.toByteArray()
}
