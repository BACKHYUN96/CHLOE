package ai.chloe.voicelab.comparison

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class ComparisonDataTest {
    private val cases = testCases(File("src/main/assets/tts-comparison-cases.json").readText())
    private fun clip(model:String=CUSTOM, case:String="ko01", condition:String="controlled", seed:Int=42, platform:String="android") =
        JSONObject().put("model_id",model).put("case_id",case).put("text",cases.single { it.id==case }.text)
            .put("condition",condition).put("seed",seed).put("platform",platform).put("instruction",COMMON_STYLE)
    @Test fun commonSetContainsTwentyOriginalCases() {
        assertEquals(20,cases.size)
        assertEquals("십육 개 중에서 세 개만 골라 주세요.",cases[14].text)
        assertEquals("네, 알겠어요. 그럼 이따 다시 이야기해요.",cases.last().text)
    }
    @Test fun blindPairNeverMixesDifferentCasesConditionsSeedsOrPlatforms() {
        val a=clip();val b=clip(DESIGN)
        assertEquals(1,eligiblePairs(listOf(a,b)).size)
        listOf(clip(DESIGN,case="ko02"),clip(DESIGN,condition="optimized"),clip(DESIGN,seed=43),clip(DESIGN,platform="linux-host"),clip()).forEach {
            assertTrue(eligiblePairs(listOf(a,it)).isEmpty())
        }
        assertEquals(setOf(CUSTOM,DESIGN),blindPair(listOf(a,b))!!.map { it.getString("model_id") }.toSet())
    }
    @Test(expected=IllegalArgumentException::class) fun fractionalSeedCannotBeSilentlyTruncated() { validateClip(clip().put("seed",42.9),cases) }
    @Test(expected=IllegalArgumentException::class) fun traversalIsRejected() { safeName("../audio.wav") }
    @Test(expected=IllegalArgumentException::class) fun unknownModelIsRejected() { validateClip(clip("fake-model"),cases) }
    @Test(expected=IllegalArgumentException::class) fun changedTestTextIsRejected() { validateClip(clip().put("text","다른 문장"),cases) }
}
