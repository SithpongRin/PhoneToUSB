package com.phonetousb.updater

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.phonetousb.BuildConfig
import com.phonetousb.data.model.AndroidReleaseAsset
import com.phonetousb.data.model.ReleaseManifest
import com.phonetousb.security.CryptoUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class GitHubUpdateManager(
    private val context: Context,
    var repoOwner: String = "SithpongRin",
    var repoName: String = "PhoneToUSB"
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()
    private val gson = Gson()

    suspend fun checkForUpdates(): ReleaseManifest? = withContext(Dispatchers.IO) {
        val url = "https://api.github.com/repos/$repoOwner/$repoName/releases/latest"
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "PhoneToUSB-Android")
            .build()

        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val body = response.body?.string() ?: return@withContext null
                val json = gson.fromJson(body, JsonObject::class.java)

                val tagName = json.get("tag_name")?.asString?.removePrefix("v") ?: "0.0.0"
                val bodyText = json.get("body")?.asString ?: "Bug fixes and performance improvements."

                // Locate PhoneToUSB.apk asset
                var downloadUrl = ""
                var apkName = "PhoneToUSB.apk"
                val assets = json.getAsJsonArray("assets")
                if (assets != null) {
                    for (element in assets) {
                        val assetObj = element.asJsonObject
                        val name = assetObj.get("name")?.asString ?: ""
                        if (name.endsWith(".apk")) {
                            downloadUrl = assetObj.get("browser_download_url")?.asString ?: ""
                            apkName = name
                            break
                        }
                    }
                }

                // If no asset found in release, fallback to raw repository main branch
                if (downloadUrl.isBlank()) {
                    downloadUrl = "https://github.com/$repoOwner/$repoName/raw/main/dist/PhoneToUSB.apk"
                }

                ReleaseManifest(
                    version = tagName,
                    changelog = bodyText,
                    android = AndroidReleaseAsset(
                        versionCode = BuildConfig.VERSION_CODE + 1,
                        versionName = tagName,
                        filename = apkName,
                        sha256 = "",
                        downloadUrl = downloadUrl
                    )
                )
            }
        } catch (_: Exception) {
            // Direct fallback to raw GitHub dist
            ReleaseManifest(
                version = "1.0.0",
                changelog = "Official latest PhoneToUSB release.",
                android = AndroidReleaseAsset(
                    versionCode = 100,
                    versionName = "1.0.0",
                    filename = "PhoneToUSB.apk",
                    sha256 = "",
                    downloadUrl = "https://github.com/$repoOwner/$repoName/raw/main/dist/PhoneToUSB.apk"
                )
            )
        }
    }

    suspend fun downloadAndVerifyApk(
        downloadUrl: String,
        expectedSha256: String?,
        onProgress: (percent: Int) -> Unit
    ): File? = withContext(Dispatchers.IO) {
        val updateDir = File(context.cacheDir, "updates").apply { mkdirs() }
        val apkFile = File(updateDir, "PhoneToUSB.apk")
        if (apkFile.exists()) apkFile.delete()

        val request = Request.Builder().url(downloadUrl).build()
        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val body = response.body ?: return@withContext null
                val totalLength = body.contentLength()

                body.byteStream().use { input ->
                    FileOutputStream(apkFile).use { output ->
                        val buffer = ByteArray(32768)
                        var bytesRead: Int
                        var totalRead = 0L

                        while (input.read(buffer).also { bytesRead = it } != -1) {
                            output.write(buffer, 0, bytesRead)
                            totalRead += bytesRead
                            if (totalLength > 0) {
                                val percent = ((totalRead * 100) / totalLength).toInt()
                                onProgress(percent.coerceIn(0, 100))
                            }
                        }
                    }
                }
            }

            if (expectedSha256 != null && expectedSha256.isNotBlank()) {
                val computedHash = CryptoUtils.calculateFileSha256(apkFile)
                if (!computedHash.equals(expectedSha256, ignoreCase = true)) {
                    apkFile.delete()
                    return@withContext null
                }
            }

            apkFile
        } catch (_: Exception) {
            apkFile.delete()
            null
        }
    }

    fun launchPackageInstaller(apkFile: File) {
        // Android 8.0+ Check for unknown app install permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!context.packageManager.canRequestPackageInstalls()) {
                val settingsIntent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                    data = Uri.parse("package:${context.packageName}")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(settingsIntent)
            }
        }

        val contentUri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apkFile
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(contentUri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    fun isNewerVersion(remote: String, local: String): Boolean {
        val rParts = remote.split(".").mapNotNull { it.toIntOrNull() }
        val lParts = local.split(".").mapNotNull { it.toIntOrNull() }

        val maxLen = maxOf(rParts.size, lParts.size)
        for (i in 0 until maxLen) {
            val r = rParts.getOrElse(i) { 0 }
            val l = lParts.getOrElse(i) { 0 }
            if (r > l) return true
            if (r < l) return false
        }
        return false
    }
}
