package ai.chloe.match.driver;

import android.app.Instrumentation;
import android.content.*;
import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import ai.chloe.voicelab.conversation.GroundedConversationPolicy;
import ai.chloe.voicelab.conversation.ReplyEconomyPolicy;
import ai.chloe.voicelab.conversation.ReplyIntegrityPolicy;
import ai.chloe.voicelab.conversation.TurnGuidancePolicy;
import ai.chloe.voicelab.conversation.ConversationActPolicy;

/** Framework-only driver, installed only against isolated comparison packages. */
public class Driver extends Instrumentation {
    Bundle args;
    public void callActivityOnResume(android.app.Activity activity) {
        super.callActivityOnResume(activity);
        activity.getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
    public void onCreate(Bundle a) { args=a; super.onCreate(a); start(); }
    public void onStart() {
        Bundle result=new Bundle();
        try {
            String op=args.getString("op", "dump");
            if(op.equals("serve")) serve();
            else if(op.equals("chloe")) runChloe();
            else if(op.equals("auditApp")) auditApp();
            else if(op.equals("groundAudit")) groundAudit();
            else if(op.equals("economyAudit")) economyAudit();
            else if(op.equals("integrityAudit")) integrityAudit();
            else if(op.equals("actsAudit")) actsAudit();
            else if(op.equals("persona")) {
                Class<?> c=getTargetContext().getClassLoader().loadClass("ai.chloe.voicelab.conversation.PersonaManager");
                Object obj=c.getDeclaredConstructor().newInstance();
                result.putString("polite",(String)c.getMethod("direct",boolean.class).invoke(obj,true));
                result.putString("casual",(String)c.getMethod("direct",boolean.class).invoke(obj,false));
            } else if(op.equals("dump")) result.putString("ui",dump(getUiAutomation().getRootInActiveWindow()).toString());
            else if(op.equals("text")) {
                AccessibilityNodeInfo n=find(getUiAutomation().getRootInActiveWindow(),"",true);
                if(n==null) throw new Exception("No editable node");
                Bundle b=new Bundle(); b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,args.getString("text"));
                result.putBoolean("ok",n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b));
            } else if(op.equals("click")) {
                AccessibilityNodeInfo n=find(getUiAutomation().getRootInActiveWindow(),args.getString("needle"),false);
                if(n==null) throw new Exception("No node: "+args.getString("needle"));
                while(!n.isClickable() && n.getParent()!=null)n=n.getParent();
                result.putBoolean("ok",n.performAction(AccessibilityNodeInfo.ACTION_CLICK));
            } else throw new Exception("Unknown op");
            finish(-1,result);
        } catch(Throwable e) { result.putString("error",android.util.Log.getStackTraceString(e)); finish(0,result); }
    }
    void actsAudit() throws Exception {
        Context ctx=getTargetContext();
        JSONArray rows=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        JSONArray output=new JSONArray();
        for(int i=0;i<rows.length();i++) {
            JSONObject row=rows.getJSONObject(i);String original=row.getJSONArray("messages").toString();
            GroundedConversationPolicy.Decision grounded=GroundedConversationPolicy.resolve(original,row.getString("register").equals("polite"));
            ConversationActPolicy.Decision act=grounded==null?ConversationActPolicy.resolve(original,row.getString("register").equals("polite")):null;
            output.put(new JSONObject().put("id",row.getString("source_id")).put("actual_messages",new JSONArray(GroundedConversationPolicy.ground(original)))
                .put("dialogue_action",act==null?"none":act.action).put("dialogue_reply",act==null?JSONObject.NULL:act.reply));
        }
        File dest=new File(ctx.getFilesDir(),args.getString("output"));if(dest.exists())throw new Exception("Refusing overwrite");
        java.nio.file.Files.write(dest.toPath(),output.toString().getBytes(StandardCharsets.UTF_8));
    }
    void integrityAudit() throws Exception {
        Context ctx=getTargetContext();
        JSONArray rows=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        Class<?> director=ctx.getClassLoader().loadClass("ai.chloe.voicelab.conversation.VoiceDirector");
        Object parser=director.getDeclaredConstructor().newInstance();JSONArray output=new JSONArray();
        for(int i=0;i<rows.length();i++) {
            JSONObject row=rows.getJSONObject(i);String raw=row.getString("raw");
            Object before=director.getMethod("parse",String.class).invoke(parser,raw);
            String spoken=(String)before.getClass().getMethod("getSpokenText").invoke(before);
            if(!before.getClass().getMethod("getFailureCode").invoke(before).equals("none"))throw new Exception("Invalid baseline");
            ReplyIntegrityPolicy.Result result=ReplyIntegrityPolicy.apply(row.getString("input"),spoken);
            JSONObject record=new JSONObject().put("id",row.getString("id")).put("before_spoken",spoken)
                .put("after_spoken",result.text).put("integrity_action",result.action).put("blocked",result.blocked);
            if(!result.blocked) {
                String finalRaw=result.action.equals("none")?raw:new JSONObject(raw).put("spoken_text",result.text).toString();
                Object after=director.getMethod("parse",String.class).invoke(parser,finalRaw);
                record.put("final_raw",finalRaw).put("after_failure_code",after.getClass().getMethod("getFailureCode").invoke(after))
                    .put("after_fallback",after.getClass().getMethod("getFallback").invoke(after));
            } else record.put("final_raw",JSONObject.NULL).put("after_failure_code","unusable_reply").put("after_fallback",true);
            output.put(record);
        }
        File dest=new File(ctx.getFilesDir(),args.getString("output"));if(dest.exists())throw new Exception("Refusing overwrite");
        java.nio.file.Files.write(dest.toPath(),output.toString().getBytes(StandardCharsets.UTF_8));
    }
    void economyAudit() throws Exception {
        Context ctx=getTargetContext();
        JSONArray rows=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        Class<?> director=ctx.getClassLoader().loadClass("ai.chloe.voicelab.conversation.VoiceDirector");
        Object parser=director.getDeclaredConstructor().newInstance();JSONArray output=new JSONArray();
        for(int i=0;i<rows.length();i++) {
            JSONObject row=rows.getJSONObject(i);String raw=row.getString("raw");
            Object before=director.getMethod("parse",String.class).invoke(parser,raw);
            String spoken=(String)before.getClass().getMethod("getSpokenText").invoke(before);
            String failure=(String)before.getClass().getMethod("getFailureCode").invoke(before);
            if(!failure.equals("none"))throw new Exception("Expected valid frozen app input");
            ReplyEconomyPolicy.Result result=ReplyEconomyPolicy.apply(row.getString("input"),spoken);
            String finalRaw=result.action.equals("none")?raw:new JSONObject(raw).put("spoken_text",result.text).toString();
            Object after=director.getMethod("parse",String.class).invoke(parser,finalRaw);
            output.put(new JSONObject().put("id",row.getString("id")).put("before_spoken",spoken)
                .put("after_spoken",after.getClass().getMethod("getSpokenText").invoke(after))
                .put("economy_action",result.action).put("final_raw",finalRaw)
                .put("after_fallback",after.getClass().getMethod("getFallback").invoke(after))
                .put("after_failure_code",after.getClass().getMethod("getFailureCode").invoke(after)));
        }
        File dest=new File(ctx.getFilesDir(),args.getString("output"));if(dest.exists())throw new Exception("Refusing overwrite");
        java.nio.file.Files.write(dest.toPath(),output.toString().getBytes(StandardCharsets.UTF_8));
    }
    void groundAudit() throws Exception {
        Context ctx=getTargetContext();
        JSONArray rows=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        JSONArray audits=new JSONArray();
        for(int i=0;i<rows.length();i++) {
            JSONObject row=rows.getJSONObject(i);String original=row.getJSONArray("messages").toString();
            String actual=GroundedConversationPolicy.ground(original);
            GroundedConversationPolicy.Decision d=GroundedConversationPolicy.resolve(original,row.getString("register").equals("polite"));
            audits.put(new JSONObject().put("id",row.getString("source_id")).put("actual_messages",new JSONArray(actual)).put("byte_identical",original.equals(actual)).put("policy_action",d==null?"none":d.action).put("policy_reply",d==null?JSONObject.NULL:d.reply));
        }
        File output=new File(ctx.getFilesDir(),args.getString("output"));if(output.exists())throw new Exception("Refusing overwrite");
        java.nio.file.Files.write(output.toPath(),audits.toString().getBytes(StandardCharsets.UTF_8));
    }
    void auditApp() throws Exception {
        Context ctx=getTargetContext();
        JSONArray rows=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        File output=new File(ctx.getFilesDir(),args.getString("output"));
        if(output.exists())throw new Exception("Refusing to overwrite app audit");
        ClassLoader loader=ctx.getClassLoader();
        Class<?> managerClass=loader.loadClass("ai.chloe.voicelab.conversation.ConversationManager");
        Class<?> directorClass=loader.loadClass("ai.chloe.voicelab.conversation.VoiceDirector");
        Object director=directorClass.getDeclaredConstructor().newInstance();
        JSONArray audits=new JSONArray();
        for(int i=0;i<rows.length();i++) {
            JSONObject row=rows.getJSONObject(i);JSONArray expected=row.getJSONArray("messages");
            Object manager=managerClass.getDeclaredConstructor().newInstance();
            Object history=managerClass.getMethod("getContext").invoke(manager);
            for(int j=1;j<expected.length()-1;j+=2) {
                if(!expected.getJSONObject(j).getString("role").equals("user") || !expected.getJSONObject(j+1).getString("role").equals("assistant"))throw new Exception("Invalid history role order");
                history.getClass().getMethod("add",String.class,String.class).invoke(history,expected.getJSONObject(j).getString("content"),expected.getJSONObject(j+1).getString("content"));
            }
            String prompt=(String)managerClass.getMethod("prompt",String.class,boolean.class,boolean.class,boolean.class).invoke(manager,row.getString("input"),row.getString("register").equals("polite"),true,true);
            JSONArray actual=new JSONArray(prompt);boolean same=expected.length()==actual.length();
            for(int j=0;same&&j<expected.length();j++)for(String key:new String[]{"role","content"})same&=expected.getJSONObject(j).getString(key).equals(actual.getJSONObject(j).getString(key));
            Object reply=directorClass.getMethod("parse",String.class).invoke(director,row.getString("raw"));
            Class<?> replyClass=reply.getClass();
            JSONObject audit=new JSONObject().put("id",row.getString("id")).put("actual_prompt_equal",same);
            for(String key:new String[]{"SpokenText","Intent","Emotion","Pace","Energy","Expressiveness","Instruction","Fallback","FailureCode"}) {
                audit.put(Character.toLowerCase(key.charAt(0))+key.substring(1),replyClass.getMethod("get"+key).invoke(reply));
            }
            audits.put(audit);
        }
        try(FileOutputStream stream=new FileOutputStream(output)){stream.write(audits.toString().getBytes(StandardCharsets.UTF_8));stream.getFD().sync();}
    }
    void serve() throws Exception {
        Context ctx=getTargetContext();
        Intent launch=ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);ctx.startActivity(launch);
        File dir=new File(ctx.getFilesDir(),"match-driver");dir.mkdirs();
        long deadline=SystemClock.elapsedRealtime()+10800000;
        int serial=Integer.parseInt(args.getString("serial","1"));
        while(SystemClock.elapsedRealtime()<deadline){
            File input=new File(dir,"cmd-"+serial+".json");
            if(!input.exists()){Thread.sleep(100);continue;}
            JSONObject cmd=new JSONObject(new String(java.nio.file.Files.readAllBytes(input.toPath()),StandardCharsets.UTF_8));
            JSONObject result=new JSONObject();
            try {
                String op=cmd.getString("op");
                if(op.equals("stop"))break;
                if(op.equals("reflect") || op.equals("inject")) {
                    Object app=ctx.getApplicationContext();
                    Object host=app.getClass().getMethod("getReactHost").invoke(app);
                    if(op.equals("reflect")) {
                        JSONArray methods=new JSONArray(),fields=new JSONArray();
                        for(java.lang.reflect.Method method:host.getClass().getDeclaredMethods())methods.put(method.toString());
                        for(java.lang.reflect.Field field:host.getClass().getDeclaredFields())fields.put(field.toString());
                        result.put("host",host.getClass().getName()).put("methods",methods).put("fields",fields);
                    } else {
                        Class<?> loader=ctx.getClassLoader().loadClass("com.facebook.react.bridge.JSBundleLoader");
                        Object bundle=loader.getMethod("createFileLoader",String.class).invoke(null,new File(ctx.getFilesDir(),cmd.getString("file")).getPath());
                        java.lang.reflect.Method found=null;
                        for(java.lang.reflect.Method method:host.getClass().getDeclaredMethods())if(method.getName().startsWith("loadBundle")&&method.getParameterCount()==1)found=method;
                        if(found==null)throw new Exception("No loadBundle method");
                        found.setAccessible(true);Object task=found.invoke(host,bundle);
                        task.getClass().getMethod("waitForCompletion").invoke(task);
                        Object error=task.getClass().getMethod("getError").invoke(task);
                        result.put("submitted",String.valueOf(task)).put("task_error",error==null?JSONObject.NULL:String.valueOf(error));
                    }
                }
                else if(op.equals("dump"))result.put("ui",dump(getUiAutomation().getRootInActiveWindow()));
                else if(op.equals("scroll")) {
                    AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();
                    AccessibilityNodeInfo node=cmd.has("needle")?findAny(root,cmd.getString("needle")):null;
                    while(node!=null&&!node.isScrollable())node=node.getParent();
                    if(node==null)node=findScrollable(root);
                    if(node==null)throw new Exception("No visible scroll container");
                    android.graphics.Rect rect=new android.graphics.Rect();node.getBoundsInScreen(rect);
                    if(rect.isEmpty())throw new Exception("Empty scroll bounds");
                    float x=rect.centerX(),from=rect.top+rect.height()*0.8f,to=rect.top+rect.height()*0.2f;
                    long t=SystemClock.uptimeMillis();
                    for(int step=0;step<=12;step++) {
                        int action=step==0?0:step==12?1:2;
                        android.view.MotionEvent event=android.view.MotionEvent.obtain(t,t+step*25,action,x,from+(to-from)*step/12,0);
                        event.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);sendPointerSync(event);event.recycle();
                        if(step<12)Thread.sleep(25);
                    }
                    result.put("ok",true).put("bounds",rect.toShortString());
                }
                else if(op.equals("text")) {
                    AccessibilityNodeInfo node=find(getUiAutomation().getRootInActiveWindow(),"",true);
                    if(node==null)throw new Exception("No editable node");
                    Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,cmd.getString("text"));
                    result.put("ok",node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b));
                } else if(op.equals("click") || op.equals("tap")) {
                    AccessibilityNodeInfo node=find(getUiAutomation().getRootInActiveWindow(),cmd.getString("needle"),false);
                    if(node==null)throw new Exception("No node: "+cmd.getString("needle"));
                    while(!node.isClickable() && node.getParent()!=null)node=node.getParent();
                    if(op.equals("tap")) {
                        android.graphics.Rect rect=new android.graphics.Rect();node.getBoundsInScreen(rect);
                        if(rect.isEmpty())throw new Exception("Empty button bounds");
                        long t=SystemClock.uptimeMillis();
                        android.view.MotionEvent down=android.view.MotionEvent.obtain(t,t,0,rect.centerX(),rect.centerY(),0);
                        android.view.MotionEvent up=android.view.MotionEvent.obtain(t,t+70,1,rect.centerX(),rect.centerY(),0);
                        down.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);up.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
                        sendPointerSync(down);sendPointerSync(up);down.recycle();up.recycle();result.put("ok",true).put("bounds",rect.toShortString());
                    } else result.put("ok",node.performAction(AccessibilityNodeInfo.ACTION_CLICK));
                } else throw new Exception("Unknown command");
            }catch(Throwable e){result.put("error",android.util.Log.getStackTraceString(e));}
            File temp=new File(dir,"out-"+serial+".tmp"), dest=new File(dir,"out-"+serial+".json");
            java.nio.file.Files.write(temp.toPath(),result.toString().getBytes(StandardCharsets.UTF_8));
            if(!temp.renameTo(dest))throw new Exception("Cannot publish response");
            serial++;
        }
    }
    JSONArray dump(AccessibilityNodeInfo n) throws Exception {
        JSONArray a=new JSONArray(); if(n==null)return a;
        JSONObject o=new JSONObject().put("text",n.getText()).put("desc",n.getContentDescription()).put("class",n.getClassName()).put("visible",n.isVisibleToUser()).put("editable",n.isEditable()).put("clickable",n.isClickable()).put("package",n.getPackageName());
        a.put(o);for(int i=0;i<n.getChildCount();i++){JSONArray b=dump(n.getChild(i));for(int j=0;j<b.length();j++)a.put(b.get(j));}return a;
    }
    AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo node) {
        if(node==null)return null;
        for(int i=node.getChildCount()-1;i>=0;i--){AccessibilityNodeInfo found=findScrollable(node.getChild(i));if(found!=null)return found;}
        return node.isScrollable()&&node.isVisibleToUser()?node:null;
    }
    AccessibilityNodeInfo findAny(AccessibilityNodeInfo node,String text) {
        if(node==null)return null;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=findAny(node.getChild(i),text);if(found!=null)return found;}
        return text.contentEquals(node.getText()==null?"":node.getText())||text.contentEquals(node.getContentDescription()==null?"":node.getContentDescription())?node:null;
    }
    AccessibilityNodeInfo find(AccessibilityNodeInfo n,String needle,boolean editable) {
        if(n==null)return null;
        boolean same=getTargetContext().getPackageName().contentEquals(n.getPackageName()==null?"":n.getPackageName());
        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo x=find(n.getChild(i),needle,editable);if(x!=null)return x;}
        if(same && n.isVisibleToUser() && ((editable&&n.isEditable()) || (!editable&&(needle.contentEquals(n.getText()==null?"":n.getText())||needle.contentEquals(n.getContentDescription()==null?"":n.getContentDescription())))))return n;
        return null;
    }
    void runChloe() throws Exception {
        Context ctx=getTargetContext();
        JSONArray cases=new JSONArray(new String(java.nio.file.Files.readAllBytes(new File(ctx.getFilesDir(),args.getString("input")).toPath()),StandardCharsets.UTF_8));
        File output=new File(ctx.getFilesDir(),args.getString("output"));
        if(output.exists())throw new Exception("Refusing to overwrite results");
        CountDownLatch connected=new CountDownLatch(1);Messenger[] remote=new Messenger[1];
        ServiceConnection connection=new ServiceConnection(){
            public void onServiceConnected(ComponentName n,IBinder binder){remote[0]=new Messenger(binder);connected.countDown();}
            public void onServiceDisconnected(ComponentName n){}
        };
        Intent intent=new Intent().setClassName(ctx.getPackageName(),"ai.chloe.voicelab.conversation.LlmWorker");
        if(!ctx.bindService(intent,connection,Context.BIND_AUTO_CREATE))throw new Exception("bind failed");
        try {
            if(!connected.await(30,TimeUnit.SECONDS))throw new Exception("bind timeout");
            for(int i=0;i<cases.length();i++) {
                JSONObject row=cases.getJSONObject(i); CountDownLatch done=new CountDownLatch(1);String[] answer=new String[1];
                Messenger reply=new Messenger(new Handler(Looper.getMainLooper(),m->{if(m.what==3){answer[0]=m.getData().getString("result");done.countDown();}return true;}));
                Message m=Message.obtain(null,1);m.arg1=i+1;m.replyTo=reply;
                String original=row.getJSONArray("messages").toString();
                boolean grounded=row.optBoolean("grounded",false);
                String actual=grounded?GroundedConversationPolicy.ground(original):original;
                if(row.optBoolean("turn_guidance",false))actual=TurnGuidancePolicy.apply(actual);
                Bundle b=new Bundle();b.putString("messages",actual);b.putString("model","4b");b.putInt("prefill_threads",4);b.putString("gpu_mode","cpu");m.setData(b);
                long start=SystemClock.elapsedRealtime();remote[0].send(m);
                boolean ok=done.await(240,TimeUnit.SECONDS);
                JSONObject record=new JSONObject().put("id",row.getString("id")).put("elapsed_ms",SystemClock.elapsedRealtime()-start).put("result",ok?new JSONObject(answer[0]):new JSONObject().put("error","timeout"));
                record.put("actual_messages",new JSONArray(actual));
                if(grounded && ok) {
                    JSONObject nativeResult=record.getJSONObject("result");
                    String raw=nativeResult.optString("raw");
                    Class<?> director=ctx.getClassLoader().loadClass("ai.chloe.voicelab.conversation.VoiceDirector");
                    Object parsed=director.getMethod("parse",String.class).invoke(director.getDeclaredConstructor().newInstance(),raw);
                    String failure=(String)parsed.getClass().getMethod("getFailureCode").invoke(parsed);
                    GroundedConversationPolicy.Decision decision=GroundedConversationPolicy.resolve(original,row.getString("register").equals("polite"));
                    boolean usable=failure.equals("none")||failure.equals("invalid_direction")||failure.equals("plain_text");
                    record.put("policy_action",usable&&decision!=null?decision.action:"none");
                    record.put("delivered_raw",usable&&decision!=null?decision.reply:raw);
                    if(row.optBoolean("finalize_reply",false)&&usable) {
                        String selected=record.getString("delivered_raw");
                        ConversationActPolicy.Decision act=row.optBoolean("conversation_acts",false)&&decision==null?ConversationActPolicy.resolve(original,row.getString("register").equals("polite")):null;
                        if(act!=null)selected=act.reply;
                        record.put("dialogue_action",act==null?"none":act.action);
                        Object parsedFinal=director.getMethod("parse",String.class).invoke(director.getDeclaredConstructor().newInstance(),selected);
                        String speech=(String)parsedFinal.getClass().getMethod("getSpokenText").invoke(parsedFinal);
                        ReplyEconomyPolicy.Result economy=ReplyEconomyPolicy.apply(row.getString("input"),speech);
                        ReplyIntegrityPolicy.Result integrity=ReplyIntegrityPolicy.apply(row.getString("input"),economy.text);
                        record.put("economy_action",economy.action).put("integrity_action",integrity.action).put("blocked",integrity.blocked);
                        if(integrity.blocked)record.put("delivered_raw",JSONObject.NULL).put("delivered_spoken","").put("consumer_failure_code","unusable_reply");
                        else {
                            String edited=new JSONObject(selected).put("spoken_text",integrity.text).toString();
                            Object consumed=director.getMethod("parse",String.class).invoke(director.getDeclaredConstructor().newInstance(),edited);
                            record.put("delivered_raw",edited).put("delivered_spoken",consumed.getClass().getMethod("getSpokenText").invoke(consumed))
                                .put("consumer_failure_code",consumed.getClass().getMethod("getFailureCode").invoke(consumed));
                        }
                    }
                }
                try(FileOutputStream out=new FileOutputStream(output,true)){out.write((record.toString()+"\n").getBytes(StandardCharsets.UTF_8));out.getFD().sync();}
                if(!ok)break;
            }
        } finally {ctx.unbindService(connection);}
    }
}
