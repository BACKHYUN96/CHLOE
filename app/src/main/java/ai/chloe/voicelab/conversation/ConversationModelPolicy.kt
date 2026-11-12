package ai.chloe.voicelab.conversation

internal object ConversationModelPolicy {
 val keys=listOf("4b","2b","9b")
 fun contextTokens(model:String):Int {require(model in keys);return if(model=="9b")1024 else 2048}
 fun inferenceTimeoutMs(model:String):Long {require(model in keys);return if(model=="9b")600_000L else 180_000L}
 fun releaseForTts(model:String,selected:Boolean):Boolean {require(model in keys);return selected}
}
