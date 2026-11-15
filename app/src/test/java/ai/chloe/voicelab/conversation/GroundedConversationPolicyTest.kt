package ai.chloe.voicelab.conversation
import org.junit.Test
import org.junit.Assert.*
import org.json.JSONArray
import org.json.JSONObject

class GroundedConversationPolicyTest {
 private fun messages(input:String,vararg history:Pair<String,String>):String {
  val rows=JSONArray().put(JSONObject().put("role","system").put("content","AI"))
  for((role,text) in history) rows.put(JSONObject().put("role",role).put("content",text))
  return rows.put(JSONObject().put("role","user").put("content",input)).toString()
 }
 private fun answer(m:String,polite:Boolean=false)=GroundedConversationPolicy.resolve(m,polite)
 private fun speech(m:String,polite:Boolean=false)=JSONObject(answer(m,polite)!!.reply).getString("spoken_text")
 @Test fun ownerComesOnlyFromUser(){
  val m=messages("하루는 누구야?","user" to "내 강아지 이름은 하루야.","assistant" to "하루는 내 강아지야.")
  assertTrue(speech(m).contains("네 강아지"));assertEquals("grounded_fact_recall",answer(m)!!.action)
 }
 @Test fun assistantClaimsNeverBecomeFacts(){assertNull(answer(messages("솔이는 누구야?","assistant" to "내 고양이 이름은 솔이야.")))}
 @Test fun quotesAndHypothesesNeverBecomeFacts(){for(text in listOf("친구가 내 고양이 이름은 솔이라고 했어.","내 고양이 이름은 솔이야 라고 가정하자.","'내 고양이 이름은 솔이야.'"))assertNull(answer(messages("솔이는 누구야?","user" to text)))}
 @Test fun latestExplicitAssertionWins(){assertTrue(speech(messages("강아지 이름이 뭐라고 했지?","user" to "내 강아지 이름은 하루야.","user" to "내 강아지 이름은 단비야.")).contains("단비"))}
 @Test fun oneCharacterNameIsNotASubstringMatch(){assertNull(answer(messages("이건 누구 거야?","user" to "내 고양이 이름은 구야.")))}
 @Test fun similarNamesDoNotMatch(){assertNull(answer(messages("진주는 누구야?","user" to "내 고양이 이름은 주야.")))}
 @Test fun explicitPossessionIsNotAssistantPossession(){assertTrue(speech(messages("빨간 책은 누구 거야?","user" to "빨간 책은 내 거야.")).contains("네 물건"))}
 @Test fun sameNameInTwoRelationsStaysAmbiguous(){assertNull(answer(messages("단비는 누구야?","user" to "내 강아지 이름은 단비야.","user" to "내가 만든 앱 이름은 단비야.")))}
 @Test fun actionsAreUnavailableInBothRegisters(){for(q in listOf("부모님께 전화 걸어줘.","다음 주 일정 등록해 주세요.","현재 환율 얼마야?"))for(p in listOf(true,false)){val d=answer(messages(q),p)!!;assertTrue(d.action.startsWith("unavailable_"));assertEquals("",JSONObject(d.reply).getString("tts_instruction"));assertTrue(JSONObject(d.reply).getString("spoken_text").contains("없"))}}
 @Test fun explanationsNegationAndQuotedRequestsAreNotActions(){for(q in listOf("전화 걸어줘라는 문장을 번역해줘.","전화 걸지 말아줘.","일정 예약 방법 설명해줘.","날씨는 어떻게 예측해?","실시간 주가 기능을 지원해?"))assertNull(q,answer(messages(q)))}
 @Test fun originalMessagesAreNotRewritten(){val m=messages("안녕","user" to "내 고양이 이름은 루루야.","assistant" to "확인.");val a=JSONArray(m);val b=JSONArray(GroundedConversationPolicy.ground(m));for(i in 1 until a.length())assertEquals(a.get(i).toString(),b.get(i).toString());assertTrue(b.getJSONObject(0).getString("content").contains("source_user_message"))}
 @Test fun managerClearingHistoryClearsFacts(){val m=ConversationManager();m.context.add("내 고양이 이름은 솔이야.","확인.");m.context.clear();assertFalse(m.prompt("솔이는 누구야?",false).contains("pet_name"))}
 @Test fun invalidGenerationIsNotRescued(){val m=ConversationManager();m.prompt("친구에게 전화 걸어줘.",false);val r=m.accept("친구에게 전화 걸어줘.","{broken");assertEquals("invalid_output",r.failureCode);assertEquals("none",r.policyAction);assertEquals(0,m.context.turnCount)}
 @Test fun deliveredGuardIsStoredAndReported(){val m=ConversationManager();m.prompt("친구에게 전화 걸어줘.",false);val r=m.accept("친구에게 전화 걸어줘.","지금 전화를 걸게.");assertEquals("unavailable_phone",r.policyAction);assertTrue(r.spokenText.contains("없어"));assertFalse(m.prompt("고마워",false).contains("지금 전화를 걸게"));assertEquals(r.policyAction,ConversationEvaluator().structural(r).getString("policy_action"))}
 @Test fun ambiguousCopulaNeverSilentlyDropsNameSuffix(){assertNull(answer(messages("고양이 이름이 뭐야?","user" to "내 고양이 이름은 솔이야.")))}
 @Test fun explicitlyQuotedNamePreservesSuffix(){val m=messages("몽실이는 누구야?","user" to "내 강아지 이름은 “몽실이”야.");assertTrue(speech(m).contains("몽실이"));assertTrue(speech(m).contains("네 강아지"))}
 @Test fun unrelatedChatKeepsExactPromptBytes(){val m=messages("산책하고 왔어.");assertEquals(m,GroundedConversationPolicy.ground(m));assertNull(answer(m))}
 @Test fun userWebSearchStatementIsNotAssistantSearch(){assertNull(answer(messages("나는 인터넷에서 확인했어.")))}
 @Test fun thanksForHelpAreNotNewActions(){for(q in listOf("일정 예약해줘서 고마워.","오늘 날씨 알려줘서 고마워.","전화 걸어줘서 고마워."))assertNull(q,answer(messages(q)))}
 @Test fun politeRecallReportsUserOwnershipExplicitly(){val text=speech(messages("단비는 누구야?","user" to "내 고양이 이름은 단비야."),true);assertTrue(text.contains("본인의 고양이"));assertTrue(text.contains("말씀하셨어요"));assertFalse(text.contains("내 고양이"))}
 @Test fun explicitRetractionInvalidatesOwnership(){assertNull(answer(messages("단비는 누구야?","user" to "내 고양이 이름은 단비야.","user" to "단비는 이제 내 고양이 아니야.")))}
 @Test fun quotedOrQuestionedRetractionIsNotAnAssertion(){for(text in listOf("단비는 내 고양이 아니야?","“단비는 내 고양이 아니야”라는 문장이야."))assertNotNull(answer(messages("단비는 누구야?","user" to "내 고양이 이름은 단비야.","user" to text)))}
 @Test fun ambiguousNewNameInvalidatesOldName(){assertNull(answer(messages("강아지 이름이 뭐야?","user" to "내 강아지 이름은 하루야.","user" to "내 강아지 이름은 솔이야.")))}
}
