package ai.chloe.voicelab.synthesis

/** Loaded exclusively inside :voice. Native aborts cannot take down the UI process. */
internal class NativeBridge {
    init { System.loadLibrary("chloe_voice") }
    external fun initialize(directory: String, talkerFile: String, hiddenSize: Int, logPath: String): String
    external fun synthesize(utf8Text: ByteArray, wavPath: String, instruction: ByteArray): DoubleArray
    external fun release()
}
