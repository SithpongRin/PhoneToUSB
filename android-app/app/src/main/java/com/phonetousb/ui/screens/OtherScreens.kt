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

// ==========================================
// 1. Home Dashboard Screen
// ==========================================
@Composable
fun HomeScreen(
    receiverRepo: ReceiverRepository,
    client: SignalingClient,
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

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasCameraPermission = isGranted
    }

    var isManualEntry by remember { mutableStateOf(!hasCameraPermission) }
    var receiverIdInput by remember { mutableStateOf("") }
    var tokenInput by remember { mutableStateOf("") }
    var friendlyNameInput by remember { mutableStateOf("My Android Phone") }
    var isPairing by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf<String?>(null) }

    fun submitPairing(rid: String, tok: String) {
        if (rid.isBlank() || tok.isBlank() || isPairing) return
        isPairing = true
        statusText = "Sending pairing request... Please click 'Approve' on your laptop."

        scope.launch {
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
                onPairingSuccess()
            } else {
                statusText = "Pairing failed: $resultMsg"
            }
        }
    }

    // Auto-parse scanned QR code JSON
    fun handleScannedQrCode(qrData: String) {
        try {
            val json = Gson().fromJson(qrData, JsonObject::class.java)
            val rid = json.get("rid")?.asString
            val tok = json.get("token")?.asString
            val backend = json.get("backend")?.asString

            if (!backend.isNullOrBlank()) {
                client.backendUrl = backend
                client.disconnect()
                client.connect()
            }

            if (!rid.isNullOrBlank() && !tok.isNullOrBlank()) {
                submitPairing(rid, tok)
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
                        .background(Color(0xCC0F172A), RoundedCornerShape(16.dp))
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

                    statusText?.let {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = it,
                            color = if (it.startsWith("Pairing failed")) RedDanger else SkyLight,
                            fontWeight = FontWeight.Bold
                        )
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

                    Spacer(modifier = Modifier.height(24.dp))

                    OutlinedTextField(
                        value = receiverIdInput,
                        onValueChange = { receiverIdInput = it },
                        label = { Text("Receiver ID (e.g. p2u-rcv-xxxx)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = tokenInput,
                        onValueChange = { tokenInput = it },
                        label = { Text("Single-use Pairing Token") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = friendlyNameInput,
                        onValueChange = { friendlyNameInput = it },
                        label = { Text("Phone Display Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Spacer(modifier = Modifier.height(24.dp))

                    Button(
                        onClick = { submitPairing(receiverIdInput, tokenInput) },
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
// 5. GitHub Updates Screen
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
    var downloadProgress by remember { mutableStateOf<Int?>(null) }

    fun checkUpdates() {
        isChecking = true
        statusText = "Checking official GitHub repository for updates..."
        scope.launch {
            val manifest = updateManager.checkForUpdates()
            isChecking = false
            if (manifest != null) {
                releaseInfo = manifest
                statusText = "New version available: v${manifest.version}"
            } else {
                statusText = "PhoneToUSB is up to date (v${BuildConfig.VERSION_NAME})."
            }
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(title = "App Updates", canNavigateBack = true, onNavigateBack = onNavigateBack)
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
                    Text("Official GitHub Releases", style = MaterialTheme.typography.titleMedium, color = TextLight, fontWeight = FontWeight.Bold)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(statusText, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { checkUpdates() },
                        enabled = !isChecking,
                        colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Text("Check for Updates", fontWeight = FontWeight.Bold)
                    }
                }
            }

            releaseInfo?.let { release ->
                Spacer(modifier = Modifier.height(20.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, Color(0xFF2A374A), RoundedCornerShape(16.dp))
                ) {
                    Column(modifier = Modifier.padding(18.dp)) {
                        Text("Changelog (v${release.version})", style = MaterialTheme.typography.titleMedium, color = SkyLight, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(release.changelog, style = MaterialTheme.typography.bodyMedium, color = TextLight)
                        Spacer(modifier = Modifier.height(16.dp))

                        val dlUrl = release.android.downloadUrl
                        if (!dlUrl.isNullOrBlank()) {
                            Button(
                                onClick = {
                                    scope.launch {
                                        val apk = updateManager.downloadAndVerifyApk(dlUrl, null) { progress ->
                                            downloadProgress = progress
                                        }
                                        if (apk != null) {
                                            updateManager.launchPackageInstaller(apk)
                                        }
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = GreenSuccess),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Text(
                                    if (downloadProgress != null) "Downloading $downloadProgress%" else "Download & Install Update",
                                    fontWeight = FontWeight.Bold
                                )
                            }
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
