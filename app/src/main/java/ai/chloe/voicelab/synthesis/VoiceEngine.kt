package ai.chloe.voicelab.synthesis

/** Transport boundary for the later conversation layer. No remote implementation in alpha1. */
interface VoiceEngine : AutoCloseable {
    fun initialize()
    fun synthesize(text: String, outputPath: String)
    fun stop()
}

internal object VoiceProtocol {
    const val INIT = 1
    const val GENERATE = 2
    const val STOP = 3
    const val EVENT = 4
    const val RUNTIME_COMMIT = "4562731dc612cb87b4cd1eedac275a17d1078773"
    const val TALKER = "qwen-talker-0.6b-customvoice-f16-stable.gguf"
    const val TOKENIZER = "qwen-tokenizer-12hz-f16.gguf"
}
