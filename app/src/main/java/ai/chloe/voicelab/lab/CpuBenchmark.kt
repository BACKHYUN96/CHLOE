package ai.chloe.voicelab.lab

internal object CpuThreads {
    fun limit(available: Int) = available.coerceIn(1, 32)
    fun choices(available: Int) = (1..limit(available)).toList()
    fun sweep(available: Int) = (listOf(2, 4, 6, 8) + limit(available)).filter { it <= limit(available) }.distinct().sorted()
    fun valid(value: Int, available: Int) = value in 1..limit(available)
}

internal data class CpuTicket(val threads: Int, val round: Int, val warmup: Boolean = false)
internal data class CpuObservation(val threads: Int, val generationMs: Double, val seconds: Double, val samples: Long, val warmup: Boolean)
internal data class CpuSummary(val threads: Int, val count: Int, val medianMs: Double, val bestMs: Double, val medianRtf: Double)

internal fun cpuSummaries(runs: List<CpuObservation>): List<CpuSummary> {
    fun median(values: List<Double>): Double {
        val sorted = values.sorted(); val middle = sorted.size / 2
        return if (sorted.size % 2 == 0) (sorted[middle - 1] + sorted[middle]) / 2 else sorted[middle]
    }
    return runs.filter { !it.warmup && it.generationMs.isFinite() && it.generationMs > 0 && it.seconds.isFinite() && it.seconds > 0 }
        .groupBy { it.threads }.map { (threads, rows) ->
            CpuSummary(threads, rows.size, median(rows.map { it.generationMs }), rows.minOf { it.generationMs },
                median(rows.map { it.generationMs / (it.seconds * 1000) }))
        }.sortedBy { it.threads }
}

internal fun cpuTickets(available: Int): List<CpuTicket> {
    val candidates = CpuThreads.sweep(available)
    // Warm once, then reverse the second round to reduce a fixed order advantage.
    return listOf(CpuTicket(4.coerceAtMost(CpuThreads.limit(available)), 0, true)) +
        candidates.map { CpuTicket(it, 1) } + candidates.reversed().map { CpuTicket(it, 2) }
}
