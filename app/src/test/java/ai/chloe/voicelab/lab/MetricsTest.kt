package ai.chloe.voicelab.lab

import org.junit.Assert.*
import org.junit.Test

class MetricsTest {
    @Test fun convertsMillisecondsToSecondsForRtf() {
        assertEquals(0.5, realTimeFactor(2000.0, 4.0)!!, 0.00001)
    }
    @Test fun doesNotInventNumbersForInvalidAudio() {
        assertNull(realTimeFactor(1000.0, 0.0))
        assertNull(realTimeFactor(Double.NaN, 5.0))
        assertNull(realTimeFactor(-1.0, 5.0))
    }
}
