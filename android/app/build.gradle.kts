plugins {
    id("com.android.application") version "8.5.2"
    kotlin("android") version "1.9.24"
    kotlin("kapt") version "1.9.24"
}

android {
    namespace = "com.pricecompare"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pricecompare"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        getByName("release") { isMinifyEnabled = false }
    }

    buildFeatures { compose = true }

    // This is ONLY for Compose compiler version
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }

    // <-- Put Java/Kotlin 17 here
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.02")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3:1.3.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")

    // Icons (for the placeholder image icon)
    implementation("androidx.compose.material:material-icons-extended")

    // Networking / JSON
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.11.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    kapt("com.squareup.moshi:moshi-kotlin-codegen:1.15.1")
}
