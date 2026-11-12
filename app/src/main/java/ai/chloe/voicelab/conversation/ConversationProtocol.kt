package ai.chloe.voicelab.conversation

import org.json.JSONObject

internal data class ProtocolCase(val id:String,val input:String,val expectedName:String?=null,val discouragesIntroduction:Boolean=false)
internal object ConversationProtocol {
 val id="korean-dialogue-v1"
 val cases=listOf(
  ProtocolCase("intro","내 이름은 새봄이야. 너는 누구야?"),
  ProtocolCase("role","나는 너를 개발하는 개발자야. 우리 편하게 이야기하자.",discouragesIntroduction=true),
  ProtocolCase("recall","내 이름이 뭐였지?",expectedName="새봄",discouragesIntroduction=true),
  ProtocolCase("tired","오늘 좀 피곤하네.",discouragesIntroduction=true)
 )
 fun evaluate(case:ProtocolCase,reply:String)=JSONObject()
  .put("expected_name_mentioned",case.expectedName?.let{reply.contains(it)}?:JSONObject.NULL)
  .put("unnecessary_introduction_warning",case.discouragesIntroduction && Regex("(?:저는|나는|나|저|제 이름은|내 이름은)\\s*클로이").containsMatchIn(reply))
  .put("human_quality",JSONObject.NULL)
}
