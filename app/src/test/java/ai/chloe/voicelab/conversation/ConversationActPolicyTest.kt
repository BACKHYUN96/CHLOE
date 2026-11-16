package ai.chloe.voicelab.conversation
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
class ConversationActPolicyTest {
 private fun source(q:String,history:List<Pair<String,String>> = emptyList(),system:String="AI"):String {val a=JSONArray().put(JSONObject().put("role","system").put("content",system));for((r,c) in history)a.put(JSONObject().put("role",r).put("content",c));return a.put(JSONObject().put("role","user").put("content",q)).toString()}
 private fun act(q:String,polite:Boolean=false)=ConversationActPolicy.resolve(source(q),polite)
 @Test fun listeningAcknowledgementHasNoCounterQuestion(){val d=act("오늘은 칭찬보다 이야기를 들어줘.")!!;assertEquals("ack_listening",d.action);assertFalse(d.reply.contains("?"));assertTrue(d.reply.contains("네 이야기를"))}
 @Test fun politeListeningRemainsPolite(){val d=act("지금은 조언 없이 들어줄래?",true)!!;val r=VoiceDirector().parse(d.reply);assertFalse(r.fallback);assertTrue(r.spokenText.endsWith("들을게요."))}
 @Test fun unseenListeningWordingWithinSupportedGrammar(){assertEquals("ack_listening",act("제 얘기를 들어주세요.",true)!!.action)}
 @Test fun uncertaintyMethodDoesNotAskForAName(){val r=VoiceDirector().parse(act("모르는 내용은 어떻게 답변해야 하나요?",true)!!.reply);assertTrue(r.spokenText.contains("추측을 구분"));assertFalse(r.spokenText.contains("클로이"));assertFalse(r.spokenText.contains("?"))}
 @Test fun emptyHistoryBirthdayIsScopedToVisibleRecord(){val r=VoiceDirector().parse(act("내 생일 기억해?")!!.reply);assertTrue(r.spokenText.contains("지금 보이는 대화 기록"));assertFalse(r.spokenText.contains("언제"))}
 @Test fun priorUserBirthdayIsNotOverwrittenByAbsence(){assertNull(ConversationActPolicy.resolve(source("내 생일 기억해?",listOf("user" to "내 생일은 7월 2일이야.","assistant" to "알겠어.")),false))}
 @Test fun ambiguousDateOrAssistantBirthdayHistoryIsNotTreatedAsEmpty(){assertNull(ConversationActPolicy.resolve(source("내 생일 기억해?",listOf("assistant" to "생일이 언제야?","user" to "7월 2일")),false))}
 @Test fun birthdayProfileInSystemIsNotIgnored(){assertNull(ConversationActPolicy.resolve(source("내 생일 기억해?",system="사용자 생일은 7월 2일"),false))}
 @Test fun aiDayNeverClaimsUserDay(){val d=act("나는 네 선생님이야. 오늘 뭐 했어?")!!;assertEquals("no_lived_day",d.action);assertTrue(d.reply.contains("나는 AI라"));assertFalse(d.reply.contains("네가"))}
 @Test fun thirdPartyDayRemainsModelTask(){assertNull(act("친구는 오늘 뭐 했어?"))}
 @Test fun thirdPersonChloeMayBeUserPetOrAppNotTheAi(){for(q in listOf("클로이는 오늘 뭐 했어?","클로이는 사람처럼 슬퍼?"))assertNull(ConversationActPolicy.resolve(source(q,listOf("user" to "내 고양이 이름은 클로이야.","assistant" to "알겠어.")),false))}
 @Test fun sadnessIsAnAppCapabilityStatement(){assertEquals("no_human_sadness",act("너 정말 사람처럼 슬퍼?")!!.action)}
 @Test fun appNameIsAcknowledgedWithoutNamingUserOrInventingMaker(){for(q in listOf("내가 만든 앱 이름은 별빛이야.","내 앱 이름은 새봄이야.")){val r=VoiceDirector().parse(act(q)!!.reply);assertEquals("앱 이름을 알려줘서 고마워.",r.spokenText);assertFalse(r.spokenText.contains("만든"))}}
 @Test fun quotesNegationsHypotheticalsAreNotAcknowledgements(){for(q in listOf("‘내 얘기를 들어줘’라고 번역해줘","내 얘기를 들어줘라고 말하지 마","가정: 내 앱 이름은 별빛이야.","내 앱 이름은 별빛이 아니야."))assertNull(act(q))}
 @Test fun unrelatedQuestionsKeepNativePath(){for(q in listOf("도와줘","RTF가 뭐야?","내 고양이 이름은 뭐야?","오늘 날씨 알려줘","어떤 이야기를 들으면 좋아?"))assertNull(act(q))}
 @Test fun unusableGenerationCannotBeRescuedByAct(){val m=ConversationManager();m.prompt("내 생일 기억해?",false);val r=m.accept("내 생일 기억해?","{broken");assertEquals("invalid_output",r.failureCode);assertEquals("none",r.dialogueAction);assertEquals(0,m.context.turnCount)}
 @Test fun managerDoesNotAppendRejectedGuidanceAndStoresCleanAct(){val m=ConversationManager();val p=m.prompt("오늘은 칭찬보다 이야기를 들어줘.",false);assertFalse(p.contains("이번 답변 작성 지침"));val r=m.accept("오늘은 칭찬보다 이야기를 들어줘.","네가 뭐라고 말해? 네가 뭐라고 말해?");assertEquals("ack_listening",r.dialogueAction);assertFalse(r.fallback);assertFalse(r.spokenText.contains("?"));assertFalse(m.context.messages("AI","다음").contains("뭐라고 말해"));assertEquals("ack_listening",ConversationEvaluator().structural(r).getString("dialogue_action"))}
 @Test fun appAcknowledgementKeepsSourceFactForLaterRecall(){val m=ConversationManager();val q="내가 만든 앱 이름은 하나야.";m.prompt(q,false);assertEquals("ack_app_name",m.accept(q,"알았어.").dialogueAction);assertFalse(m.prompt("RTF가 뭐야?",false).contains("하나"));m.accept("RTF가 뭐야?","RTF는 문서 형식이야.");m.prompt("앱 이름이 뭐라고 했지?",false);val r=m.accept("앱 이름이 뭐라고 했지?","기억이 안 나.");assertTrue(r.spokenText.contains("하나"));assertEquals("grounded_fact_recall",r.policyAction);assertTrue(m.context.messages("AI","다음").contains(q))}
}
