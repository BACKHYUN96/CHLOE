package ai.chloe.voicelab.comparison

import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ComparisonWavTest {
    private fun wav(rate:Int, channels:Int=1, truncate:Boolean=false):File {
        val b=ByteBuffer.allocate(48).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray()).putInt(40).put("WAVEfmt ".toByteArray()).putInt(16)
            .putShort(1).putShort(channels.toShort()).putInt(rate).putInt(rate*2*channels).putShort((2*channels).toShort()).putShort(16)
            .put("data".toByteArray()).putInt(4).putShort(1).putShort(2)
        return File.createTempFile("chloe-comparison-", ".wav").apply { writeBytes(if(truncate)b.array().copyOf(46) else b.array());deleteOnExit() }
    }
    @Test fun nativeRatesAreAcceptedWithoutResampling() { listOf(16000,24000,48000).forEach { validateWav(wav(it)) } }
    @Test(expected=IllegalArgumentException::class) fun stereoIsRejected() { validateWav(wav(24000,channels=2)) }
    @Test(expected=IllegalArgumentException::class) fun truncatedPcmIsRejected() { validateWav(wav(24000,truncate=true)) }
}
