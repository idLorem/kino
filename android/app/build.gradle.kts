plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "app.kino.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.kino.tv"
        minSdk = 23
        targetSdk = 34
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
        versionCode = (findProperty("verCode") as String?)?.toInt() ?: 2
        versionName = (findProperty("verName") as String?) ?: "1.0.0"
    }

    val ksPath = System.getenv("KINO_KS")
    val ksPass = System.getenv("KINO_KS_PASS")
    if (!ksPath.isNullOrEmpty() && !ksPass.isNullOrEmpty()) {
        signingConfigs {
            create("kino") {
                storeFile = file(ksPath)
                storePassword = ksPass
                keyAlias = "kino"
                keyPassword = ksPass
            }
        }
    }

    buildTypes {
        debug {
            if (!ksPath.isNullOrEmpty() && !ksPass.isNullOrEmpty()) {
                signingConfig = signingConfigs.getByName("kino")
            }
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.videolan.android:libvlc-all:3.6.5")
}
