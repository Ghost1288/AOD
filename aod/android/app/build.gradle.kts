plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "app.aod.remote"
    compileSdk = 34
    defaultConfig {
        applicationId = "app.aod.remote"
        minSdk = 29
        targetSdk = 34
        val build = (project.findProperty("buildNumber") as String?)?.toIntOrNull() ?: 1
        versionCode = build
        versionName = "2.0.$build"
    }
    // Fixed signing key so every build can update the previous one in place.
    signingConfigs {
        create("aod") {
            storeFile = file("aod.jks"); storePassword = "aodaodaod"
            keyAlias = "aod"; keyPassword = "aodaodaod"
        }
    }
    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("aod") }
        getByName("release") { isMinifyEnabled = false; signingConfig = signingConfigs.getByName("aod") }
    }
    lint { checkReleaseBuilds = false; abortOnError = false }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
}
