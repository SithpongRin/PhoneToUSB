package com.phonetousb.ui.screens

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import com.phonetousb.data.model.ReceiverInfo
import com.phonetousb.data.model.UsbItem
import com.phonetousb.network.SignalingClient
import com.phonetousb.ui.components.*
import com.phonetousb.ui.theme.*
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UsbBrowserScreen(
    client: SignalingClient,
    selectedReceiver: ReceiverInfo?,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var currentPath by remember { mutableStateOf("") }
    var parentPath by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<UsbItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var searchQuery by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Dialog states
    var showCreateFolderDialog by remember { mutableStateOf(false) }
    var itemToRename by remember { mutableStateOf<UsbItem?>(null) }
    var itemToDelete by remember { mutableStateOf<UsbItem?>(null) }

    // Upload status
    var uploadStatus by remember { mutableStateOf<String?>(null) }

    fun refreshDirectory(path: String = currentPath) {
        if (selectedReceiver == null) return
        isLoading = true
        errorMessage = null
        scope.launch {
            val res = client.listUsbDirectory(selectedReceiver.receiverId, path, search = searchQuery)
            isLoading = false
            if (res != null) {
                items = res.items
                currentPath = res.currentPath
                parentPath = res.parentPath
            } else {
                errorMessage = "Failed to load directory. Receiver may be offline."
            }
        }
    }

    LaunchedEffect(selectedReceiver, currentPath) {
        refreshDirectory(currentPath)
    }

    // File picker for upload
    val filePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments()
    ) { uris: List<Uri> ->
        if (uris.isEmpty() || selectedReceiver == null) return@rememberLauncherForActivityResult

        scope.launch {
            uris.forEach { uri ->
                var displayName = "file_${System.currentTimeMillis()}"
                context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (cursor.moveToFirst() && nameIndex != -1) {
                        displayName = cursor.getString(nameIndex)
                    }
                }

                // Copy to temporary cache file
                val tempFile = File(context.cacheDir, displayName)
                context.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(tempFile).use { output ->
                        input.copyTo(output)
                    }
                }

                val targetPath = if (currentPath.isBlank()) displayName else "$currentPath/$displayName"
                uploadStatus = "Uploading $displayName..."

                val success = client.uploadFile(selectedReceiver.receiverId, tempFile, targetPath) { sent, total ->
                    uploadStatus = "Uploading $displayName: ${(sent * 100 / total)}%"
                }

                tempFile.delete()
                uploadStatus = if (success) "Upload completed: $displayName" else "Upload failed: $displayName"
            }
            refreshDirectory()
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(
                title = selectedReceiver?.friendlyName ?: "USB Browser",
                canNavigateBack = true,
                onNavigateBack = onNavigateBack,
                actions = {
                    IconButton(onClick = { refreshDirectory() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = TextLight)
                    }
                    IconButton(onClick = { showCreateFolderDialog = true }) {
                        Icon(Icons.Default.CreateNewFolder, contentDescription = "New Folder", tint = TextLight)
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { filePickerLauncher.launch(arrayOf("*/*")) },
                containerColor = SkyPrimary,
                contentColor = TextLight
            ) {
                Icon(Icons.Default.Upload, contentDescription = "Upload to USB")
            }
        },
        containerColor = DarkBackground
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Upload progress banner
            uploadStatus?.let { status ->
                Surface(
                    color = DarkSurface,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = status,
                        style = MaterialTheme.typography.bodyMedium,
                        color = SkyLight,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            }

            // Path Breadcrumb & Navigation
            Surface(color = DarkSurface, modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (parentPath != null) {
                        IconButton(onClick = { refreshDirectory(parentPath ?: "") }) {
                            Icon(Icons.Default.ArrowUpward, contentDescription = "Up", tint = SkyLight)
                        }
                    }
                    Text(
                        text = if (currentPath.isBlank()) "/ (Root of USB)" else "/$currentPath",
                        style = MaterialTheme.typography.titleMedium,
                        color = TextLight,
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            // Search Bar
            OutlinedTextField(
                value = searchQuery,
                onValueChange = {
                    searchQuery = it
                    refreshDirectory()
                },
                placeholder = { Text("Search files on USB...", color = TextMuted) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = TextMuted) },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = SkyPrimary,
                    unfocusedBorderColor = DarkSurface,
                    focusedTextColor = TextLight,
                    unfocusedTextColor = TextLight
                )
            )

            // Content Area
            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = SkyPrimary)
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.CloudOff, contentDescription = null, tint = RedDanger, modifier = Modifier.size(48.dp))
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(text = errorMessage ?: "", color = TextMuted)
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(onClick = { refreshDirectory() }) {
                            Text("Retry Connection")
                        }
                    }
                }
            } else if (items.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.FolderOpen, contentDescription = null, tint = TextMuted, modifier = Modifier.size(48.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("This folder is empty.", color = TextMuted)
                    }
                }
            } else {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(items) { item ->
                        FileItemView(
                            item = item,
                            onClick = {
                                if (item.isDir) {
                                    refreshDirectory(item.relativePath)
                                }
                            },
                            onRename = { itemToRename = item },
                            onDelete = { itemToDelete = item },
                            onDownload = {
                                uploadStatus = "Downloading ${item.name}..."
                            }
                        )
                    }
                }
            }
        }
    }

    // Dialog: Create Folder
    if (showCreateFolderDialog && selectedReceiver != null) {
        InputDialog(
            title = "New Folder",
            onConfirm = { folderName ->
                showCreateFolderDialog = false
                val newPath = if (currentPath.isBlank()) folderName else "$currentPath/$folderName"
                scope.launch {
                    client.createDirectory(selectedReceiver.receiverId, newPath)
                    refreshDirectory()
                }
            },
            onDismiss = { showCreateFolderDialog = false }
        )
    }

    // Dialog: Rename
    itemToRename?.let { item ->
        if (selectedReceiver != null) {
            InputDialog(
                title = "Rename",
                initialValue = item.name,
                onConfirm = { newName ->
                    itemToRename = null
                    scope.launch {
                        client.renameItem(selectedReceiver.receiverId, item.relativePath, newName)
                        refreshDirectory()
                    }
                },
                onDismiss = { itemToRename = null }
            )
        }
    }

    // Dialog: Delete Confirmation
    itemToDelete?.let { item ->
        if (selectedReceiver != null) {
            ConfirmationDialog(
                title = "Delete File or Folder",
                message = "Are you sure you want to permanently delete '${item.name}' from the USB drive?",
                onConfirm = {
                    itemToDelete = null
                    scope.launch {
                        client.deleteItem(selectedReceiver.receiverId, item.relativePath, recursive = item.isDir)
                        refreshDirectory()
                    }
                },
                onDismiss = { itemToDelete = null }
            )
        }
    }
}
