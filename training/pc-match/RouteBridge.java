package ai.chloe.pc;

import ai.chloe.voicelab.conversation.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Experimental ablation only. No production policy or persona changes. */
public final class RouteBridge {
 private static boolean usable(DirectedReply r) {
  return Arrays.asList("none","invalid_direction","plain_text").contains(r.getFailureCode());
 }
 private static JSONObject stage(String name, String action, String text, boolean blocked) throws Exception {
  return new JSONObject().put("stage",name).put("action",action).put("speech",text).put("blocked",blocked);
 }
 private static JSONObject consume(JSONObject row, VoiceDirector director) throws Exception {
  String raw=row.getString("raw"), messages=row.getJSONArray("messages").toString();
  boolean polite=row.getString("register").equals("polite");
  DirectedReply parsed=director.parse(raw);JSONArray stages=new JSONArray();
  stages.put(stage("parse","none",usable(parsed)?parsed.getSpokenText():"",!usable(parsed)));
  String selected=raw;
  if(usable(parsed)) {
   GroundedConversationPolicy.Decision g=GroundedConversationPolicy.resolve(messages,polite);
   if(g!=null) selected=g.reply;
   stages.put(stage("grounded_reply",g==null?"none":g.action,director.parse(selected).getSpokenText(),false));
   ConversationActPolicy.Decision a=g==null?ConversationActPolicy.resolve(messages,polite):null;
   if(a!=null) selected=a.reply;
   stages.put(stage("conversation_act",a==null?"none":a.action,director.parse(selected).getSpokenText(),false));
   ReplyEconomyPolicy.Result e=ReplyEconomyPolicy.apply(row.getString("input"),director.parse(selected).getSpokenText());
   stages.put(stage("economy",e.action,e.text,false));
   ReplyIntegrityPolicy.Result i=ReplyIntegrityPolicy.apply(row.getString("input"),e.text);
   stages.put(stage("integrity",i.action,i.blocked?"":i.text,i.blocked));
  }
  JSONObject finalStage=stages.getJSONObject(row.getString("route").equals("minimal")?0:stages.length()-1);
  boolean blocked=finalStage.getBoolean("blocked");String speech=finalStage.getString("speech");
  String delivered=blocked?null:new JSONObject(selected).put("spoken_text",speech).toString();
  // Minimal retains the original model metadata too, not an overridden stage's metadata.
  if(!blocked && row.getString("route").equals("minimal")) delivered=new JSONObject(raw).put("spoken_text",speech).toString();
  return new JSONObject().put("stages",stages).put("blocked",blocked).put("delivered_spoken",speech)
    .put("delivered_raw",delivered==null?JSONObject.NULL:delivered).put("raw_failure_code",parsed.getFailureCode());
 }
 public static void main(String[] args)throws Exception {
  BufferedReader input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));
  PrintWriter output=new PrintWriter(new OutputStreamWriter(System.out,StandardCharsets.UTF_8),true);
  VoiceDirector director=new VoiceDirector();PersonaManager persona=new PersonaManager();
  Map<String,ConversationManager> sessions=new HashMap<>();
  for(String line;(line=input.readLine())!=null;) {
   try {
    JSONObject row=new JSONObject(line);String op=row.getString("op");
    if(op.equals("system")){output.println(new JSONObject().put("system",persona.system(row.getString("register").equals("polite"))));continue;}
    boolean current=row.getString("route").equals("current");
    ConversationManager manager=null;
    if(row.has("session")) {
     String key=row.getString("route")+":"+row.getString("session");
     manager=sessions.computeIfAbsent(key,k->new ConversationManager());
    }
    if(op.equals("prepare")) {
     JSONArray messages=manager==null?row.getJSONArray("messages"):new JSONArray(manager.getContext().messages(persona.system(row.getString("register").equals("polite")),row.getString("input")));
     JSONArray actual=current?new JSONArray(GroundedConversationPolicy.ground(messages.toString())):messages;
     if(current && manager!=null && !actual.toString().equals(manager.prompt(row.getString("input"),row.getString("register").equals("polite")))) throw new IllegalStateException("Prompt mismatch");
     output.println(new JSONObject().put("messages",messages).put("actual_messages",actual));continue;
    }
    JSONObject result=consume(row,director);
    if(manager!=null) {
     if(current) {
      DirectedReply accepted=manager.accept(row.getString("input"),row.getString("raw"));
      if(result.getBoolean("blocked")==usable(accepted) || (!result.getBoolean("blocked") && !accepted.getSpokenText().equals(result.getString("delivered_spoken")))) throw new IllegalStateException("Actual manager consumption mismatch");
     } else if(!result.getBoolean("blocked")) manager.getContext().add(row.getString("input"),result.getString("delivered_spoken"));
     result.put("retained_history_pairs",manager.getContext().getTurnCount());
    }
    output.println(result);
   } catch(Exception e){output.println(new JSONObject().put("error",e.getClass().getSimpleName()+": "+e.getMessage()));}
  }
 }
}
