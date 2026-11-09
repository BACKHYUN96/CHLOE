package ai.chloe.voicelab.diagnostics

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager
import org.json.JSONObject

internal fun deviceTelemetry(context: Context): JSONObject = try {
    val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    val manager = context.getSystemService(BatteryManager::class.java)
    val memory = ActivityManager.MemoryInfo().also { context.getSystemService(ActivityManager::class.java).getMemoryInfo(it) }
    fun property(id: Int): Any = manager.getIntProperty(id).let { if (it == Int.MIN_VALUE) JSONObject.NULL else it }
    fun extra(key: String, divisor: Double = 1.0): Any = battery?.getIntExtra(key, Int.MIN_VALUE)
        ?.takeIf { it != Int.MIN_VALUE }?.let { it / divisor } ?: JSONObject.NULL
    JSONObject().put("thermal_status", context.getSystemService(PowerManager::class.java).currentThermalStatus)
        .put("battery_temperature_c", extra(BatteryManager.EXTRA_TEMPERATURE, 10.0))
        .put("battery_voltage_mv", extra(BatteryManager.EXTRA_VOLTAGE))
        .put("battery_level", extra(BatteryManager.EXTRA_LEVEL)).put("battery_scale", extra(BatteryManager.EXTRA_SCALE))
        .put("battery_plugged", extra(BatteryManager.EXTRA_PLUGGED))
        .put("battery_current_now_ua", property(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW))
        .put("battery_charge_counter_uah", property(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER))
        .put("power_save_mode", context.getSystemService(PowerManager::class.java).isPowerSaveMode)
        .put("system_available_ram_bytes", memory.availMem).put("system_total_ram_bytes", memory.totalMem)
        .put("system_low_memory", memory.lowMemory)
} catch (e: Exception) {
    JSONObject().put("telemetry_error", e.javaClass.simpleName)
}
