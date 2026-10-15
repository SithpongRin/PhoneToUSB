package com.phonetousb.data.model

import com.google.gson.annotations.SerializedName

data class UsbItem(
    @SerializedName("name") val name: String,
    @SerializedName("relative_path") val relativePath: String,
    @SerializedName("is_dir") val isDir: Boolean,
    @SerializedName("size") val size: Long,
    @SerializedName("modified_timestamp") val modifiedTimestamp: Long,
    @SerializedName("extension") val extension: String = ""
)

data class UsbDirectoryResponse(
    @SerializedName("current_path") val currentPath: String,
    @SerializedName("parent_path") val parentPath: String?,
    @SerializedName("total_items") val totalItems: Int,
    @SerializedName("page") val page: Int,
    @SerializedName("page_size") val pageSize: Int,
    @SerializedName("items") val items: List<UsbItem>
)

data class ReceiverInfo(
    val receiverId: String,
    val friendlyName: String,
    val publicKeyBase64: String,
    var isOnline: Boolean = false,
    val pairedAt: Long = System.currentTimeMillis(),
    var lastSeen: Long = System.currentTimeMillis()
)

enum class TransferDirection { UPLOAD, DOWNLOAD }
enum class TransferStatus { QUEUED, IN_PROGRESS, COMPLETED, FAILED, CANCELLED }

data class TransferTask(
    val transferId: String,
    val filename: String,
    val relativePath: String,
    val totalBytes: Long,
    var bytesTransferred: Long = 0,
    val direction: TransferDirection,
    var status: TransferStatus = TransferStatus.QUEUED,
    var error: String? = null,
    val timestamp: Long = System.currentTimeMillis()
)

data class ReleaseManifest(
    @SerializedName("version") val version: String,
    @SerializedName("changelog") val changelog: String,
    @SerializedName("android") val android: AndroidReleaseAsset
)

data class AndroidReleaseAsset(
    @SerializedName("version_code") val versionCode: Int,
    @SerializedName("version_name") val versionName: String,
    @SerializedName("filename") val filename: String,
    @SerializedName("sha256") val sha256: String,
    @SerializedName("download_url") val downloadUrl: String? = null
)
