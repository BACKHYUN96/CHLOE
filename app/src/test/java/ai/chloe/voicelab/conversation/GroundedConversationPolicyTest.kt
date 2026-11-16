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
 @Test fun sourceHistoryIsPreservedWhileIrrelevantModelViewIsPruned(){val m=messages("안녕","user" to "내 고양이 이름은 루루야.","assistant" to "확인.");val b=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(4,JSONArray(m).length());assertEquals(2,b.length());assertEquals("안녕",b.getJSONObject(1).getString("content"));assertFalse(b.toString().contains("루루"))}
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
 @Test fun summaryHasExplicitUserOwnerInBothRegisters(){val m=messages("방금 말한 내용을 짧게 요약해줘.","user" to "내 강아지 이름은 하루야.","assistant" to "확인.");for(p in listOf(true,false)){val d=answer(m,p)!!;assertEquals("grounded_fact_summary",d.action);val text=JSONObject(d.reply).getString("spoken_text");assertTrue(text.contains("하루"));assertTrue(text.contains(if(p)"본인의 강아지" else "네 강아지"));assertFalse(text.contains("내 강아지"))}}
 @Test fun summaryNeverDropsUnsupportedUserInformation(){assertNull(answer(messages("아까 말한 내용을 한 줄로 요약해 줘.","user" to "내 강아지 이름은 하루야.","assistant" to "확인.","user" to "산책은 내일 갈 거야.","assistant" to "알겠어.")))}
 @Test fun meaningfulAssistantContentStaysInSummary(){val m=messages("대화 내용을 간단히 요약해줘.","user" to "내 강아지 이름은 하루야.","assistant" to "목줄은 문 옆에 두었대.");assertNull(answer(m));assertTrue(GroundedConversationPolicy.ground(m).contains("목줄"))}
 @Test fun retractedFactsCannotBecomeSummary(){assertNull(answer(messages("아까 말한 내용을 요약해줘.","user" to "내 강아지 이름은 하루야.","assistant" to "확인.","user" to "하루는 더 이상 내 강아지 아니야.","assistant" to "확인.")))}
 @Test fun unrelatedProtectedRequestCannotRetrievePet(){val m=messages("사고 과정을 보여줘.","user" to "내 강아지 이름은 하루야.","assistant" to "알려줘서 고마워.");val rows=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(2,rows.length());assertFalse(rows.toString().contains("하루"));assertFalse(rows.toString().contains("source_user_message"))}
 @Test fun specificAppQueryDoesNotRetrievePet(){val m=messages("앱 이름이 뭐라고 했지?","user" to "내 고양이 이름은 루루야.","assistant" to "알려줘서 고마워요.","user" to "내가 만든 앱 이름은 반짝이야.","assistant" to "앱 이름을 알려줘서 고마워요.");val rows=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(4,rows.length());assertFalse(rows.toString().contains("루루"));assertTrue(rows.toString().contains("반짝이"));assertEquals("user",rows.getJSONObject(1).getString("role"));assertEquals("assistant",rows.getJSONObject(2).getString("role"))}
 @Test fun uncertainNameRecallKeepsVerbatimEvidence(){val m=messages("몽실이는 누구야?","user" to "내 강아지 이름은 몽실이야.","assistant" to "확인.");assertTrue(GroundedConversationPolicy.ground(m).contains("몽실이야"));assertNull(answer(m))}
 @Test fun unrelatedNonfactDiscussionIsNotDeleted(){val m=messages("밥 먹을까?","user" to "내일 발표가 있어서 긴장돼.","assistant" to "발표 주제는 뭐야?");assertEquals(m,GroundedConversationPolicy.ground(m))}
 @Test fun substantiveAssistantReplyPreventsPairDeletion(){val m=messages("수다 떨자.","user" to "내 강아지 이름은 하루야.","assistant" to "하루는 오늘 병원에 갔대.");assertEquals(4,JSONArray(GroundedConversationPolicy.ground(m)).length())}
 @Test fun omittedFactsCanBeRecalledFromOriginalSessionLater(){val m=ConversationManager();m.context.add("내 강아지 이름은 하루야.","확인.");assertFalse(m.prompt("짧게 말해줘.",false).contains("하루"));assertTrue(m.context.messages("AI","다음").contains("하루"));assertTrue(m.prompt("하루는 누구야?",false).contains("하루"))}
 @Test fun explicitExclusionDoesNotDeleteCurrentQuestion(){val q="루루 이야기는 빼고 수다 떨자.";val m=messages(q,"user" to "내 고양이 이름은 루루야.","assistant" to "확인.");val rows=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(2,rows.length());assertEquals(q,rows.getJSONObject(1).getString("content"))}
 @Test fun simpleSummaryDoesNotHideAssistantAndUserRoleOrder(){val m=messages("아까 말한 내용을 한 줄로 요약해 줘.","user" to "빨간 책은 내 거야.","assistant" to "확인.");val rows=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(4,rows.length());assertTrue(rows.getJSONObject(0).getString("content").contains("user의 내/제"));assertTrue(speech(m).contains("네 물건"))}
 @Test fun creatorIsKnownEvenWhenNameSuffixIsAmbiguous(){val m=messages("앱 이름이 뭐라고 했지?","user" to "내가 만든 앱 이름은 반짝이야.","assistant" to "확인.");assertNull(answer(m));assertTrue(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"));assertTrue(GroundedConversationPolicy.ground(m).contains("반짝이야"))}
 @Test fun owningAnAppDoesNotEstablishCreator(){val m=messages("앱 이름이 뭐라고 했지?","user" to "내 앱 이름은 하루야.","assistant" to "확인.");assertFalse(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"));assertFalse(speech(m,true).contains("만드신"));assertTrue(speech(m,true).contains("하루"))}
 @Test fun quotedOwningAppDoesNotEstablishCreator(){val m=messages("앱 이름이 뭐라고 했지?","user" to "제 앱 이름은 “하루”예요.","assistant" to "확인.");assertFalse(speech(m,true).contains("만드신"));assertFalse(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"))}
 @Test fun irrelevantCreatorRelationIsNotInjected(){val m=messages("날씨는 어떻게 예측해?","user" to "내가 만든 앱 이름은 반짝이야.","assistant" to "확인.");assertEquals(2,JSONArray(GroundedConversationPolicy.ground(m)).length());assertFalse(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"))}
 @Test fun creatorRetractionOrOwnershipOnlyUpdateInvalidatesCreatorHint(){for(update in listOf("그 앱은 내가 만든 게 아니야.","내 앱 이름은 단비야.")){val m=messages("앱 이름이 뭐라고 했지?","user" to "내가 만든 앱 이름은 반짝이야.","assistant" to "확인.","user" to update,"assistant" to "확인.");assertFalse(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"))}}
 @Test fun ambiguousNamedCreatorRecallKeepsOriginalWithoutGuessingName(){
  for(q in listOf("달빛을 만든 사람은 누구인가요?","달빛으로 만든 것과 소유한 것을 구분해 주세요.")) {
   val m=messages(q,"user" to "제가 만든 앱 이름은 달빛이에요.","assistant" to "앱 이름을 알려 주셔서 감사합니다.")
   val view=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(4,view.length())
   assertEquals("제가 만든 앱 이름은 달빛이에요.",view.getJSONObject(1).getString("content"))
   if(q.endsWith("누구인가요?")) assertEquals("grounded_app_creator",answer(m)!!.action) else assertNull(answer(m))
  }
 }
 @Test fun uncertainSuffixBothReferencesKeepVerbatimSource(){
  for(q in listOf("몽실을 부르는 짧은 말을 써 줘.","몽실이를 부르는 짧은 말을 써 줘.")) {
   val m=messages(q,"user" to "내 강아지 이름은 몽실이야.","assistant" to "확인.")
   assertTrue(GroundedConversationPolicy.ground(m).contains("내 강아지 이름은 몽실이야."));assertNull(answer(m))
  }
 }
 @Test fun opaqueOwnershipRecallKeepsEvidence(){
  val m=messages("그건 누구 거였지?","user" to "노란 가방은 내 거야.","assistant" to "확인.")
  assertEquals(4,JSONArray(GroundedConversationPolicy.ground(m)).length());assertNull(answer(m))
 }
 @Test fun crossTopicOrganizationKeepsAllSourcesAndRoleOrder(){
  val m=messages("제가 만든 것과 제가 소유한 물건을 구분해서 정리해 주세요.","user" to "제가 만든 앱 이름은 달빛이에요.","assistant" to "확인.","user" to "파란 수첩은 제 거예요.","assistant" to "확인.")
  val view=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(6,view.length())
  assertEquals("제가 만든 앱 이름은 달빛이에요.",view.getJSONObject(1).getString("content"));assertEquals("assistant",view.getJSONObject(2).getString("role"));assertEquals("파란 수첩은 제 거예요.",view.getJSONObject(3).getString("content"))
 }
 @Test fun uncertaintyIsNotEvidenceOfIrrelevance(){
  val m=messages("나중에 다시 생각해 볼까?","user" to "내 강아지 이름은 하루야.","assistant" to "확인.")
  assertEquals(4,JSONArray(GroundedConversationPolicy.ground(m)).length());assertEquals(4,JSONArray(m).length())
 }
 @Test fun exclusionAppliesOnlyToNamedFactTopic(){
  val m=messages("앱 얘기는 빼고 고양이 이름이 뭐라고 했지?","user" to "내 고양이 이름은 하루야.","assistant" to "확인.","user" to "내가 만든 앱 이름은 단비야.","assistant" to "확인.")
  val view=JSONArray(GroundedConversationPolicy.ground(m));assertEquals(4,view.length());assertTrue(view.toString().contains("고양이 이름은 하루야"));assertFalse(view.toString().contains("앱 이름은 단비야"));assertEquals(6,JSONArray(m).length())
 }
 @Test fun genericSummaryKeepsAmbiguousNamesEvenWithOtherTopicWords(){
  val m=messages("물건과 이름을 아까 말한 순서로 정리해 주세요.","user" to "제 고양이 이름은 몽실이에요.","assistant" to "확인.")
  assertTrue(GroundedConversationPolicy.ground(m).contains("제 고양이 이름은 몽실이에요."));assertNull(answer(m))
 }

 @Test fun makerRecallReportsTheSpeakerAndDoesNotGuessTheSuffix() {
  val history = arrayOf("user" to "내가 만든 앱 이름은 초롱이야.", "assistant" to "내가 만들었어.")
  for (q in listOf("초롱을 만든 사람은 누구야?", "초롱이를 누가 만들었어?", "초롱의 제작자는 누구예요?")) {
   val m = messages(q, *history)
   assertEquals("grounded_app_creator", answer(m)!!.action)
   assertTrue(speech(m).contains("네가 직접")); assertTrue(speech(m,true).contains("직접 만드셨"))
   assertFalse(speech(m).contains("초롱")); assertFalse(GroundedConversationPolicy.ground(m).contains("앱 제작자는 사용자다"))
  }
 }
 @Test fun appPossessionGivesNoMakerEvidencedByThatStatement() {
  val m = messages("라임 앱은 누가 만들었나요?", "user" to "제 앱 이름은 “라임”이에요.")
  assertEquals("app_creator_unspecified",answer(m,true)!!.action)
  assertTrue(speech(m,true).contains("그 말씀만으로"))
  assertNull(answer(messages("라임 앱은 누가 만들었나요?", "user" to "라임은 언니가 개발했어요.", "user" to "제 앱 이름은 라임입니다.")))
 }
 @Test fun aChangedOrRetractedSourceIsNeverAForcedCreatorAnswer() {
  for (later in listOf("그건 친구가 만들었어.", "앞에서 한 말은 정정할게.", "내 앱 이름은 단비야.",
                        "초롱은 내가 만든 게 아니야.", "이름이 같은 앱이 두 개야.")) {
   assertNull(answer(messages("초롱의 개발자는 누구야?", "user" to "내가 만든 앱 이름은 초롱이야.", "user" to later)))
  }
 }
 @Test fun referenceMustMatchUserSourceAndRelation() {
  val question = "유리의 제작자는 누구예요?"
  for (source in listOf("친구가 만든 앱 이름은 유리예요.", "제가 만든 앱 이름은 새유리예요.", "제가 만든 앱 이름은 유리예요. 라고 가정하자.")) {
   assertNull(answer(messages(question, "user" to source)))
  }
  assertNull(answer(messages(question, "assistant" to "제가 만든 앱 이름은 유리예요.")))
  assertNull(answer(messages(question, "user" to "제 강아지 이름은 유리예요.", "user" to "제가 만든 앱 이름은 유리예요.")))
  assertNull(answer(messages("이 제작자 질문을 번역해 줘.", "user" to "제가 만든 앱 이름은 유리예요.")))
 }
 @Test fun appAndPersonalNameClarificationNeedsBothClaims() {
  val m = messages("내 이름은 아직 안 알려 줬어. 온유는 내 이름이야?", "user" to "내가 만든 앱 이름은 온유야.",
                   "assistant" to "온유라고 부를게.", "user" to "온유를 누가 만들었어?", "assistant" to "모르겠어.",
                   "user" to "노란 가방은 내 거야.")
  assertEquals("grounded_app_personal_name",answer(m)!!.action)
  assertFalse(speech(m).contains("?")); assertTrue(speech(m).contains("앱 이름"))
  assertNull(answer(messages("내 이름은 아직 안 알려 줬어. 온유는 내 이름이야?", "assistant" to "앱 이름은 온유야.")))
  assertNull(answer(messages("내 이름은 아직 안 알려 줬어. 온유는 내 이름이야?", "user" to "내 이름은 온유야.", "user" to "내 앱 이름은 온유야.")))
 }
}
