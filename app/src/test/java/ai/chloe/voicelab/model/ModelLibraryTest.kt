package ai.chloe.voicelab.model

import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ModelLibraryTest {
    @get:Rule val temporary = TemporaryFolder()
    private fun pack(directory: File, spec: ModelSpec, marker: String) {
        directory.mkdirs()
        File(directory, "model-pack.json").writeText(JSONObject().put("model_id", spec.modelId).toString())
        File(directory, "weights").writeText(marker)
    }
    @Test fun migratesLegacyWithoutLosingSmallWeights() {
        val root = temporary.newFolder()
        pack(File(root, "active"), ModelSpec.SMALL, "existing-small")
        val library = ModelLibrary(root)
        assertTrue(library.installed(ModelSpec.SMALL))
        assertEquals("existing-small", File(library.directory(ModelSpec.SMALL), "weights").readText())
        assertFalse(library.installed(ModelSpec.LARGE))
        assertFalse(File(root, "active").exists())
    }
    @Test fun coexistingModelsResolveDifferentDirectories() {
        val root = temporary.newFolder()
        pack(File(root, "0.6b"), ModelSpec.SMALL, "small")
        pack(File(root, "1.7b"), ModelSpec.LARGE, "large")
        val library = ModelLibrary(root)
        assertTrue(ModelSpec.entries.all { library.installed(it) })
        assertEquals("small", File(library.directory(ModelSpec.SMALL), "weights").readText())
        assertEquals("large", File(library.directory(ModelSpec.LARGE), "weights").readText())
    }
    @Test fun recoversInterruptedAlpha2ImportBeforeMigration() {
        val root = temporary.newFolder()
        pack(File(root, "previous"), ModelSpec.SMALL, "legacy-backup")
        val library = ModelLibrary(root)
        assertTrue(library.installed(ModelSpec.SMALL))
        assertEquals("legacy-backup", File(library.directory(ModelSpec.SMALL), "weights").readText())
    }
    @Test fun recoversInterruptedReplacementWithoutAffectingOtherModel() {
        val root = temporary.newFolder()
        pack(File(root, "1.7b.previous"), ModelSpec.LARGE, "saved-large")
        pack(File(root, "0.6b"), ModelSpec.SMALL, "small")
        val library = ModelLibrary(root)
        assertEquals("saved-large", File(library.directory(ModelSpec.LARGE), "weights").readText())
        assertEquals("small", File(library.directory(ModelSpec.SMALL), "weights").readText())
    }
}
