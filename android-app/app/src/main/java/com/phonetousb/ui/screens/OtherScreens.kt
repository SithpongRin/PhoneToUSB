package com.phonetousb.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.phonetousb.BuildConfig
import com.phonetousb.data.model.ReceiverInfo
import com.phonetousb.data.model.ReleaseManifest
import com.phonetousb.data.repository.ReceiverRepository
import com.phonetousb.data.repository.TransferRepository
import com.phonetousb.network.SignalingClient
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
                .padding(16.dp)
        ) {
            // Service Status Card
            Card(
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val statusColor = if (netState == "CONNECTED") GreenSuccess else AmberWarning
                    Icon(
                        imageVector = if (netState == "CONNECTED") Icons.Default.CloudDone else Icons.Default.CloudQueue,
                        contentDescription = null,
                        tint = statusColor,
                        modifier = Modifier.size(32.dp)
                    )
                    Spacer(modifier = Modifier.width(16.dp))
                    Column {
                        Text("Signaling Service", style = MaterialTheme.typography.titleMedium, color = TextLight)
                        Text(
                            if (netState == "CONNECTED") "Connected to Internet Coordination" else "Connecting...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = statusColor
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Active USB Drive Card
            Text("Active USB Drive", style = MaterialTheme.typography.titleMedium, color = TextLight)
            Spacer(modifier = Modifier.height(8.dp))

            if (selectedReceiver != null) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onNavigateToBrowser() }
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Usb, contentDescription = null, tint = SkyLight, modifier = Modifier.size(36.dp))
                        Spacer(modifier = Modifier.width(16.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(selectedReceiver!!.friendlyName, style = MaterialTheme.typography.titleMedium, color = TextLight)
                            val statusText = if (selectedReceiver!!.isOnline) "Ready & Online" else "Offline"
                            val statusColor = if (selectedReceiver!!.isOnline) GreenSuccess else RedDanger
                            Text(statusText, style = MaterialTheme.typography.bodyMedium, color = statusColor)
                        }
                        Button(
                            onClick = onNavigateToBrowser,
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary)
                        ) {
                            Text("Browse Files")
                        }
                    }
                }
            } else {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(Icons.Default.UsbOff, contentDescription = null, tint = TextMuted, modifier = Modifier.size(48.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("No USB Receiver Paired Yet", style = MaterialTheme.typography.titleMedium, color = TextLight)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Plug your USB into a Windows PC and pair it with this phone.", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = onNavigateToPairing,
                            colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary)
                        ) {
                            Icon(Icons.Default.QrCodeScanner, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Pair New USB Drive")
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Quick Navigation Shortcuts
            Text("Management", style = MaterialTheme.typography.titleMedium, color = TextLight)
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth()) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onNavigateToPairing() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = null, tint = SkyLight)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Pair USB", color = TextLight, fontWeight = FontWeight.Bold)
                    }
                }
                Spacer(modifier = Modifier.width(12.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onNavigateToDevices() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Devices, contentDescription = null, tint = SkyLight)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Receivers (${receivers.size})", color = TextLight, fontWeight = FontWeight.Bold)
                    }
                }
                Spacer(modifier = Modifier.width(12.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onNavigateToTransfers() }
                ) {
                    Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.SwapVert, contentDescription = null, tint = SkyLight)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Transfers", color = TextLight, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

// ==========================================
// 2. Pairing Screen (Token / QR Scanner)
// ==========================================
@Composable
fun PairingScreen(
    client: SignalingClient,
    receiverRepo: ReceiverRepository,
    onPairingSuccess: () -> Unit,
    onNavigateBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var receiverIdInput by remember { mutableStateOf("") }
    var tokenInput by remember { mutableStateOf("") }
    var friendlyNameInput by remember { mutableStateOf("Android Phone") }
    var isPairing by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf<String?>(null) }

    fun submitPairing(rid: String, tok: String) {
        if (rid.isBlank() || tok.isBlank()) return
        isPairing = true
        statusText = "Sending pairing request... Please click 'Approve' on your Windows PC screen."

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

    Scaffold(
        topBar = {
            AppTopBar(title = "Pair New USB Drive", canNavigateBack = true, onNavigateBack = onNavigateBack)
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(Icons.Default.QrCodeScanner, contentDescription = null, tint = SkyLight, modifier = Modifier.size(64.dp))
            Spacer(modifier = Modifier.height(16.dp))

            Text("Pair with Windows Receiver", style = MaterialTheme.typography.titleLarge, color = TextLight)
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                "Click 'Generate Pairing QR Code' on your Windows PC, then enter the details or scan.",
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
                modifier = Modifier.fillMaxWidth()
            ) {
                if (isPairing) {
                    CircularProgressIndicator(color = TextLight, modifier = Modifier.size(20.dp))
                } else {
                    Text("Send Pairing Request", fontWeight = FontWeight.Bold)
                }
            }

            statusText?.let {
                Spacer(modifier = Modifier.height(16.dp))
                Text(it, color = if (it.startsWith("Pairing failed")) RedDanger else SkyLight, style = MaterialTheme.typography.bodyMedium)
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
            AppTopBar(title = "Paired Receivers", canNavigateBack = true, onNavigateBack = onNavigateBack)
        },
        containerColor = DarkBackground
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            items(receivers) { r ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface)
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Usb, contentDescription = null, tint = SkyLight, modifier = Modifier.size(32.dp))
                        Spacer(modifier = Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(r.friendlyName, style = MaterialTheme.typography.titleMedium, color = TextLight)
                            Text(r.receiverId, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                        }
                        IconButton(onClick = { receiverToRevoke = r }) {
                            Icon(Icons.Default.Delete, contentDescription = "Remove", tint = RedDanger)
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
                title = "Transfer Activity",
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
            LazyColumn(modifier = Modifier.fillMaxSize().padding(padding)) {
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
    var statusText by remember { mutableStateOf("Current Version: v${BuildConfig.VERSION_NAME} (Build ${BuildConfig.VERSION_CODE})") }
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
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Official GitHub Releases", style = MaterialTheme.typography.titleMedium, color = TextLight)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(statusText, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { checkUpdates() },
                        enabled = !isChecking,
                        colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary)
                    ) {
                        Text("Check for Updates")
                    }
                }
            }

            releaseInfo?.let { release ->
                Spacer(modifier = Modifier.height(20.dp))
                Card(
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("Changelog (v${release.version})", style = MaterialTheme.typography.titleMedium, color = SkyLight)
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
                                colors = ButtonDefaults.buttonColors(containerColor = GreenSuccess)
                            ) {
                                Text(if (downloadProgress != null) "Downloading $downloadProgress%" else "Download & Install Update")
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
            Text("Coordination Service", style = MaterialTheme.typography.titleMedium, color = TextLight)
            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = urlText,
                onValueChange = { urlText = it },
                label = { Text("Backend WebSocket URL") },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(12.dp))

            Button(
                onClick = {
                    client.backendUrl = urlText
                    client.disconnect()
                    client.connect()
                },
                colors = ButtonDefaults.buttonColors(containerColor = SkyPrimary)
            ) {
                Text("Save and Reconnect")
            }
        }
    }
}
