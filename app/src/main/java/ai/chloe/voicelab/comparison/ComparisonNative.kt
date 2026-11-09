package ai.chloe.voicelab.comparison

internal class ComparisonNative {
    init { System.loadLibrary("chloe_voice") }
    external fun initialize(directory: String, talker: String, design: Boolean): String
    external fun generate(text: ByteArray, instruction: ByteArray, seed: Int, path: String): DoubleArray
}
