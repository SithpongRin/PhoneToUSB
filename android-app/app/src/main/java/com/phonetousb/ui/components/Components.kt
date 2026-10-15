package com.phonetousb.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.phonetousb.data.model.TransferStatus
import com.phonetousb.data.model.TransferTask
import com.phonetousb.data.model.UsbItem
import com.phonetousb.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppTopBar(
    title: String,
    canNavigateBack: Boolean = false,
    onNavigateBack: () -> Unit = {},
    actions: @Composable RowScope.() -> Unit = {}
) {
    TopAppBar(
        title = {
            Text(
                text = title,
                style = MaterialTheme.typography.titleLarge,
                color = TextLight
            )
        },
        navigationIcon = {
            if (canNavigateBack) {
                IconButton(onClick = onNavigateBack) {
                    Icon(
                        imageVector = Icons.Default.ArrowBack,
                        contentDescription = "Back",
                        tint = TextLight
                    )
                }
            }
        },
        actions = actions,
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = DarkBackground
        )
    )
}

@Composable
fun FileItemView(
    item: UsbItem,
    onClick: () -> Unit,
    onRename: () -> Unit,
    onDelete: () -> Unit,
    onDownload: () -> Unit
) {
    var menuExpanded by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clickable { onClick() },
        colors = CardDefaults.cardColors(containerColor = DarkSurface)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (item.isDir) Icons.Default.Folder else Icons.Default.InsertDriveFile,
                contentDescription = if (item.isDir) "Folder" else "File",
                tint = if (item.isDir) SkyLight else TextMuted,
                modifier = Modifier.size(36.dp)
            )

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = TextLight,
                    maxLines = 1
                )
                val dateStr = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
                    .format(Date(item.modifiedTimestamp * 1000))
                val sizeStr = if (item.isDir) "Folder" else "${item.size / 1024} KB"
                Text(
                    text = "$sizeStr | $dateStr",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextMuted
                )
            }

            Box {
                IconButton(onClick = { menuExpanded = true }) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "Options",
                        tint = TextMuted
                    )
                }
                DropdownMenu(
                    expanded = menuExpanded,
                    onDismissRequest = { menuExpanded = false }
                ) {
                    if (!item.isDir) {
                        DropdownMenuItem(
                            text = { Text("Download") },
                            onClick = { menuExpanded = false; onDownload() },
                            leadingIcon = { Icon(Icons.Default.Download, contentDescription = null) }
                        )
                    }
                    DropdownMenuItem(
                        text = { Text("Rename") },
                        onClick = { menuExpanded = false; onRename() },
                        leadingIcon = { Icon(Icons.Default.Edit, contentDescription = null) }
                    )
                    DropdownMenuItem(
                        text = { Text("Delete", color = RedDanger) },
                        onClick = { menuExpanded = false; onDelete() },
                        leadingIcon = { Icon(Icons.Default.Delete, contentDescription = null, tint = RedDanger) }
                    )
                }
            }
        }
    }
}

@Composable
fun TransferItemView(task: TransferTask) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = DarkSurface)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Upload,
                    contentDescription = null,
                    tint = SkyLight,
                    modifier = Modifier.size(24.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = task.filename,
                    style = MaterialTheme.typography.titleMedium,
                    color = TextLight,
                    modifier = Modifier.weight(1f)
                )
                val statusColor = when (task.status) {
                    TransferStatus.COMPLETED -> GreenSuccess
                    TransferStatus.FAILED -> RedDanger
                    TransferStatus.IN_PROGRESS -> SkyLight
                    else -> AmberWarning
                }
                Text(
                    text = task.status.name,
                    style = MaterialTheme.typography.bodyMedium,
                    color = statusColor,
                    fontWeight = FontWeight.Bold
                )
            }

            if (task.status == TransferStatus.IN_PROGRESS && task.totalBytes > 0) {
                Spacer(modifier = Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { (task.bytesTransferred.toFloat() / task.totalBytes).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                    color = SkyPrimary,
                    trackColor = DarkBackground
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "${task.bytesTransferred / 1024} KB / ${task.totalBytes / 1024} KB",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextMuted
                )
            }
        }
    }
}

@Composable
fun ConfirmationDialog(
    title: String,
    message: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title, color = TextLight) },
        text = { Text(message, color = TextMuted) },
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text("Confirm", color = RedDanger, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextLight)
            }
        },
        containerColor = DarkSurface
    )
}

@Composable
fun InputDialog(
    title: String,
    initialValue: String = "",
    onConfirm: (String) -> Unit,
    onDismiss: () -> Unit
) {
    var text by remember { mutableStateOf(initialValue) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title, color = TextLight) },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
        },
        confirmButton = {
            TextButton(onClick = { if (text.isNotBlank()) onConfirm(text) }) {
                Text("OK", color = SkyLight, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextMuted)
            }
        },
        containerColor = DarkSurface
    )
}
