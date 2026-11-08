package ai.chloe.voicelab.model

internal enum class ModelSpec(val key: String, val label: String, val hiddenSize: Int) {
    SMALL("0.6b", "0.6B", 1024), LARGE("1.7b", "1.7B", 2048);

    val modelId get() = "Qwen/Qwen3-TTS-12Hz-$label-CustomVoice"
    val talkerFile get() = "qwen-talker-$key-customvoice-f16-stable.gguf"
    val supportsInstruction get() = this == LARGE

    companion object {
        fun fromKey(key: String): ModelSpec = entries.singleOrNull { it.key == key }
            ?: throw IllegalArgumentException("지원하지 않는 모델: $key")
        fun fromModelId(id: String): ModelSpec = entries.singleOrNull { it.modelId == id }
            ?: throw IllegalArgumentException("0.6B 또는 1.7B CustomVoice 패키지가 필요합니다. Base는 지원하지 않습니다.")
    }
}
