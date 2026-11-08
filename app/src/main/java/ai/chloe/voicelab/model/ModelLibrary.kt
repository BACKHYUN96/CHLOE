package ai.chloe.voicelab.model

import java.io.File
import org.json.JSONObject

/** Filesystem-only catalog. An update migrates alpha1/2's active folder without copying weights. */
internal class ModelLibrary(private val root: File) {
    init {
        root.mkdirs()
        val legacy = File(root, "active")
        val legacyPrevious = File(root, "previous")
        if (!legacy.exists() && File(legacyPrevious, "model-pack.json").isFile) legacyPrevious.renameTo(legacy)
        for (spec in ModelSpec.entries) {
            val destination = File(root, spec.key)
            val previous = File(root, "${spec.key}.previous")
            if (!destination.exists() && previous.exists()) previous.renameTo(destination)
        }
        if (legacy.isDirectory) runCatching {
            val id = JSONObject(File(legacy, "model-pack.json").readText()).getString("model_id")
            val spec = ModelSpec.fromModelId(id)
            val destination = File(root, spec.key)
            if (!destination.exists()) legacy.renameTo(destination)
        }
    }
    fun directory(spec: ModelSpec): File {
        val destination = File(root, spec.key)
        // Keep an old installation usable if a filesystem rename was unsuccessful.
        val legacy = File(root, "active")
        if (!destination.exists() && legacy.isDirectory && runCatching {
            JSONObject(File(legacy, "model-pack.json").readText()).getString("model_id") == spec.modelId
        }.getOrDefault(false)) return legacy
        return destination
    }
    fun installed(spec: ModelSpec) = File(directory(spec), "model-pack.json").isFile
}
