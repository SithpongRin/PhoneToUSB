package com.phonetousb.network

import android.content.Context
import android.util.Base64
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.phonetousb.data.model.*
import com.phonetousb.security.CryptoUtils
import com.phonetousb.security.KeyStoreManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.*
import java.io.File
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

class SignalingClient(private val context: Context, initialBackendUrl: String = "ws://10.55.2.164:8000/ws/client") {
    private val prefs = context.getSharedPreferences("phonetousb_prefs", Context.MODE_PRIVATE)

    private val client = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    var backendUrl: String = normalizeClientUrl(prefs.getString("backend_url", initialBackendUrl) ?: initialBackendUrl)
        set(value) {
            val normalized = normalizeClientUrl(value)
            field = normalized
            prefs.edit().putString("backend_url", normalized).apply()
        }

    private var webSocket: WebSocket? = null
    private val gson = Gson()
    private val pendingRequests = ConcurrentHashMap<String, CompletableDeferred<JsonObject>>()

    private val _connectionState = MutableStateFlow("DISCONNECTED")
    val connectionState: StateFlow<String> = _connectionState

    private val _receiverPresence = MutableStateFlow<Map<String, Boolean>>(emptyMap())
    val receiverPresence: StateFlow<Map<String, Boolean>> = _receiverPresence

    val clientId: String by lazy { KeyStoreManager.getOrCreateClientId(context) }

    fun normalizeClientUrl(url: String): String {
        var clean = url.trim()
        if (!clean.startsWith("ws://") && !clean.startsWith("wss://")) {
            clean = if (clean.startsWith("https://")) {
                clean.replaceFirst("https://", "wss://")
            } else if (clean.startsWith("http://")) {
                clean.replaceFirst("http://", "ws://")
            } else {
                "ws://$clean"
            }
        }
        // Ensure path points to /ws/client
        if (clean.endsWith("/ws/receiver")) {
            clean = clean.replace("/ws/receiver", "/ws/client")
        } else if (!clean.endsWith("/ws/client")) {
            clean = clean.trimEnd('/') + "/ws/client"
        }
        return clean
    }

