package ai.chloe.voicelab.conversation;

import java.util.*;
import java.util.regex.*;

/** Deletion-only reply edits. No new facts, paraphrases, reranking or generation.
 * Conservative lexical rules, not a general relevance/clarification classifier.
 */
public final class ReplyEconomyPolicy {
    public static final String VERSION="literal-dedupe-generic-tail-v1";
    public static final class Result {
        public final String text, action;
        Result(String text,String action){this.text=text;this.action=action;}
    }
    private static final class Unit {
        final String raw,key;
        Unit(String raw){this.raw=raw;this.key=raw.trim().replaceAll("\\s+"," ");}
    }
    private static boolean has(String s,String pattern){return Pattern.compile(pattern).matcher(s).find();}
    private static boolean protectedRequest(String input,String text){
        boolean literal=has(input,"(?:그대로|반복해|되풀이해|따라 ?해|인용해|(?:두|세|네|다섯|[2-9]) ?번.{0,12}(?:말해|읽어|반복))")
            && !has(input,"(?:반복|되풀이|그대로|따라).{0,12}(?:말아|하지 ?마|하지말|주지 ?마|말고)");
        return literal
            ||has(text,"[\"'“”‘’「」]|```|https?://|www\\.|[A-Za-z0-9]+@[A-Za-z0-9]");
    }
    private static List<Unit> units(String text){
        List<Unit> result=new ArrayList<>();int start=0;
        for(int i=0;i<text.length();i++){
            char c=text.charAt(i);
            boolean decimal=c=='.'&&i>0&&i+1<text.length()&&Character.isDigit(text.charAt(i-1))&&Character.isDigit(text.charAt(i+1));
            if(".!?。！？".indexOf(c)>=0&&!decimal){
                int end=i+1;while(end<text.length()&&".!?。！？".indexOf(text.charAt(end))>=0)end++;
                String raw=text.substring(start,end);if(!raw.trim().isEmpty())result.add(new Unit(raw));start=end;i=end-1;
            }
        }
        if(start<text.length()&&!text.substring(start).trim().isEmpty())result.add(new Unit(text.substring(start)));
        return result;
    }
    private static boolean same(List<Unit> rows,int a,int b,int n){
        for(int j=0;j<n;j++)if(!rows.get(a+j).key.equals(rows.get(b+j).key))return false;
        return true;
    }
    private static List<Unit> deduplicate(List<Unit> source){
        List<Unit> result=new ArrayList<>();
        for(int i=0;i<source.size();){
            int block=0;
            for(int n=1;n<=4&&i+2*n<=source.size();n++)if(same(source,i,i+n,n)){block=n;break;}
            if(block==0){result.add(source.get(i++));continue;}
            for(int j=0;j<block;j++)result.add(source.get(i+j));
            int next=i+block;
            while(next+block<=source.size()&&same(source,i,next,block))next+=block;
            i=next;
        }
        return result;
    }
    private static boolean asksForQuestions(String input){
        if(has(input,"(?:질문|물어보|되묻|묻).{0,12}(?:하지 ?마|하지말|말아|그만|말고)"))return false;
        return has(input,"(?:질문해|질문을|물어봐|물어보|인터뷰|퀴즈|서로 소개|소개하자)");
    }
    private static boolean needsClarification(String input){
        return input.trim().matches("^(?:좀 |조금 )?(?:도와 ?(?:줘|주세요)|도움이 필요해|추천해 ?(?:줘|주세요)|골라 ?(?:줘|주세요)|어떻게 해야 해)[.!?]?$" );
    }
    private static boolean genericTail(String text){
        String s=text.trim();
        String invite="^(?:(?:뭐|더|또|혹시) ?)?(?:더 ?)?궁금한 ?(?:점|게|것|거)(?:이|가)? ?(?:있(?:니|어|어요|나요|으신가요)|있(?:으면|으시면).{0,30}(?:물어봐 ?(?:요|주세요)?|말씀해 ?주세요|질문해 ?(?:줘|주세요)))[.!?]?$";
        String curiosity="^(?:(?:네가|너가|너는) ?)?뭐가 ?궁금한지 ?알려 ?(?:줘|주세요)[.!?]?$|^(?:뭐가|무엇이) ?궁금(?:한 ?(?:거|것))?(?:이야|야|니|신가요|한가요|해|하세요)[.!?]?$|^(?:뭐가|무엇이) ?궁금한 ?(?:거|것)(?:이)? ?있(?:니|어|어요|나요)[.!?]?$|^(?:뭐가|무엇이) ?궁금하(?:니|신가요|세요)[.!?]?$";
        String help="^(?:(?:오늘|지금) ?)?(?:어떤|무슨|다른) ?도움(?:이|을)? ?(?:필요(?:해|하니|하세요|하신가요)|원(?:해|하니|하세요|하시나요))[.!?]?$|^(?:제가 ?)?(?:무엇을|뭘|어떻게) ?도와(?:드릴까요|줄까|줄까요|드릴까)[.!?]?$";
        String repeat="^(?:다시|한번 ?더) ?말(?:해|씀해) ?(?:드릴까요|줄까|줄까요)[.!?]?$";
        String name="^(?:(?:네|너의|당신의|사용자님의) ?)?이름(?:이|은)? ?(?:뭐야|뭐니|무엇인가요|어떻게 ?되(?:니|세요|시나요))[.!?]?$";
        return s.matches(invite)||s.matches(curiosity)||s.matches(help)||s.matches(repeat)||s.matches(name);
    }
    private static int requiredSentenceFloor(String input){
        if(has(input,"(?:두|2) ?문장"))return 2;
        if(has(input,"(?:세|3) ?문장"))return 3;
        return 1;
    }
    private static boolean meaningfulPrefix(List<Unit> rows,int length,boolean concise,String input){
        int letters=0;
        for(int i=0;i<length;i++){
            String s=rows.get(i).key;
            if(has(s,"[?？]$"))continue;
            if(concise&&!s.isEmpty())return true;
            if(has(input,"(?:이름|명칭|제목)") && s.matches("^.{0,30}(?:이름|명칭|제목)(?:은|는) ?.{1,30}(?:이야|야|이에요|예요|입니다)[.!]$") )return true;
            if(s.matches("^(?:네|응|알았어|좋아|알겠습니다|안녕하세요|고마워요)[.!]?$"))continue;
            letters+=s.replaceAll("[^가-힣A-Za-z0-9]","").length();
        }
        return letters>=12;
    }
    private static String join(List<Unit> rows){
        StringBuilder b=new StringBuilder();for(Unit row:rows)b.append(row.raw);return b.toString().trim();
    }
    public static Result apply(String input,String spoken){
        if(spoken==null||spoken.trim().isEmpty()||protectedRequest(input,spoken)||asksForQuestions(input))return new Result(spoken,"none");
        // Only long runs of acknowledgement fillers, not words/numbers generally.
        Matcher run=Pattern.compile("(?<![가-힣A-Za-z0-9])(네|응|예|음)(?: ?[,，] ?\\1){3,}(?![가-힣A-Za-z0-9])").matcher(spoken);
        StringBuffer sb=new StringBuffer();boolean filler=false;
        while(run.find()){run.appendReplacement(sb,Matcher.quoteReplacement(run.group(1)));filler=true;}run.appendTail(sb);
        List<Unit> before=units(sb.toString()), after=deduplicate(before);
        if(after.size()<requiredSentenceFloor(input))return new Result(spoken,"none");
        boolean duplicate=filler||after.size()!=before.size(), trimmed=false;
        if(!asksForQuestions(input)&&!needsClarification(input)){
            boolean concise=has(input,"(?:짧게|간단히|한 ?문장|한 ?줄|두 ?문장)");
            int floor=requiredSentenceFloor(input);
            boolean missingInfo=has(join(after),"(?:모르겠|모릅|몰라|알 수 없|알지 못|정보가 없|자료가 없|불분명|확실하지)");
            while(!missingInfo&&after.size()>floor&&genericTail(after.get(after.size()-1).key)&&meaningfulPrefix(after,after.size()-1,concise,input)){
                after.remove(after.size()-1);trimmed=true;
            }
        }
        if(!duplicate&&!trimmed)return new Result(spoken,"none");
        String result=join(after);
        if(result.isEmpty()||result.length()>spoken.length())return new Result(spoken,"none");
        String action=duplicate?(trimmed?"deduplicate+trim_generic_tail":"deduplicate"):"trim_generic_tail";
        return new Result(result,action);
    }
    private ReplyEconomyPolicy(){}
}
