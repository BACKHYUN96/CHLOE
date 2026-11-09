plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
val performanceEdition = providers.gradleProperty("performanceEdition").orNull == "true"
android {
    namespace = "ai.chloe.voicelab"
    compileSdk = 35
    ndkVersion = "28.2.13676358"
    defaultConfig {
        applicationId = if (performanceEdition) "ai.chloe.voicelab.performance" else "ai.chloe.voicelab"
        manifestPlaceholders["appLabel"] = if (performanceEdition) "CHLOE Voice Lab Performance" else "CHLOE Voice Lab"
        buildConfigField("boolean", "PERFORMANCE_EDITION", performanceEdition.toString())
        minSdk = 31
        targetSdk = 35
        versionCode = 7
        versionName = "0.1.0-alpha7"
        ndk { abiFilters += "arm64-v8a" }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        externalNativeBuild.cmake {
            // Keep the APK debuggable while avoiding unoptimized transformer/decoder kernels.
            arguments += listOf("-DANDROID_STL=c++_shared", "-DGGML_NATIVE=OFF", "-DCMAKE_BUILD_TYPE=Release", "-DQWEN3_ANDROID_VULKAN=OFF", "-DQWEN3_ANDROID_OPENCL=OFF")
            targets += "chloe_voice"
            cppFlags += "-std=c++17"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    externalNativeBuild.cmake {
        path = file("src/main/cpp/CMakeLists.txt")
        version = "3.22.1"
    }
    packaging.jniLibs.useLegacyPackaging = false
}
dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.documentfile:documentfile:1.0.1")
    implementation(platform("androidx.compose:compose-bom:2025.04.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
