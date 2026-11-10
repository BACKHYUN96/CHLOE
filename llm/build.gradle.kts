plugins { id("com.android.library") }
android {
 namespace = "ai.chloe.llm"
 compileSdk = 35
 ndkVersion = "28.2.13676358"
 defaultConfig {
  minSdk = 31
  ndk { abiFilters += "arm64-v8a" }
  externalNativeBuild.cmake { arguments += listOf("-DANDROID_STL=c++_shared", "-DCMAKE_BUILD_TYPE=Release"); targets += "chloe_llm" }
 }
 externalNativeBuild.cmake { path=file("src/main/cpp/CMakeLists.txt"); version="3.22.1" }
}
