plugins { id("com.android.library") }
android {
 namespace = "ai.chloe.llm"
 compileSdk = 35
 ndkVersion = "28.2.13676358"
 defaultConfig {
  minSdk = 31
  ndk { abiFilters += "arm64-v8a" }
  externalNativeBuild.cmake { arguments += listOf("-DANDROID_STL=c++_shared", "-DCMAKE_BUILD_TYPE=Release"); targets += "chloe_llm"
   providers.gradleProperty("llmVulkanSdk").orNull?.let { sdk ->
    arguments += listOf("-DCMAKE_PREFIX_PATH=$sdk", "-DSPIRV-Headers_DIR=$sdk/share/cmake/SPIRV-Headers")
   }
   providers.gradleProperty("llmSpirvHeaders").orNull?.let { arguments += "-DSPIRV-Headers_DIR=$it" }
   providers.gradleProperty("llmVulkanHeaders").orNull?.let { arguments += "-DVulkan_INCLUDE_DIR=$it" }
   providers.gradleProperty("llmGlslc").orNull?.let { arguments += "-DVulkan_GLSLC_EXECUTABLE=$it" } }
 }
 externalNativeBuild.cmake { path=file("src/main/cpp/CMakeLists.txt"); version="3.22.1" }
}
