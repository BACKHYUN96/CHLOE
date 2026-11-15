package ai.chloe.voicelab.conversation
import org.junit.Test
import org.junit.Assert.*
class ReplyIntegrityPolicyTest {
 private fun clean(q:String,s:String)=ReplyIntegrityPolicy.apply(q,s)
 @Test fun completeAnswerSurvivesEchoRemoval(){val r=clean("RTF가 뭐야?","RTF는 문서 포맷이야. RTF가 뭐야?");assertEquals("RTF는 문서 포맷이야.",r.text);assertFalse(r.blocked)}
 @Test fun pureQuestionEchoIsAbstentionNotInventedAnswer(){val r=clean("오늘 뭐 했어?","오늘 뭐 했어? 네, 오늘 뭐 했어? 네, 오늘 뭐");assertTrue(r.blocked);assertEquals("",r.text)}
 @Test fun differentFollowupIsPreserved(){val s="그 일로 힘들었구나. 어떤 일이 있었어?";assertEquals(s,clean("내가 힘들어 보였어?",s).text)}
 @Test fun incompleteTailIsRemoved(){assertEquals("괜찮아. 천천히 해도 돼.",clean("도와줘","괜찮아. 천천히 해도 돼. 그리고").text)}
 @Test fun onlyFragmentDoesNotBecomeSpeech(){assertTrue(clean("오늘 뭐 할까?","제가").blocked)}
 @Test fun punctuationAbsenceAloneIsNotFailure(){val s="천천히 쉬어도 괜찮아";assertEquals(s,clean("좀 쉬고 싶어",s).text)}
 @Test fun decimalAndStructuredContentIsPreserved(){val s="값은 1.5야. 단위는";assertEquals(s,clean("계산해줘",s).text)}
 @Test fun codeQuotesUrlsAndRequestedRepeatAreProtected(){for(q in listOf("그대로 말해줘","번역해줘","인터뷰 질문해줘"))assertEquals("오늘 뭐 했어?",clean(q,"오늘 뭐 했어?").text);for(s in listOf("“네가 알려준 이름이 없으면 모른다고 답해.”","https://example.com 그리고"))assertEquals(s,clean("설명해줘",s).text)}
 @Test fun ruleLeakIsRemovedWithoutChangingIdentity(){val r=clean("넌 누구야?","나는 한국어 AI야. 네가 알려준 이름이 없으면 모른다고 답해.");assertEquals("나는 한국어 AI야.",r.text);assertFalse(r.blocked)}
 @Test fun onlyRuleLeakIsBlocked(){assertTrue(clean("넌 누구야?","네가 알려준 이름이 없으면 모른다고 답해.").blocked)}
 @Test fun publicRuleExplanationIsNotLeak(){val s="규칙은 공동으로 정한 약속이야. 짧게 말해.";assertEquals(s,clean("규칙이 뭐야?",s).text)}
 @Test fun missingInformationIsPreserved(){val s="아직 생일을 몰라. 생일이 언제야?";assertEquals(s,clean("내 생일 기억해?",s).text)}
 @Test fun explicitSentenceCountCannotBeSilentlyBroken(){assertTrue(clean("두 문장으로 답해줘","나는 AI야. 네가 알려준 이름이 없으면 모른다고 답해.").blocked)}
 @Test fun blockedReplyNeverEntersHistoryOrBecomesTtsCurrent(){val m=ConversationManager();m.prompt("이 파일 맞아?",false);val r=m.accept("이 파일 맞아?","이 파일 맞아? 이 파일은");assertTrue(r.fallback);assertEquals("unusable_reply",r.failureCode);assertFalse(r.failureCode in setOf("none","invalid_direction","plain_text"));assertFalse(m.context.messages("AI","다음").contains("이 파일 맞아?"));assertTrue(r.integrityAction.contains("abstain"))}
 @Test fun invalidJsonIsNotRescued(){val m=ConversationManager();m.prompt("이름?",false);val r=m.accept("이름?","{broken");assertEquals("invalid_output",r.failureCode);assertEquals("none",r.integrityAction)}
 @Test fun retainedReplyIsStoredAfterIntegrityEdit(){val m=ConversationManager();m.prompt("넌 누구야?",false);val r=m.accept("넌 누구야?","나는 AI야. 네가 알려준 이름이 없으면 모른다고 답해.");assertEquals("나는 AI야.",r.spokenText);assertFalse(m.context.messages("AI","다음").contains("알려준 이름"));assertTrue(ConversationEvaluator().structural(r).getString("integrity_action").contains("strip_rule_leak"))}
}
