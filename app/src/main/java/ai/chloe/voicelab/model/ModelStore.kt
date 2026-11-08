package ai.chloe.voicelab.model

import android.content.Context
import android.net.Uri
import android.os.StatFs
import androidx.documentfile.provider.DocumentFile
import ai.chloe.voicelab.synthesis.VoiceProtocol
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.io.InputStream

private fun InputStream.readBounded(limit: Int): ByteArray {
    val buffer = ByteArray(limit)
    var offset = 0
    while (offset < limit) {
        val count = read(buffer, offset, limit - offset)
        if (count < 0) break
        offset += count
    }
    return buffer.copyOf(offset)
}

internal data class PackFile(val name: String, val size: Long, val sha256: String)

internal data class PackManifest(val json: String, val files: List<PackFile>) {
    companion object {
        fun parse(text: String): PackManifest {
            val doc = JSONObject(text)
            require(doc.getInt("schema") == 1) { "지원하지 않는 모델 패키지 버전" }
            require(doc.getString("model_id") == "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice") { "0.6B CustomVoice 패키지가 필요합니다. Base는 지원하지 않습니다." }
            require(doc.getString("tokenizer_id") == "Qwen/Qwen3-TTS-Tokenizer-12Hz")
            require(doc.getString("runtime_commit") == VoiceProtocol.RUNTIME_COMMIT) { "다른 런타임용 패키지입니다." }
            require(doc.getString("precision") == "f16-f32-cp-down") { "F32 안정화 투영이 포함된 F16 패키지가 필요합니다." }
            for (key in listOf("model_revision", "tokenizer_revision"))
                require(doc.getString(key).matches(Regex("[0-9a-f]{40}"))) { "모델 출처 리비전이 필요합니다." }
            val list = doc.getJSONArray("files")
            require(list.length() == 2) { "Talker와 음성 Tokenizer 파일 두 개가 필요합니다." }
            val files = (0 until list.length()).map { i ->
                val f = list.getJSONObject(i)
                PackFile(f.getString("name"), f.getLong("size"), f.getString("sha256"))
            }
            require(files.map { it.name }.toSet() == setOf(VoiceProtocol.TALKER, VoiceProtocol.TOKENIZER)) { "패키지 파일명이 올바르지 않습니다." }
            files.forEach {
                require(it.size in 1_000_000..6_000_000_000L) { "비정상적인 모델 크기" }
                require(it.sha256.matches(Regex("[0-9a-f]{64}"))) { "SHA-256 누락" }
            }
            require(files.sumOf { it.size } <= 8_000_000_000L) { "패키지 크기 초과" }
            return PackManifest(text, files)
        }
    }
}

internal class ModelStore(private val context: Context) {
    private val root = File(context.filesDir, "models").apply { mkdirs() }
    val active = File(root, "active")
    fun installed(): Boolean = File(active, "model-pack.json").isFile

    suspend fun import(uri: Uri, progress: (String) -> Unit) {
        val tree = DocumentFile.fromTreeUri(context, uri) ?: error("폴더를 열 수 없습니다.")
        val manifestDoc = tree.findFile("model-pack.json") ?: error("model-pack.json이 없습니다. PC 준비 스크립트를 먼저 실행하세요.")
        val text = context.contentResolver.openInputStream(manifestDoc.uri)!!.use {
            val bytes = it.readBounded(32_769)
            require(bytes.size <= 32_768) { "매니페스트 크기 초과" }
            bytes.toString(Charsets.UTF_8)
        }
        val manifest = PackManifest.parse(text)
        val required = manifest.files.sumOf { it.size }
        require(StatFs(root.path).availableBytes > required + 512_000_000L) { "내부 저장소 공간이 부족합니다." }
        val stage = File(root, "importing").apply { deleteRecursively(); mkdirs() }
        try {
            var copied = 0L
            for (file in manifest.files) {
                val source = tree.findFile(file.name) ?: error("${file.name} 파일이 없습니다.")
                val hash = MessageDigest.getInstance("SHA-256")
                var bytes = 0L
                var lastUpdate = 0L
                context.contentResolver.openInputStream(source.uri)!!.use { input ->
                    File(stage, file.name).outputStream().use { output ->
                        val buffer = ByteArray(1024 * 1024)
                        while (true) {
                            currentCoroutineContext().ensureActive()
                            val count = input.read(buffer)
                            if (count == -1) break
                            bytes += count
                            require(bytes <= file.size) { "파일이 매니페스트보다 큽니다." }
                            output.write(buffer, 0, count); hash.update(buffer, 0, count)
                            copied += count
                            if (copied - lastUpdate >= 16 * 1024 * 1024) {
                                progress("모델 복사 및 SHA-256 검사 ${(copied * 100 / required)}%")
                                lastUpdate = copied
                            }
                        }
                        output.fd.sync()
                    }
                }
                require(bytes == file.size && hash.digest().joinToString("") { "%02x".format(it) } == file.sha256) { "${file.name}: 크기 또는 SHA-256 불일치" }
                File(stage, file.name).inputStream().use {
                    require(it.readBounded(4).contentEquals("GGUF".toByteArray())) { "GGUF 파일이 아닙니다." }
                }
            }
            File(stage, "model-pack.json").writeText(text)
            val previous = File(root, "previous").apply { deleteRecursively() }
            if (active.exists()) check(active.renameTo(previous)) { "기존 모델 보관 실패" }
            if (!stage.renameTo(active)) {
                previous.renameTo(active)
                error("모델 적용 실패; 기존 모델을 복원했습니다.")
            }
            previous.deleteRecursively()
        } finally { stage.deleteRecursively() }
    }
}
