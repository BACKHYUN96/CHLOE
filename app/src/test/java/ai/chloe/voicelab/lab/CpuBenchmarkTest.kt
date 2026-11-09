package ai.chloe.voicelab.lab

import org.junit.Assert.*
import org.junit.Test

class CpuBenchmarkTest {
    @Test fun candidatesRespectVisibleCpuLimitAndDeduplicate() {
        assertEquals(listOf(2, 4, 6), CpuThreads.sweep(8))
        assertEquals(listOf(2, 4), CpuThreads.sweep(4))
        assertEquals(listOf(1), CpuThreads.sweep(0))
        assertFalse(CpuThreads.valid(0, 8)); assertFalse(CpuThreads.valid(9, 8))
    }
    @Test fun twoRoundsReverseOrderAndHaveExactlyOneWarmup() {
        val tickets = cpuTickets(8)
        assertEquals(7, tickets.size)
        assertEquals(1, tickets.count { it.warmup })
        assertEquals(listOf(2, 4, 6), tickets.filter { it.round == 1 }.map { it.threads })
        assertEquals(listOf(6, 4, 2), tickets.filter { it.round == 2 }.map { it.threads })
    }
    @Test fun summaryExcludesWarmupAndInvalidDurations() {
        val result = cpuSummaries(listOf(
            CpuObservation(4, 9999.0, 2.0, 48000, true),
            CpuObservation(4, 4000.0, 2.0, 48000, false),
            CpuObservation(4, 2000.0, 2.0, 48000, false),
            CpuObservation(4, Double.NaN, 2.0, 48000, false),
            CpuObservation(4, 1000.0, 0.0, 0, false)))
        assertEquals(1, result.size); assertEquals(2, result.single().count)
        assertEquals(3000.0, result.single().medianMs, 0.001)
        assertEquals(2000.0, result.single().bestMs, 0.001)
        assertEquals(1.5, result.single().medianRtf, 0.001)
    }
}
