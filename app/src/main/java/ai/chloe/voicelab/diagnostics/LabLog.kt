package ai.chloe.voicelab.diagnostics

import android.content.Context
import android.os.Debug
import android.os.Process
import android.util.Log
import org.json.JSONObject
import java.io.File

internal class LabLog(context: Context, private val role: String) {
    private val directory = File(context.filesDir, "logs").apply { mkdirs() }
    private val file = File(directory, "$role.jsonl")
    @Synchronized fun record(event: String, details: JSONObject = JSONObject()) {
        runCatching {
            if (file.length() > 4 * 1024 * 1024) {
                val old = File(directory, "$role.previous.jsonl")
                old.delete(); file.renameTo(old)
            }
            details.put("event", event).put("wall_time_ms", System.currentTimeMillis())
                .put("pid", Process.myPid()).put("native_heap_bytes", Debug.getNativeHeapAllocatedSize())
            file.appendText(details.toString() + "\n")
            Log.i("CHLOE.$role", details.toString())
        }.onFailure { Log.e("CHLOE.$role", "Log write failed", it) }
    }
}
