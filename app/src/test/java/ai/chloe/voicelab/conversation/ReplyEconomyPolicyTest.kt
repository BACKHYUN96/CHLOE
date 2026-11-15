package ai.chloe.voicelab.conversation
import org.junit.Test
import org.junit.Assert.*
class ReplyEconomyPolicyTest {
 private fun clean(q:String,s:String)=ReplyEconomyPolicy.apply(q,s).text
 @Test fun exactAdjacentSentenceRepetitionIsRemoved(){assertEquals("반가워. 같이 해보자.",clean("안녕","반가워. 같이 해보자. 같이 해보자."))}
 @Test fun repeatedBlocksDoNotDeleteNewFollowingFacts(){assertEquals("단비는 강아지야. 가방은 초록색이야. 책은 노란색이야.",clean("요약해줘","단비는 강아지야. 가방은 초록색이야. 단비는 강아지야. 가방은 초록색이야. 책은 노란색이야."))}
 @Test fun negationIsNeverNormalizedAway(){val s="열지 마. 열어도 돼.";assertEquals(s,clean("설명해줘",s))}
 @Test fun nonAdjacentRepetitionIsNotAChange(){val s="가자. 잠깐 멈춰. 가자.";assertEquals(s,clean("말해줘",s))}
 @Test fun quotesAreNotEdited(){val s="“기억해. 기억해.”라고 말했어.";assertEquals(s,clean("이야기해줘",s))}
 @Test fun explicitRepetitionRequestIsPreserved(){val s="안녕. 안녕. 안녕.";assertEquals(s,clean("안녕을 그대로 세 번 말해줘",s))}
 @Test fun numbersAndDecimalFactsArePreserved(){assertEquals("값은 1.5야. 가격은 20원이야.",clean("설명해줘","값은 1.5야. 가격은 20원이야. 궁금한 게 있으면 물어봐!"))}
 @Test fun genuineClarificationIsKept(){val s="어떤 파일인지 알려줘.";assertEquals(s,clean("도와줘",s))}
 @Test fun onlyQuestionCannotBecomeEmpty(){val s="무엇을 도와드릴까요?";assertEquals(s,clean("안녕",s))}
 @Test fun conversationalFollowupIsKept(){val s="산책 잘하셨네요. 어디로 가셨나요?";assertEquals(s,clean("산책하고 왔어",s))}
 @Test fun requestedInterviewQuestionsAreKept(){val s="답변은 이렇습니다. 무엇이 궁금하신가요?";assertEquals(s,clean("인터뷰 질문해줘",s))}
 @Test fun twoSentenceConstraintIsPreserved(){val s="두 문장으로 답할게. 궁금한 게 있으면 물어봐!";assertEquals(s,clean("두 문장으로 말해줘",s))}
 @Test fun shortReplyDeduplicatesAndDropsGenericQuestion(){assertEquals("알았어! 짧게 말해 줄게.",clean("짧게 말해줘","알았어! 짧게 말해 줄게. 네가 뭐가 궁금한지 알려줘. 네가 뭐가 궁금한지 알려줘."))}
 @Test fun substantiveDefinitionDoesNotNeedGenericTail(){assertEquals("메모리는 임시 데이터를 보관하는 공간이야.",clean("메모리가 뭐야?","메모리는 임시 데이터를 보관하는 공간이야. 궁금한 게 있으면 물어봐!"))}
 @Test fun fillerRunsAreNarrow(){assertEquals("네. 3, 3, 3, 3.",clean("말해줘","네, 네, 네, 네. 3, 3, 3, 3."))}
 @Test fun meaningfulTopicQuestionIsKept(){val s="선택에는 용도와 메모리 요구를 살펴야 해. 어떤 용도로 쓰려고 해?";assertEquals(s,clean("모델 크면 좋아?",s))}
 @Test fun malformedGenerationIsNotRescued(){val m=ConversationManager();m.prompt("짧게 말해줘",false);val r=m.accept("짧게 말해줘","{broken");assertEquals("invalid_output",r.failureCode);assertEquals("none",r.economyAction)}
 @Test fun cleanedSpeechIsStoredAndGroundedProvenanceSurvives(){val m=ConversationManager();m.prompt("짧게 말해줘",false);val r=m.accept("짧게 말해줘","알았어. 짧게 말할게. 뭐가 궁금한 거야? 뭐가 궁금한 거야?");assertFalse(r.economyAction=="none");assertFalse(m.context.messages("AI","다음").contains("궁금한"));val metric=ConversationEvaluator().structural(r);assertEquals(r.economyAction,metric.getString("economy_action"));assertEquals("none",metric.getString("policy_action"))}
 @Test fun requestedSentenceCountAlsoProtectsDeduplication(){val s="알았어. 알았어.";assertEquals(s,clean("두 문장으로 답해줘",s))}
 @Test fun negativeRepeatInstructionDoesNotProtectLoop(){assertEquals("알았어.",clean("반복해주지 마", "알았어. 알았어."))}
 @Test fun negativeQuestionInstructionAllowsGenericTailRemoval(){assertEquals("메모리는 임시 데이터를 보관하는 공간이야.",clean("질문을 하지 말아줘", "메모리는 임시 데이터를 보관하는 공간이야. 궁금한 게 있으면 물어봐!"))}
 @Test fun urlsAndCodeAreNotReformatted(){for(s in listOf("https://example.com 안녕. 안녕.","```print(1.5)``` 안녕. 안녕."))assertEquals(s,clean("설명해줘",s))}
 @Test fun shortCompletedNameAnswerDoesNotNeedEchoOffer(){assertEquals("앱 이름은 별빛이에요.",clean("앱 이름이 뭐였죠?","앱 이름은 별빛이에요. 다시 말해 드릴까요?"))}
 @Test fun shortUnansweredNameClarificationIsPreserved(){val s="이름을 알려주세요.";assertEquals(s,clean("누구인지 모르겠어",s))}
 @Test fun genericPraiseDoesNotBecomeASubstantiveAnswer(){val s="좋은 질문이에요. 무엇을 도와드릴까요?";assertEquals(s,clean("뭐야?",s))}
 @Test fun missingNameQuestionIsNotRemoved(){val s="아직 성함을 정확히 모르겠어요. 이름은 무엇인가요?";assertEquals(s,clean("내 이름 기억해?",s))}
 @Test fun requestedQuestionCountIsNotDeduplicated(){val s="어떤 취미가 있나요? 어떤 취미가 있나요?";assertEquals(s,clean("질문을 두 개 해줘",s))}
 @Test fun bareTitleAnswerCanDropEchoOffer(){assertEquals("제목은 봄날이에요.",clean("제목이 뭐였죠?","제목은 봄날이에요. 다시 말해 드릴까요?"))}
}