    fun connect() {
        if (_connectionState.value == "CONNECTED" || _connectionState.value == "CONNECTING") return

        _connectionState.value = "CONNECTING"
        try {
            val request = Request.Builder().url(backendUrl).build()
            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(ws: WebSocket, response: Response) {
                    _connectionState.value = "CONNECTED"
                    val hello = JsonObject().apply {
                        addProperty("client_id", clientId)
                    }
                    ws.send(hello.toString())
                }

                override fun onMessage(ws: WebSocket, text: String) {
                    handleIncomingMessage(text)
                }

                override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                    _connectionState.value = "DISCONNECTED"
                }

                override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                    _connectionState.value = "ERROR"
                }
            })
        } catch (_: Exception) {
            _connectionState.value = "ERROR"
        }
    }

    fun disconnect() {
        try {
            webSocket?.close(1000, "User disconnect")
        } catch (_: Exception) {}
        webSocket = null
        _connectionState.value = "DISCONNECTED"
    }

    suspend fun ensureConnected(timeoutMs: Long = 6000): Boolean {
        if (_connectionState.value == "CONNECTED") return true

        disconnect()
        connect()

        return withTimeoutOrNull(timeoutMs) {
            while (_connectionState.value != "CONNECTED") {
                if (_connectionState.value == "ERROR") {
                    return@withTimeoutOrNull false
                }
                delay(150)
            }
            true
        } ?: false
    }

    private fun handleIncomingMessage(text: String) {
        try {
            val json = gson.fromJson(text, JsonObject::class.java)
            val action = json.get("action")?.asString

            if (action == "PRESENCE_RESPONSE") {
                val presenceObj = json.getAsJsonObject("presence")
                val map = mutableMapOf<String, Boolean>()
                presenceObj?.keySet()?.forEach { rid ->
                    map[rid] = presenceObj.get(rid)?.asBoolean ?: false
                }
                _receiverPresence.value = map
            } else if (action == "PAIRING_RESULT") {
                val reqId = json.get("request_id")?.asString
                if (!reqId.isNullOrBlank() && pendingRequests.containsKey(reqId)) {
                    pendingRequests.remove(reqId)?.complete(json)
                }
                pendingRequests.remove("PAIRING_PENDING")?.complete(json)
            } else if (json.has("request_id")) {
                val reqId = json.get("request_id").asString
                pendingRequests.remove(reqId)?.complete(json)
            }
        } catch (_: Exception) {}
    }

    suspend fun queryPresence(receiverIds: List<String>) {
        if (!ensureConnected(2000)) return
        val msg = JsonObject().apply {
            addProperty("action", "QUERY_PRESENCE")
            add("receiver_ids", gson.toJsonTree(receiverIds))
        }
        webSocket?.send(msg.toString())
    }

    suspend fun sendPairingRequest(receiverId: String, token: String, clientName: String): Pair<Boolean, String> {
        // Ensure WebSocket is alive and ready
        val isReady = ensureConnected(7000)
        if (!isReady) {
            return Pair(false, "Cannot connect to server ($backendUrl). Ensure laptop and phone are on the same Wi-Fi/Hotspot.")
        }

        // Small delay to ensure initial client_id HELLO is processed first
        delay(150)

        val reqId = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<JsonObject>()
        pendingRequests[reqId] = deferred
        pendingRequests["PAIRING_PENDING"] = deferred

        val msg = JsonObject().apply {
            addProperty("action", "PAIRING_REQUEST")
            addProperty("request_id", reqId)
            addProperty("receiver_id", receiverId)
            addProperty("token", token)
            addProperty("client_id", clientId)
            addProperty("client_name", clientName)
            addProperty("client_pubkey", KeyStoreManager.getPublicKeyBase64(context))
        }

        val sent = webSocket?.send(msg.toString()) ?: false
        if (!sent) {
            pendingRequests.remove(reqId)
            pendingRequests.remove("PAIRING_PENDING")
            return Pair(false, "Failed to send packet over network")
        }

        return try {
            val res = withTimeout(60000) { deferred.await() }
            pendingRequests.remove(reqId)
            pendingRequests.remove("PAIRING_PENDING")
            val status = res.get("status")?.asString
            if (status == "APPROVED") {
                Pair(true, res.get("receiver_friendly_name")?.asString ?: "PhoneToUSB Drive")
            } else {
                Pair(false, res.get("reason")?.asString ?: "Pairing was rejected or timed out")
            }
        } catch (e: Exception) {
            pendingRequests.remove(reqId)
            pendingRequests.remove("PAIRING_PENDING")
            Pair(false, "Waiting timed out. Please click 'Approve' promptly on your laptop.")
        }
    }

    suspend fun listUsbDirectory(
        receiverId: String,
        path: String,
        sortBy: String = "name",
        sortAsc: Boolean = true,
        search: String = ""
    ): UsbDirectoryResponse? {
        if (!ensureConnected(3000)) return null

        val reqId = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<JsonObject>()
        pendingRequests[reqId] = deferred

        val params = JsonObject().apply {
            addProperty("path", path)
            addProperty("sort_by", sortBy)
            addProperty("sort_asc", sortAsc)
            addProperty("search", search)
        }
        val msg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "FS_LIST")
            addProperty("request_id", reqId)
            addProperty("receiver_id", receiverId)
            add("params", params)
        }

        webSocket?.send(msg.toString())
        return try {
            val res = withTimeout(15000) { deferred.await() }
            if (res.get("success")?.asBoolean == true) {
                val data = res.getAsJsonObject("data")
                gson.fromJson(data, UsbDirectoryResponse::class.java)
            } else null
        } catch (_: Exception) {
            null
        }
    }

    suspend fun createDirectory(receiverId: String, path: String): Boolean {
        if (!ensureConnected(3000)) return false
        val reqId = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<JsonObject>()
        pendingRequests[reqId] = deferred

        val params = JsonObject().apply { addProperty("path", path) }
        val msg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "FS_MKDIR")
            addProperty("request_id", reqId)
            addProperty("receiver_id", receiverId)
            add("params", params)
        }
        webSocket?.send(msg.toString())
        return try {
            withTimeout(10000) { deferred.await() }.get("success")?.asBoolean == true
        } catch (_: Exception) { false }
    }

    suspend fun renameItem(receiverId: String, oldPath: String, newName: String): Boolean {
        if (!ensureConnected(3000)) return false
        val reqId = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<JsonObject>()
        pendingRequests[reqId] = deferred

        val params = JsonObject().apply {
            addProperty("old_path", oldPath)
            addProperty("new_name", newName)
        }
        val msg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "FS_RENAME")
            addProperty("request_id", reqId)
            addProperty("receiver_id", receiverId)
            add("params", params)
        }
        webSocket?.send(msg.toString())
        return try {
            withTimeout(10000) { deferred.await() }.get("success")?.asBoolean == true
        } catch (_: Exception) { false }
    }

    suspend fun deleteItem(receiverId: String, path: String, recursive: Boolean = false): Boolean {
        if (!ensureConnected(3000)) return false
        val reqId = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<JsonObject>()
        pendingRequests[reqId] = deferred

        val params = JsonObject().apply {
            addProperty("path", path)
            addProperty("recursive", recursive)
        }
        val msg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "FS_DELETE")
            addProperty("request_id", reqId)
            addProperty("receiver_id", receiverId)
            add("params", params)
        }
        webSocket?.send(msg.toString())
        return try {
            withTimeout(10000) { deferred.await() }.get("success")?.asBoolean == true
        } catch (_: Exception) { false }
    }

    suspend fun uploadFile(
        receiverId: String,
        file: File,
        targetRelativePath: String,
        onProgress: (bytesSent: Long, total: Long) -> Unit
    ): Boolean = withContext(Dispatchers.IO) {
        if (!ensureConnected(5000)) return@withContext false

        val transferId = UUID.randomUUID().toString()
        val totalBytes = file.length()
        val sha256 = CryptoUtils.calculateFileSha256(file)

        // 1. Start Upload
        val startReqId = UUID.randomUUID().toString()
        val startDeferred = CompletableDeferred<JsonObject>()
        pendingRequests[startReqId] = startDeferred

        val startMsg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "TRANSFER_START")
            addProperty("request_id", startReqId)
            addProperty("receiver_id", receiverId)
            add("params", JsonObject().apply {
                addProperty("transfer_id", transferId)
                addProperty("relative_path", targetRelativePath)
                addProperty("file_size", totalBytes)
                addProperty("sha256", sha256)
                addProperty("conflict_policy", "RENAME")
            })
        }
        webSocket?.send(startMsg.toString())
        val startRes = try {
            withTimeout(12000) { startDeferred.await() }
        } catch (_: Exception) { return@withContext false }

        if (startRes.get("success")?.asBoolean != true) return@withContext false

        // 2. Stream Chunks (64 KB)
        val chunkSize = 65536
        var chunkIndex = 0
        var sentBytes = 0L

        file.inputStream().use { input ->
            val buffer = ByteArray(chunkSize)
            var bytesRead: Int
            while (input.read(buffer).also { bytesRead = it } != -1) {
                val chunkData = if (bytesRead == chunkSize) buffer else buffer.copyOf(bytesRead)
                val b64 = Base64.encodeToString(chunkData, Base64.NO_WRAP)

                val chunkMsg = JsonObject().apply {
                    addProperty("action", "DATA_FRAME")
                    addProperty("command", "TRANSFER_CHUNK")
                    addProperty("receiver_id", receiverId)
                    add("params", JsonObject().apply {
                        addProperty("transfer_id", transferId)
                        addProperty("chunk_index", chunkIndex)
                        addProperty("chunk_data_b64", b64)
                    })
                }
                webSocket?.send(chunkMsg.toString())
                sentBytes += bytesRead
                chunkIndex++
                onProgress(sentBytes, totalBytes)
                delay(5)
            }
        }

        // 3. Finish Upload
        val finReqId = UUID.randomUUID().toString()
        val finDeferred = CompletableDeferred<JsonObject>()
        pendingRequests[finReqId] = finDeferred

        val finMsg = JsonObject().apply {
            addProperty("action", "DATA_FRAME")
            addProperty("command", "TRANSFER_FINISH")
            addProperty("request_id", finReqId)
            addProperty("receiver_id", receiverId)
            add("params", JsonObject().apply {
                addProperty("transfer_id", transferId)
            })
        }
        webSocket?.send(finMsg.toString())

        return@withContext try {
            val finRes = withTimeout(15000) { finDeferred.await() }
            finRes.get("success")?.asBoolean == true
        } catch (_: Exception) { false }
    }
}
