package ai.chloe.voicelab.conversation;

import java.util.*;
import java.util.regex.*;

/** Bounded deletion/abstention. Never supplies a guessed answer to replace echo. */
public final class ReplyIntegrityPolicy {
    public static final String VERSION="echo-fragment-rule-leak-v1";
    public static final class Result {
        public final String text, action;
        public final boolean blocked;
        Result(String text,String action,boolean blocked){this.text=text;this.action=action;this.blocked=blocked;}
    }
    private static boolean has(String text,String regex){return Pattern.compile(regex).matcher(text).find();}
    private static String key(String s){return s.replaceFirst("^(?:아|네|응|예)[,!，]?\\s*","").replaceAll("[\\s.!?。！？]","");}
    private static boolean protectedText(String q,String s){
        return has(q,"(?:그대로|인용|따라 ?해|반복해|읽어 ?줘|번역|인터뷰|퀴즈|질문을|질문해|확인 질문|되물어)")
            ||has(s,"[\"'“”‘’「」]|```|https?://|www\\.|[A-Za-z0-9]+@[A-Za-z0-9]");
    }
    private static List<String> units(String text){
        List<String> rows=new ArrayList<>();Matcher m=Pattern.compile("[^.!?。！？]+(?:[.!?。！？]+|$)").matcher(text);
        while(m.find())rows.add(m.group());return rows;
    }
    private static boolean leakedInstruction(String s){
        return has(s,"네가 알려준 이름이 (?:없으면|있으면)")
            &&has(s,"(?:모른다고 (?:답해|해)|그 이름으로 답하고|자기소개.{0,12}(?:않아|안 해))")
            ;
    }
    private static boolean fragment(String s){
        String t=s.trim();
        return !t.isEmpty()&&!has(t,"[.!?。！？]$")&&has(t,"(?:[가-힣]+(?:은|는|을|를)|내가|제가|그리고|그래서|하지만|뭐|어떤|어떻게|때문에|하면|한다면)$");
    }
    public static Result apply(String input,String spoken){
        if(spoken==null||spoken.trim().isEmpty()||protectedText(input,spoken))return new Result(spoken,"none",false);
        // Decimal/structured output is outside this sentence-level editor.
        if(has(spoken,"[0-9]\\.[0-9]|\\n|[{}]"))return new Result(spoken,"none",false);
        Set<String> questions=new HashSet<>();
        for(String q:units(input))if(has(q,"[?？]$")&&key(q).length()>=3)questions.add(key(q));
        List<String> source=units(spoken), kept=new ArrayList<>();List<String> actions=new ArrayList<>();
        for(int i=0;i<source.size();i++){
            String unit=source.get(i), trimmed=unit.trim();
            boolean leaked=leakedInstruction(trimmed)||has(spoken,"네가 알려준 이름이 (?:없으면|있으면)")
                &&trimmed.matches("^(?:짧게 말해|자기소개(?:를|는)? 반복하지 (?:마|않아))[.!]$");
            if(leaked){if(!actions.contains("strip_rule_leak"))actions.add("strip_rule_leak");continue;}
            if(has(trimmed,"[?？]$")&&questions.contains(key(trimmed))){if(!actions.contains("strip_question_echo"))actions.add("strip_question_echo");continue;}
            if(i==source.size()-1&&fragment(trimmed)){actions.add("strip_dangling_fragment");continue;}
            kept.add(unit);
        }
        if(actions.isEmpty())return new Result(spoken,"none",false);
        String result=String.join("",kept).trim();
        // An acknowledgement alone is not a replacement answer.
        if(result.isEmpty()||result.matches("^(?:아|네|응|예|알았어|알겠습니다)[.!]?$"))
            return new Result("",String.join("+",actions)+"+abstain",true);
        int floor=has(input,"(?:두|2) ?문장")?2:has(input,"(?:세|3) ?문장")?3:1;
        if(units(result).size()<floor)return new Result("",String.join("+",actions)+"+abstain",true);
        return new Result(result,String.join("+",actions),false);
    }
    private ReplyIntegrityPolicy(){}
}
