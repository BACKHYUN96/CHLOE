package ai.chloe.voicelab.conversation
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
class TurnGuidancePolicyTest {
 private fun source(q:String,history:List<Pair<String,String>> = emptyList()):String {val a=JSONArray().put(JSONObject().put("role","system").put("content","AI"));for((r,c) in history)a.put(JSONObject().put("role",r).put("content",c));return a.put(JSONObject().put("role","user").put("content",q)).toString()}
 @Test fun listeningGetsPurposeInsteadOfCannedReply(){val s=TurnGuidancePolicy.apply(source("지금은 조언 없이 들어줄래?"));assertTrue(s.contains("경청 요청"));assertFalse(s.contains("알았어, 들어줄게"))}
 @Test fun informationalQuestionIsNotReturnedAsAnotherQuestion(){assertTrue(TurnGuidancePolicy.apply(source("모르는 정보는 어떻게 대답해야 해?")).contains("답변 방식을 설명"))}
 @Test fun birthdayUserSourceIsNotRewritten(){val s=source("내 생일 기억해?",listOf("user" to "내 생일은 3월 8일이야.","assistant" to "내 생일은 4월 9일이야."));val before=JSONArray(s);val after=JSONArray(TurnGuidancePolicy.apply(s));for(i in 1 until before.length())assertEquals(before.getJSONObject(i).toString(),after.getJSONObject(i).toString());assertTrue(after.getJSONObject(0).getString("content").contains("assistant의 추측"))}
 @Test fun appOwnerNameIsNotPromotedToUserName(){val s=TurnGuidancePolicy.apply(source("내가 만든 앱 이름은 별빛이야."));assertTrue(s.contains("사용자 호칭"));assertTrue(s.contains("제작자라고 명시한 주체만"))}
 @Test fun aiExperienceDoesNotChangeUserFacts(){assertTrue(TurnGuidancePolicy.apply(source("나는 네 선생님이야. 오늘 뭐 했어?")).contains("실제 하루"))}
 @Test fun thirdPartyExperienceIsNotAiExperience(){val s=source("친구는 오늘 뭐 했어?");assertEquals(s,TurnGuidancePolicy.apply(s))}
 @Test fun noChangeForUnrelatedDefinitionOrToolRequest(){for(q in listOf("RTF가 뭐야?","오늘 날씨 알려줘","도와줘")){val s=source(q);assertEquals(s,TurnGuidancePolicy.apply(s))}}
 @Test fun quoteTranslationIsNotListeningIntent(){val s=source("‘조언 없이 들어줘’라는 문장을 번역해줘");assertEquals(s,TurnGuidancePolicy.apply(s))}
 @Test fun hypotheticalOwnerIsNotCurrentFact(){val s=source("가정: 내가 만든 앱 이름은 별빛이야.");assertEquals(s,TurnGuidancePolicy.apply(s))}
 @Test fun candidateGuidanceIsNotEnabledInFinalManager(){val m=ConversationManager();val p=m.prompt("내 생일 기억해?",false);assertFalse(p.contains("이번 답변 작성 지침"));assertEquals(ConversationActPolicy.VERSION,ConversationEvaluator().structural(DirectedReply("답")).getString("conversation_act_version"))}
}
