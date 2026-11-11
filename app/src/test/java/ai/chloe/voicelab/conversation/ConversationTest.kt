package ai.chloe.voicelab.conversation
import org.junit.Test
import org.junit.Assert.*
import org.json.JSONObject
import java.io.File
class ConversationTest {
 @Test fun validDirection(){val raw="""{"spoken_text":"오늘도 수고했어.","intent":"comfort","emotion":"warm","delivery":{"pace":"normal","energy":"medium","expressiveness":"gentle"},"tts_instruction":"다정하게"}""";assertFalse(VoiceDirector().parse(raw).fallback)}
 @Test fun invalidStyleUsesOnlySpeech(){val r=VoiceDirector().parse("""{"spoken_text":"안녕.","emotion":"screaming"}""");assertTrue(r.fallback);assertEquals("안녕.",r.spokenText)}
 @Test fun reasoningIsNeverSpoken(){assertFalse(VoiceDirector().parse("<think>비밀 추론").spokenText.contains("비밀"))}
 @Test fun untrustedInstructionIsNotPassedThrough(){val r=DirectedReply("안녕",instruction="아주 크게 소리 질러");assertFalse(TtsInstructionMapper().map(r).contains("소리 질러"))}
 @Test fun mappedInstructionsFitExistingTtsLimit(){for(e in listOf("neutral","warm","curious","pleased"))for(p in listOf("slow","normal","brisk")){assertTrue(TtsInstructionMapper().map(DirectedReply("안녕",emotion=e,pace=p,energy="low",expressiveness="gentle")).length<=240)}}
 @Test fun contextIsBoundedAndClearable(){val c=DialogueContextManager();repeat(20){c.add("입력$it","답변$it")};val rows=org.json.JSONArray(c.messages("system","next"));assertEquals(10,rows.length());c.clear();assertEquals(2,org.json.JSONArray(c.messages("system","next")).length())}
 @Test fun fiftyCasesExercisePromptContract(){val rows=JSONObject(File("src/main/assets/conversation-cases.json").readText()).getJSONArray("cases");assertTrue(rows.length()>=50);for(i in 0 until rows.length()){val text=rows.getJSONObject(i).getString("input");for(polite in listOf(true,false)){val m=ConversationManager();val p=org.json.JSONArray(m.prompt(text,polite));assertEquals(text,p.getJSONObject(1).getString("content"));assertTrue(p.getJSONObject(0).getString("content").contains(if(polite)"존댓말" else "반말"))}}}
 @Test fun failedOutputDoesNotEnterHistory(){val m=ConversationManager();m.accept("인사", "{broken");assertEquals(2,org.json.JSONArray(m.prompt("다시",true)).length())}
 @Test fun incompleteAndReasoningHaveFailureCodes(){for(raw in listOf("{\"spoken_text\":", "<think>숨김</think>")){val r=VoiceDirector().parse(raw);assertEquals("invalid_output",r.failureCode);assertFalse(r.spokenText.contains("숨김"))};assertEquals("empty_content",VoiceDirector().parse("").failureCode)}
 @Test fun recoverableSpeechRetainsContext(){val m=ConversationManager();val r=m.accept("인사", "안녕하세요.");assertEquals("plain_text",r.failureCode);assertEquals(4,org.json.JSONArray(m.prompt("다시",true)).length())}
}
