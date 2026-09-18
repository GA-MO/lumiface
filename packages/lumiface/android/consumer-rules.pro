# ML Kit face detection under R8: without these, release builds throw
# InputImageConverterError (NullPointerException in mlkit_vision_common) on every frame.
-keep class com.google.mlkit.** { *; }
-keep class com.google.android.gms.internal.mlkit_** { *; }
