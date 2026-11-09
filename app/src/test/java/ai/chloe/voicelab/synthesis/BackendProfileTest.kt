package ai.chloe.voicelab.synthesis

import org.junit.Assert.*
import org.junit.Test

class BackendProfileTest {
    @Test fun profilesHaveStableWireIdsAndDistinctModes() {
        assertEquals(listOf(0, 1, 2), BackendProfile.entries.map { it.nativeId })
        BackendProfile.entries.forEach { assertEquals(it, BackendProfile.fromKey(it.key)) }
    }
    @Test(expected = IllegalArgumentException::class)
    fun unknownProfileCannotSilentlySelectCpu() { BackendProfile.fromKey("invalid") }
}
