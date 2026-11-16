package ai.chloe.pc;
import ai.chloe.voicelab.conversation.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Same production Java policies and Kotlin VoiceDirector, on JVM, not Android. */
public final class PcPolicyBridge {
 public static void main(String[] args)throws Exception {
  BufferedReader input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));
  PrintWriter output=new PrintWriter(new OutputStreamWriter(System.out,StandardCharsets.UTF_8),true);
  VoiceDirector director=new VoiceDirector();
  for(String line;(line=input.readLine())!=null;){
   try {
    JSONObject row=new JSONObject(line);String original=row.getJSONArray("messages").toString();
    if(row.optString("op").equals("prepare")) {
     output.println(new JSONObject().put("actual_messages",new JSONArray(GroundedConversationPolicy.ground(original))));continue;
    }
    String raw=row.getString("raw");boolean polite=row.getString("register").equals("polite");
    DirectedReply parsed=director.parse(raw);String failure=parsed.getFailureCode();
    boolean usable=failure.equals("none")||failure.equals("invalid_direction")||failure.equals("plain_text");
    GroundedConversationPolicy.Decision grounding=usable?GroundedConversationPolicy.resolve(original,polite):null;
    ConversationActPolicy.Decision act=usable&&grounding==null&&row.getString("condition").equals("after")?ConversationActPolicy.resolve(original,polite):null;
    JSONObject result=new JSONObject().put("policy_action",grounding==null?"none":grounding.action).put("dialogue_action",act==null?"none":act.action)
      .put("raw_failure_code",failure).put("raw_spoken",parsed.getSpokenText());
    if(!usable){output.println(result.put("blocked",true).put("consumer_failure_code",failure).put("delivered_raw",JSONObject.NULL).put("delivered_spoken",""));continue;}
    String selected=grounding!=null?grounding.reply:act!=null?act.reply:raw;
    DirectedReply grounded=director.parse(selected);
    ReplyEconomyPolicy.Result economy=ReplyEconomyPolicy.apply(row.getString("input"),grounded.getSpokenText());
    ReplyIntegrityPolicy.Result integrity=ReplyIntegrityPolicy.apply(row.getString("input"),economy.text);
    result.put("economy_action",economy.action).put("integrity_action",integrity.action).put("blocked",integrity.blocked);
    if(integrity.blocked)result.put("consumer_failure_code","unusable_reply").put("delivered_raw",JSONObject.NULL).put("delivered_spoken","");
    else {
     String edited=new JSONObject(selected).put("spoken_text",integrity.text).toString();DirectedReply delivered=director.parse(edited);
     result.put("delivered_raw",edited).put("delivered_spoken",delivered.getSpokenText()).put("consumer_failure_code",delivered.getFailureCode());
    }
    output.println(result);
   }catch(Exception e){output.println(new JSONObject().put("error",e.getClass().getSimpleName()+": "+e.getMessage()));}
  }
 }
}
