package com.phonetousb.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.phonetousb.BuildConfig
import com.phonetousb.data.model.ReceiverInfo
import com.phonetousb.data.model.ReleaseManifest
import com.phonetousb.data.repository.ReceiverRepository
import com.phonetousb.data.repository.TransferRepository
import com.phonetousb.network.SignalingClient
import com.phonetousb.ui.camera.CameraScannerView
import com.phonetousb.ui.components.*
import com.phonetousb.ui.theme.*
import com.phonetousb.updater.GitHubUpdateManager
import kotlinx.coroutines.launch
import java.io.File

// ==========================================
// 1. Home Dashboard Screen
// ==========================================
@Composable
fun HomeScreen(
    receiverRepo: ReceiverRepository,
    client: SignalingClient,
    updateManager: GitHubUpdateManager? = null,
    onNavigateToBrowser: () -> Unit,
    onNavigateToPairing: () -> Unit,
    onNavigateToDevices: () -> Unit,
    onNavigateToTransfers: () -> Unit,
    onNavigateToUpdates: () -> Unit,
    onNavigateToSettings: () -> Unit
) {
    val receivers by receiverRepo.receivers.collectAsState()
    val selectedReceiver by receiverRepo.selectedReceiver.collectAsState()
    val netState by client.connectionState.collectAsState()
    var availableUpdateVer by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        if (updateManager != null) {
            try {
                val manifest = updateManager.checkForUpdates()
                if (updateManager.isNewerVersion(manifest.version, BuildConfig.VERSION_NAME)) {
                    availableUpdateVer = manifest.version
                }
            } catch (_: Exception) {}
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(
                title = "PhoneToUSB",
                actions = {
                    IconButton(onClick = onNavigateToUpdates) {
                        Icon(Icons.Default.SystemUpdate, contentDescription = "Updates", tint = TextLight)
                    }
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings", tint = TextLight)
                    }
                }
            )
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 12.dp)
        ) {
            // Live Connection Status Pill Card
            Card(
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val statusColor = if (netState == "CONNECTED") GreenSuccess else AmberWarning
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(statusColor)
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (netState == "CONNECTED") "Online — Coordination Ready" else "Connecting...",
                            style = MaterialTheme.typography.titleMedium,
                            color = TextLight,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = if (netState == "CONNECTED") "Global WebRTC and Relay standby" else "Re-establishing connection",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextMuted
                        )
                    }
                    Icon(
                        imageVector = if (netState == "CONNECTED") Icons.Default.CloudDone else Icons.Default.CloudQueue,
                        contentDescription = null,
                        tint = statusColor,
                        modifier = Modifier.size(28.dp)
                    )
                }
            }

            // In-App Update Alert Banner (if update found)
            availableUpdateVer?.let { newVer ->
                Spacer(modifier = Modifier.height(14.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF0F2D4A)),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, SkyLight, RoundedCornerShape(16.dp))
                        .clickable { onNavigateToUpdates() }
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(SkyPrimary),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.DownloadForOffline, contentDescription = null, tint = TextLight, modifier = Modifier.size(24.dp))
                        }
                        Spacer(modifier = Modifier.width(14.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                "New Version v$newVer Ready",
                                color = TextLight,
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleMedium
                            )
                            Text(
                                "Tap here to update directly in-app",
                                color = SkyLight,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                        Icon(Icons.Default.ChevronRight, contentDescription = null, tint = SkyLight)
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Authoritative USB Storage Card
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "AUTHORITATIVE USB DRIVE",
                    style = MaterialTheme.typography.bodyMedium,
                    color = SkyLight,
                    fontWeight = FontWeight.Bold
                )
            }
            Spacer(modifier = Modifier.height(8.dp))

            if (selectedReceiver != null) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
                        .clickable { onNavigateToBrowser() }
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(44.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(Color(0xFF0F2338)),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Default.Usb, contentDescription = null, tint = SkyLight, modifier = Modifier.size(26.dp))
                            }
                            Spacer(modifier = Modifier.width(16.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    selectedReceiver!!.friendlyName,
                                    style = MaterialTheme.typography.titleLarge,
                                    color = TextLight,
                                    fontWeight = FontWeight.Bold
                                )
                                val isOnline = selectedReceiver!!.isOnline
                                Text(
                                    text = if (isOnline) "Ready & Accessible over Internet" else "Receiver Offline (PC asleep or stopped)",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (isOnline) GreenSuccess else RedDanger,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(16.dp))

                        Button(
                            onClick = onNavigateToBrowser,
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.FolderOpen, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Browse Live USB Files", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            } else {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Box(
                            modifier = Modifier
                                .size(56.dp)
                                .clip(CircleShape)
                                .background(Color(0xFF1E2838)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(Icons.Default.UsbOff, contentDescription = null, tint = TextMuted, modifier = Modifier.size(32.dp))
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        Text("No Paired USB Drive", style = MaterialTheme.typography.titleMedium, color = TextLight, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            "Insert USB into your Windows PC and pair using camera QR scanner.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextMuted
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = onNavigateToPairing,
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Icon(Icons.Default.QrCodeScanner, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Scan QR to Pair USB", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Quick Access Action Grid
            Text(
                "QUICK ACTIONS",
                style = MaterialTheme.typography.bodyMedium,
                color = SkyLight,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth()) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .weight(1f)
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(14.dp))
                        .clickable { onNavigateToPairing() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = null, tint = SkyLight, modifier = Modifier.size(28.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Scan QR", color = TextLight, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("Pair new drive", color = TextMuted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Spacer(modifier = Modifier.width(12.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .weight(1f)
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(14.dp))
                        .clickable { onNavigateToDevices() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Devices, contentDescription = null, tint = SkyLight, modifier = Modifier.size(28.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Drives (${receivers.size})", color = TextLight, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("Manage paired", color = TextMuted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Spacer(modifier = Modifier.width(12.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .weight(1f)
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(14.dp))
                        .clickable { onNavigateToTransfers() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.SwapVert, contentDescription = null, tint = SkyLight, modifier = Modifier.size(28.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Transfers", color = TextLight, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("Queues & history", color = TextMuted, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

// ==========================================
// 2. Camera QR Code Scanner & Pairing Screen
// ==========================================
@Composable
fun PairingScreen(
    client: SignalingClient,
    receiverRepo: ReceiverRepository,
    onPairingSuccess: () -> Unit,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        )
    }

    var isManualEntry by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasCameraPermission = isGranted
        if (isGranted) {
            isManualEntry = false
        }
    }

    var serverUrlInput by remember { mutableStateOf(client.backendUrl) }
    var receiverIdInput by remember { mutableStateOf("") }
    var tokenInput by remember { mutableStateOf("") }
    var friendlyNameInput by remember { mutableStateOf("My Android Phone") }
    var isPairing by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf<String?>(null) }
    var lastScannedData by remember { mutableStateOf<String?>(null) }

    fun submitPairing(rid: String, tok: String, customBackend: String? = null) {
        if (rid.isBlank() || tok.isBlank() || isPairing) return
        isPairing = true
        statusText = "Connecting to coordination server..."

        scope.launch {
            if (!customBackend.isNullOrBlank() && customBackend != client.backendUrl) {
                client.backendUrl = customBackend
                client.disconnect()
            }

            val isConnected = client.ensureConnected(7000)
            if (!isConnected) {
                statusText = "Cannot reach server at ${client.backendUrl}. Check Wi-Fi/Internet connection."
                isPairing = false
                return@launch
            }

            statusText = "Sending pairing request... Please click 'Approve' on your laptop."
            val (success, resultMsg) = client.sendPairingRequest(rid.trim(), tok.trim(), friendlyNameInput)
            isPairing = false
            if (success) {
                receiverRepo.addReceiver(
                    ReceiverInfo(
                        receiverId = rid.trim(),
                        friendlyName = resultMsg,
                        publicKeyBase64 = "",
                        isOnline = true
                    )
                )
                statusText = "Approved! Connecting to USB storage..."
                onPairingSuccess()
            } else {
                statusText = "Pairing failed: $resultMsg"
            }
        }
    }

    // Auto-parse scanned QR code JSON
    fun handleScannedQrCode(qrData: String) {
        if (isPairing || qrData == lastScannedData) return
        lastScannedData = qrData

        try {
            val json = Gson().fromJson(qrData, JsonObject::class.java)
            val rid = json.get("rid")?.asString
            val tok = json.get("token")?.asString
            val backend = json.get("backend")?.asString

            if (!rid.isNullOrBlank() && !tok.isNullOrBlank()) {
                submitPairing(rid, tok, backend)
            }
        } catch (_: Exception) {
            // If QR is raw token or plain text
            if (qrData.contains(":")) {
                val parts = qrData.split(":")
                submitPairing(parts[0], parts[1])
            }
        }
    }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(
                title = "Pair USB Drive",
                canNavigateBack = true,
                onNavigateBack = onNavigateBack,
                actions = {
                    TextButton(onClick = { isManualEntry = !isManualEntry }) {
                        Text(if (isManualEntry) "Scan Camera" else "Manual Entry", color = SkyLight, fontWeight = FontWeight.Bold)
                    }
                }
            )
        },
        containerColor = DarkBackground
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            if (!isManualEntry && hasCameraPermission) {
                // Live Camera Viewfinder
                CameraScannerView(
                    onQrCodeDetected = { scannedText ->
                        handleScannedQrCode(scannedText)
                    },
                    modifier = Modifier.fillMaxSize()
                )

                // Overlay Instructions at bottom
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(24.dp)
                        .background(Color(0xEE0F172A), RoundedCornerShape(16.dp))
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Point camera at the QR code on your Windows screen",
                        style = MaterialTheme.typography.titleMedium,
                        color = TextLight,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Pairing requires only one scan. Once approved, connection is automatic.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )

                    if (isPairing) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            CircularProgressIndicator(
                                color = SkyLight,
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.5.dp
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "Waiting for laptop approval...",
                                color = SkyLight,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    statusText?.let {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = it,
                            color = if (it.startsWith("Pairing failed") || it.startsWith("Cannot reach")) RedDanger else SkyLight,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    if (!isPairing && statusText != null && (statusText!!.startsWith("Pairing failed") || statusText!!.startsWith("Cannot reach"))) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(
                            onClick = {
                                lastScannedData = null
                                statusText = null
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("Scan Again", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            } else {
                // Manual Entry Form Fallback
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(Icons.Default.QrCodeScanner, contentDescription = null, tint = SkyLight, modifier = Modifier.size(56.dp))
                    Spacer(modifier = Modifier.height(12.dp))

                    Text("Manual Device Pairing", style = MaterialTheme.typography.titleLarge, color = TextLight, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "If camera is unavailable, enter the Receiver ID and single-use token shown on your PC.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    OutlinedTextField(
                        value = serverUrlInput,
                        onValueChange = { serverUrlInput = it },
                        label = { Text("Wi-Fi Server URL (e.g. ws://10.55.2.164:8000/ws/client)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = receiverIdInput,
                        onValueChange = { receiverIdInput = it },
                        label = { Text("Receiver ID (e.g. p2u-rcv-xxxx)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = tokenInput,
                        onValueChange = { tokenInput = it },
                        label = { Text("Single-use Pairing Token") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = friendlyNameInput,
                        onValueChange = { friendlyNameInput = it },
                        label = { Text("Phone Display Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(20.dp))

                    Button(
                        onClick = { submitPairing(receiverIdInput, tokenInput, serverUrlInput) },
                        enabled = !isPairing && receiverIdInput.isNotBlank() && tokenInput.isNotBlank(),
                        colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        if (isPairing) {
                            CircularProgressIndicator(color = TextLight, modifier = Modifier.size(20.dp))
                        } else {
                            Text("Submit Pairing Request", fontWeight = FontWeight.Bold)
                        }
                    }

                    if (!hasCameraPermission) {
                        Spacer(modifier = Modifier.height(12.dp))
                        OutlinedButton(
                            onClick = { permissionLauncher.launch(Manifest.permission.CAMERA) },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Grant Camera Permission to Scan")
                        }
                    }

                    statusText?.let {
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(it, color = if (it.startsWith("Pairing failed")) RedDanger else SkyLight, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

// ==========================================
// 3. Paired Devices Screen
// ==========================================
@Composable
fun DevicesScreen(
    receiverRepo: ReceiverRepository,
    onNavigateBack: () -> Unit
) {
    val receivers by receiverRepo.receivers.collectAsState()
    var receiverToRevoke by remember { mutableStateOf<ReceiverInfo?>(null) }

    Scaffold(
        topBar = {
            AppTopBar(title = "Paired USB Receivers", canNavigateBack = true, onNavigateBack = onNavigateBack)
        },
        containerColor = DarkBackground
    ) { padding ->
        if (receivers.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("No paired USB drives found.", color = TextMuted)
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(vertical = 8.dp)
            ) {
                items(receivers) { r ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 6.dp)
                            .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(14.dp)),
                        colors = CardDefaults.cardColors(containerColor = DarkSurface),
                        shape = RoundedCornerShape(14.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(40.dp)
                                    .clip(RoundedCornerShape(10.dp))
                                    .background(Color(0xFF0F2338)),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Default.Usb, contentDescription = null, tint = SkyLight, modifier = Modifier.size(24.dp))
                            }
                            Spacer(modifier = Modifier.width(14.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(r.friendlyName, style = MaterialTheme.typography.titleMedium, color = TextLight, fontWeight = FontWeight.Bold)
                                Text(r.receiverId, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                            }
                            IconButton(onClick = { receiverToRevoke = r }) {
                                Icon(Icons.Default.Delete, contentDescription = "Unpair", tint = RedDanger)
                            }
                        }
                    }
                }
            }
        }
    }

    receiverToRevoke?.let { r ->
        ConfirmationDialog(
            title = "Unpair USB Drive",
            message = "Remove pairing for '${r.friendlyName}'? You will need to re-scan the QR code to connect again.",
            onConfirm = {
                receiverRepo.removeReceiver(r.receiverId)
                receiverToRevoke = null
            },
            onDismiss = { receiverToRevoke = null }
        )
    }
}

// ==========================================
// 4. Transfers Screen
// ==========================================
@Composable
fun TransfersScreen(
    transferRepo: TransferRepository,
    onNavigateBack: () -> Unit
) {
    val tasks by transferRepo.tasks.collectAsState()

    Scaffold(
        topBar = {
            AppTopBar(
                title = "Transfer Queues & History",
                canNavigateBack = true,
                onNavigateBack = onNavigateBack,
                actions = {
                    IconButton(onClick = { transferRepo.clearCompleted() }) {
                        Icon(Icons.Default.ClearAll, contentDescription = "Clear", tint = TextLight)
                    }
                }
            )
        },
        containerColor = DarkBackground
    ) { padding ->
        if (tasks.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("No transfers recorded yet.", color = TextMuted)
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(vertical = 8.dp)
            ) {
                items(tasks) { task ->
                    TransferItemView(task = task)
                }
            }
        }
    }
}

// ==========================================
// 5. In-App Updates Screen
// ==========================================
@Composable
fun UpdatesScreen(
    updateManager: GitHubUpdateManager,
    onNavigateBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var isChecking by remember { mutableStateOf(false) }
    var releaseInfo by remember { mutableStateOf<ReleaseManifest?>(null) }
    var statusText by remember { mutableStateOf("Installed: v${BuildConfig.VERSION_NAME} (Build ${BuildConfig.VERSION_CODE})") }
    var isDownloading by remember { mutableStateOf(false) }
    var downloadStatusText by remember { mutableStateOf<String?>(null) }
    var downloadPercent by remember { mutableStateOf(0) }
    var hasInstallPermission by remember { mutableStateOf(updateManager.hasInstallPermission()) }
    var downloadedApk by remember { mutableStateOf<File?>(null) }

    fun checkUpdates() {
        isChecking = true
        statusText = "Checking latest release..."
        scope.launch {
            val manifest = updateManager.checkForUpdates()
            isChecking = false
            releaseInfo = manifest
            if (updateManager.isNewerVersion(manifest.version, BuildConfig.VERSION_NAME)) {
                statusText = "New version available: v${manifest.version}"
            } else {
                statusText = "Version v${BuildConfig.VERSION_NAME} is installed. You can reinstall or update anytime."
            }
        }
    }

    LaunchedEffect(Unit) {
        checkUpdates()
    }

    fun startInAppUpdate() {
        val dlUrl = releaseInfo?.android?.downloadUrl ?: "https://github.com/SithpongRin/PhoneToUSB/raw/main/dist/PhoneToUSB.apk"

        if (!updateManager.hasInstallPermission()) {
            updateManager.requestInstallPermission()
            statusText = "Please allow 'Install unknown apps' permission in Settings, then tap Install."
            return
        }

        isDownloading = true
        downloadStatusText = "Connecting and downloading PhoneToUSB.apk..."
        scope.launch {
            val apk = updateManager.downloadAndVerifyApk(dlUrl, null) { percent, read, total ->
                downloadPercent = percent
                val readMb = String.format("%.1f", read / (1024.0 * 1024.0))
                val totalMb = if (total > 0) String.format("%.1f", total / (1024.0 * 1024.0)) else "19.9"
                downloadStatusText = "Downloading in-app: $percent% ($readMb MB / $totalMb MB)"
            }
            isDownloading = false
            if (apk != null) {
                downloadedApk = apk
                downloadStatusText = "Download complete! Opening Android installer..."
                val launched = updateManager.launchPackageInstaller(apk)
                if (!launched) {
                    hasInstallPermission = false
                    statusText = "Please grant permission to install unknown apps to finish."
                }
            } else {
                downloadStatusText = "Download failed. Please check internet connection."
            }
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(title = "In-App Updates", canNavigateBack = true, onNavigateBack = onNavigateBack)
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp)
        ) {
            // Version Info Card
            Card(
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text("Official Release Channel", style = MaterialTheme.typography.titleMedium, color = TextLight, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(statusText, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    Spacer(modifier = Modifier.height(16.dp))

                    Row(modifier = Modifier.fillMaxWidth()) {
                        Button(
                            onClick = { checkUpdates() },
                            enabled = !isChecking && !isDownloading,
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Text(if (isChecking) "Checking..." else "Check for Updates", fontWeight = FontWeight.Bold)
                        }

                        Spacer(modifier = Modifier.width(12.dp))

                        if (downloadedApk != null && !isDownloading) {
                            Button(
                                onClick = { updateManager.launchPackageInstaller(downloadedApk!!) },
                                colors = ButtonDefaults.buttonColors(containerColor = GreenSuccess),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Text("Install Downloaded APK", fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }

            // Unknown Sources Permission Alert if needed
            if (!hasInstallPermission) {
                Spacer(modifier = Modifier.height(16.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF2C2411)),
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, AmberWarning, RoundedCornerShape(14.dp))
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Security, contentDescription = null, tint = AmberWarning, modifier = Modifier.size(24.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Permission Required", color = TextLight, fontWeight = FontWeight.Bold)
                        }
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            "Android requires permission to allow PhoneToUSB to update directly inside the app.",
                            color = TextMuted,
                            style = MaterialTheme.typography.bodySmall
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = {
                                updateManager.requestInstallPermission()
                                hasInstallPermission = updateManager.hasInstallPermission()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = AmberWarning),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("Allow In-App Installation in Settings", color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            // In-App 1-Click Update Card
            Spacer(modifier = Modifier.height(20.dp))
            Card(
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    val targetVer = releaseInfo?.version ?: "Latest Build"
                    Text("Direct In-App Upgrade", style = MaterialTheme.typography.titleMedium, color = SkyLight, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        "Downloads PhoneToUSB.apk directly and triggers installation in 1 click without going to GitHub in your browser.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextLight
                    )

                    releaseInfo?.changelog?.let { cl ->
                        if (cl.isNotBlank()) {
                            Spacer(modifier = Modifier.height(10.dp))
                            Text("Changelog: $cl", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    if (isDownloading) {
                        LinearProgressIndicator(
                            progress = { downloadPercent / 100f },
                            modifier = Modifier.fillMaxWidth().height(8.dp),
                            color = SkyLight,
                            trackColor = Color(0xFF1E293B)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        downloadStatusText?.let {
                            Text(it, color = SkyLight, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                        }
                    } else {
                        Button(
                            onClick = { startInAppUpdate() },
                            colors = ButtonDefaults.buttonColors(containerColor = GreenSuccess),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(Icons.Default.DownloadForOffline, contentDescription = null, modifier = Modifier.size(20.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                "Download & Install Update (In-App)",
                                fontWeight = FontWeight.Bold
                            )
                        }

                        downloadStatusText?.let {
                            Spacer(modifier = Modifier.height(10.dp))
                            Text(it, color = if (it.startsWith("Download failed")) RedDanger else SkyLight, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }
    }
}

// ==========================================
// 6. Settings Screen
// ==========================================
@Composable
fun SettingsScreen(
    client: SignalingClient,
    onNavigateBack: () -> Unit
) {
    var urlText by remember { mutableStateOf(client.backendUrl) }

    Scaffold(
        topBar = {
            AppTopBar(title = "Settings", canNavigateBack = true, onNavigateBack = onNavigateBack)
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp)
        ) {
            Card(
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text("Internet Coordination Server", style = MaterialTheme.typography.titleMedium, color = TextLight, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("Configure public WebSocket signaling address.", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    Spacer(modifier = Modifier.height(16.dp))

                    OutlinedTextField(
                        value = urlText,
                        onValueChange = { urlText = it },
                        label = { Text("Backend WebSocket URL") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = {
                            client.backendUrl = urlText
                            client.disconnect()
                            client.connect()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Text("Save and Reconnect", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}
