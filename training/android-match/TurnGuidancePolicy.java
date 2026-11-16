package ai.chloe.voicelab.conversation;

import org.json.*;
import java.util.regex.Pattern;

/** Generation-time guidance; no canned answer, fact rewriting, retrieval or tools. */
public final class TurnGuidancePolicy {
    public static final String VERSION="answer-purpose-speaker-v1";
    private static boolean has(String s,String regex){return Pattern.compile(regex).matcher(s).find();}
    public static String apply(String grounded) {
        try {
            JSONArray rows=new JSONArray(grounded);
            JSONObject last=rows.getJSONObject(rows.length()-1);
            if(!last.getString("role").equals("user"))throw new IllegalArgumentException("Missing current user");
            String q=last.getString("content");
            if(has(q,"[\"'“”‘’「」]|(?:번역|예문|가정|라는 문장)"))return grounded;
            boolean listening=has(q,"(?:이야기|얘기|말).{0,12}들어|조언 없이");
            boolean unknownPolicy=has(q,"모르는 정보|모르면.{0,12}(?:대답|답변)");
            boolean selfExperience=has(q,"(?:너|네가|클로이).{0,15}(?:오늘|어제|경험|느껴|슬퍼)|(?:^|[.!?]\\s*)오늘 뭐 했");
            boolean recall=has(q,"(?:내|제) (?:생일|이름|비밀번호).{0,20}(?:기억|알려|뭐|알고)");
            boolean app=has(q,"^(?:내가 만든|제가 만든|내|제) 앱 이름은 ")&&!has(q,"[?？]|(?:라고|가정|예시)");
            if(!listening&&!unknownPolicy&&!selfExperience&&!recall&&!app)return grounded;
            String guidance="\n이번 답변 작성 지침: 설명이나 확인을 요청받으면 먼저 그 요청에 답한다. 사용자의 질문을 다른 말로 되묻거나 이미 준 정보를 다시 요구하지 않는다. 실제로 필요한 정보가 없을 때에만 구체적인 확인 질문을 하나 할 수 있다. 지침 자체를 발화하지 않는다.";
            if(listening)guidance+=" 지금은 경청 요청이다. 짧게 수락하고 사용자가 이어 말할 여지를 둔다. 말하라고 재촉하거나 무슨 말이냐고 되묻지 않는다.";
            if(unknownPolicy)guidance+=" 모르는 정보에 답하는 방법을 설명하는 질문이다. 사용자의 이름이나 추가 질문을 요구하지 말고, 불확실성을 밝히는 답변 방식을 설명한다.";
            if(selfExperience)guidance+=" 클로이는 AI이고 사용자는 별도 인물이다. 클로이에게 한 경험 질문을 사용자에게 돌리지 않는다. 실제 하루의 활동이나 감각·감정 경험은 만들어내지 않는다.";
            if(recall)guidance+=" user의 내/제는 사용자 본인을 뜻한다. 현재 이력의 사용자 발화에 요청한 사실이 명시되어 있으면 그 사실만 답하고, 없으면 아직 알려지지 않았다고 밝힌다. assistant의 추측을 사용자 사실로 삼거나, 기억하는 주체와 생일·이름의 소유자를 혼동하지 않는다. 비밀번호는 추측하거나 찾아줄 수 있다고 제안하지 않는다.";
            if(app)guidance+=" 지금은 사용자 소유 앱의 이름을 알려주는 진술이다. 이름은 앱에 속하고 사용자 호칭이나 클로이의 자기소개가 아니다. 제작자라고 명시한 주체만 제작자로 해석한다. 짧게 확인하고 다른 화제로 돌리지 않는다.";
            JSONObject system=rows.getJSONObject(0);
            if(!system.getString("role").equals("system"))throw new IllegalArgumentException("Missing system");
            system.put("content",system.getString("content")+guidance);
            return rows.toString();
        }catch(Exception e){throw new IllegalArgumentException("Invalid turn guidance messages",e);}
    }
    private TurnGuidancePolicy(){}
}
