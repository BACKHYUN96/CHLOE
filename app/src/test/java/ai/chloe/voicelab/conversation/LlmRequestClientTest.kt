package ai.chloe.voicelab.conversation

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LlmRequestClientTest {
 private class Channel(val reply:(Int,JSONObject)->Unit):LlmChannel {
  lateinit var connected:()->Unit
  lateinit var disconnected:()->Unit
  val sent=mutableListOf<LlmRequest>()
  var closed=false
  override fun bind(connected:()->Unit,disconnected:()->Unit):Boolean{this.connected=connected;this.disconnected=disconnected;return true}
  override fun send(request:LlmRequest){check(!closed);sent+=request}
  override fun close(){closed=true}
 }
 private class Fixture {
  val channels=mutableListOf<Channel>();val events=mutableListOf<JSONObject>()
  val timers=mutableListOf<Pair<Long,()->Unit>>()
  val client=LlmRequestClient({reply->Channel(reply).also{channels+=it}}, {delay,action->val entry=delay to action;timers+=entry;{timers.remove(entry);Unit}}, {events+=it})
  fun request():Channel{client.request("안녕","2b");return channels.last()}
  fun finish(c:Channel){c.reply(c.sent.last().id,JSONObject().put("raw","안녕"))}
 }
 @Test fun repeatedWarmRequestsUseLiveConnection(){val f=Fixture();val c=f.request();c.connected();f.finish(c);f.client.request("두 번째","2b");assertEquals(2,c.sent.size);assertEquals(1,f.channels.size);f.finish(c);assertEquals(2,f.events.size)}
 @Test fun stopThenRequestBindsAgain(){val f=Fixture();val old=f.request();old.connected();f.finish(old);f.client.stop();val fresh=f.request();assertTrue(old.closed);assertNotSame(old,fresh);fresh.connected();assertEquals(1,fresh.sent.size);f.finish(fresh);assertEquals(2,f.events.size)}
 @Test fun releaseBeforeInitialConnectionIgnoresLateCallback(){val f=Fixture();val old=f.request();f.client.stop();val fresh=f.request();old.connected();assertTrue(old.sent.isEmpty());fresh.connected();f.finish(fresh);assertEquals(1,f.events.size)}
 @Test fun staleWorkerReplyCannotFinishNewRequest(){val f=Fixture();val old=f.request();old.connected();val id=old.sent.single().id;f.client.stop();val fresh=f.request();fresh.connected();old.reply(id,JSONObject().put("raw","늦은 답"));assertTrue(f.events.isEmpty());f.finish(fresh);assertEquals(1,f.events.size)}
 @Test fun pendingBindTimesOutAndNextRequestRecovers(){val f=Fixture();val old=f.request();assertEquals(15_000L,f.timers.single().first);f.timers.single().second();assertTrue(old.closed);assertEquals("request_timeout",f.events.single().getString("failure_code"));val fresh=f.request();fresh.connected();f.finish(fresh);assertEquals(2,f.events.size)}
 @Test fun workerProgressDoesNotFinishRequestAndExtendsInferenceBudget(){val f=Fixture();val c=f.request();c.connected();val id=c.sent.single().id;c.reply(id,JSONObject().put("progress","inference"));assertEquals(180_000L,f.timers.single().first);assertFalse(c.closed);f.finish(c);assertTrue(f.timers.isEmpty());assertEquals(2,f.events.size)}
 @Test fun disconnectReleasesOldChannelAndRejectsItsCallbacks(){val f=Fixture();val c=f.request();c.connected();c.disconnected();assertTrue(c.closed);assertEquals("worker_disconnected",f.events.single().getString("failure_code"));val fresh=f.request();c.disconnected();fresh.connected();f.finish(fresh);assertEquals(2,f.events.size)}
 @Test fun simulatedTtsReleaseAndResetAllowFurtherTurns(){val f=Fixture();var c=f.request();c.connected();repeat(3){f.finish(c);f.client.request("다음","4b")};f.finish(c);f.client.stop();c=f.request();c.connected();f.finish(c);f.client.stop();c=f.request();c.connected();f.finish(c);assertEquals(6,f.events.size);assertEquals(3,f.channels.size)}
 @Test fun prefillSettingTravelsWithEachRequest(){val f=Fixture();f.client.request("입력","4b",8);val c=f.channels.single();c.connected();assertEquals(8,c.sent.single().prefillThreads);f.finish(c);f.client.request("다음","4b",6);assertEquals(6,c.sent.last().prefillThreads)}
 @Test fun unsupportedThreadsNeverBind(){val f=Fixture();try{f.client.request("입력","4b",32);fail("must reject")}catch(expected:IllegalArgumentException){};assertTrue(f.channels.isEmpty())}
}
