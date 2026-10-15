# PhoneToUSB Proguard rules
-keep class com.phonetousb.data.model.** { *; }
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}
