package ai.chloe.voicelab.synthesis

internal enum class BackendProfile(val key: String, val nativeId: Int, val label: String) {
    CPU("cpu", 0, "CPU"), GPU("gpu", 1, "GPU 우선"), HYBRID("hybrid", 2, "하이브리드 분담");
    companion object {
        fun fromKey(key: String) = entries.firstOrNull { it.key == key }
            ?: throw IllegalArgumentException("알 수 없는 실행 모드: $key")
    }
}
