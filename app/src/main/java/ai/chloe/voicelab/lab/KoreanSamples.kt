package ai.chloe.voicelab.lab

internal val koreanSamples = listOf(
    "안녕하세요? 저는 클로이예요.",
    "오늘 하루는 어떻게 보내셨어요?",
    "아, 진짜요? 그건 좀 신기한데요?",
    "아니, 그게 아니라 제 말은요.",
    "음... 잠깐만요. 제가 한번 생각해 볼게요.",
    "와, 그거 정말 대단하네요!",
    "오늘 많이 피곤하셨나 봐요.",
    "그러게요. 저도 그렇게 생각해요.",
    "아, 그건 조금 다르게 볼 수도 있겠네요.",
    "네, 알겠어요. 언제든 편하게 이야기해 주세요.",
)

internal fun realTimeFactor(generationMs: Double, audioSeconds: Double): Double? =
    if (generationMs.isFinite() && generationMs >= 0 && audioSeconds.isFinite() && audioSeconds > 0)
        generationMs / (audioSeconds * 1000.0) else null
