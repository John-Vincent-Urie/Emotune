import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Signing material lives in android/key.properties, which is git-ignored. A
// checkout without it can still build and run debug, but cannot produce a
// release build that claims to be ours.
val keystoreProperties = Properties().apply {
    val keystorePropertiesFile = rootProject.file("key.properties")
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}
val hasReleaseKeystore = keystoreProperties.getProperty("storeFile") != null

android {
    namespace = "com.example.emotune"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.emotune"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["redirectSchemeName"] = "emotune"
        manifestPlaceholders["redirectHostName"] = "spotify-auth-callback"
    }

    packaging {
        resources {
            pickFirsts += setOf("META-INF/LICENSE", "META-INF/NOTICE")
        }
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                storeFile = rootProject.file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // The debug keystore is a well-known key shipped with the Android
            // SDK, so anything signed with it can be impersonated by anyone.
            // Fail loudly instead of quietly producing such a build.
            if (!hasReleaseKeystore) {
                throw GradleException(
                    "Cannot build a release: android/key.properties is missing. " +
                        "See docs/SETUP.md to create the signing keystore, or use " +
                        "`flutter build apk --debug` for a throwaway build."
                )
            }
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    implementation(files("../spotify-android-sdk/app-remote-lib/spotify-app-remote-release-0.8.0.aar"))
    implementation("com.spotify.android:auth:1.2.5")
    implementation("androidx.browser:browser:1.0.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("com.google.code.gson:gson:2.10.1")
}
