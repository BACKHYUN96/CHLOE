package ai.chloe.voicelab.conversation

internal object LlmComputePolicy {
 val modes=listOf("cpu","vulkan16","vulkanmax")
 fun layers(mode:String):Int=when(mode){"cpu"->0;"vulkan16"->16;"vulkanmax"->-1;else->throw IllegalArgumentException("지원하지 않는 연산 모드")}
 fun timeoutMs(model:String,mode:String):Long {layers(mode);return if(mode=="cpu")ConversationModelPolicy.inferenceTimeoutMs(model) else 600_000L}
 fun label(mode:String)=when(mode){"cpu"->"CPU";"vulkan16"->"GPU 16레이어";"vulkanmax"->"GPU 최대";else->throw IllegalArgumentException("지원하지 않는 연산 모드")}
}
