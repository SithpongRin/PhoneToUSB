package com.phonetousb.ui.camera

import android.view.ViewGroup
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.phonetousb.ui.theme.SkyLight
import com.phonetousb.ui.theme.SkyPrimary
import java.util.concurrent.Executors

@Composable
fun CameraScannerView(
    onQrCodeDetected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    var camera by remember { mutableStateOf<Camera?>(null) }
    var isTorchOn by remember { mutableStateOf(false) }

    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val qrAnalyzer = remember {
        QrCodeAnalyzer { result ->
            onQrCodeDetected(result)
        }
    }

    // Scanning laser bar animation
    val infiniteTransition = rememberInfiniteTransition(label = "Laser")
    val laserY by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(2000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "LaserY"
    )

    Box(modifier = modifier.fillMaxSize()) {
        // CameraX Live Preview
        AndroidView(
            factory = { ctx ->
                PreviewView(ctx).apply {
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT
                    )
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                }
            },
            update = { previewView ->
                val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
                cameraProviderFuture.addListener({
                    val cameraProvider = cameraProviderFuture.get()
                    val preview = Preview.Builder().build().also {
                        it.surfaceProvider = previewView.surfaceProvider
                    }

                    val imageAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .also {
                            it.setAnalyzer(cameraExecutor, qrAnalyzer)
                        }

                    val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                    try {
                        cameraProvider.unbindAll()
                        camera = cameraProvider.bindToLifecycle(
                            lifecycleOwner,
                            cameraSelector,
                            preview,
                            imageAnalysis
                        )
                    } catch (_: Exception) {}
                }, ContextCompat.getMainExecutor(context))
            },
            modifier = Modifier.fillMaxSize()
        )

        // Semi-transparent darkened background mask with cutout
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0x77000000))
        )

        // Viewfinder targeting frame
        Box(
            modifier = Modifier
                .size(260.dp)
                .align(Alignment.Center)
                .border(2.dp, SkyLight, RoundedCornerShape(16.dp))
                .background(Color.Transparent)
        ) {
            // Animated Scanning Laser Line
            Canvas(modifier = Modifier.fillMaxSize()) {
                val y = size.height * laserY
                drawLine(
                    color = SkyLight,
                    start = Offset(0f, y),
                    end = Offset(size.width, y),
                    strokeWidth = 3.dp.toPx()
                )
            }
        }

        // Flashlight Toggle Button
        IconButton(
            onClick = {
                camera?.let {
                    if (it.cameraInfo.hasFlashUnit()) {
                        isTorchOn = !isTorchOn
                        it.cameraControl.enableTorch(isTorchOn)
                    }
                }
            },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(24.dp)
                .background(Color(0x99000000), RoundedCornerShape(50))
        ) {
            Icon(
                imageVector = if (isTorchOn) Icons.Default.FlashOn else Icons.Default.FlashOff,
                contentDescription = "Torch",
                tint = if (isTorchOn) SkyLight else Color.White
            )
        }
    }
}
