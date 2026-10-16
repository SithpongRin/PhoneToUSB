package com.phonetousb.ui.camera

import android.os.Handler
import android.os.Looper
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.*
import com.google.zxing.common.GlobalHistogramBinarizer
import com.google.zxing.common.HybridBinarizer

class QrCodeAnalyzer(
    private val onQrCodeScanned: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val mainHandler = Handler(Looper.getMainLooper())
    private val reader = MultiFormatReader().apply {
        val hints = mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
            DecodeHintType.TRY_HARDER to true,
            DecodeHintType.ALSO_INVERTED to true,
            DecodeHintType.CHARACTER_SET to "UTF-8"
        )
        setHints(hints)
    }

    private var lastDetectedTime = 0L

    override fun analyze(image: ImageProxy) {
        val now = System.currentTimeMillis()
        if (now - lastDetectedTime < 1000L) {
            image.close()
            return
        }

        try {
            val plane = image.planes[0]
            val buffer = plane.buffer
            buffer.rewind()
            val rowStride = plane.rowStride
            val pixelStride = plane.pixelStride
            val width = image.width
            val height = image.height

            // Extract clean, unpadded luminance array (handles MediaTek/Tecno/Samsung rowStride padding)
            val luminance = ByteArray(width * height)
            if (rowStride == width && pixelStride == 1) {
                buffer.get(luminance, 0, width * height)
            } else {
                val rowBuffer = ByteArray(rowStride)
                for (row in 0 until height) {
                    val bytesToRead = if (row == height - 1) {
                        minOf(rowStride, buffer.remaining())
                    } else {
                        rowStride
                    }
                    buffer.get(rowBuffer, 0, bytesToRead)
                    if (pixelStride == 1) {
                        System.arraycopy(rowBuffer, 0, luminance, row * width, width)
                    } else {
                        for (col in 0 until width) {
                            val idx = col * pixelStride
                            if (idx < bytesToRead) {
                                luminance[row * width + col] = rowBuffer[idx]
                            }
                        }
                    }
                }
            }

            // Try normal orientation first, then 90-degree rotated (portrait camera sensor)
            val decodedText = tryDecode(luminance, width, height)
                ?: run {
                    val rotated = rotate90(luminance, width, height)
                    tryDecode(rotated, height, width)
                }

            if (!decodedText.isNullOrBlank()) {
                lastDetectedTime = System.currentTimeMillis()
                mainHandler.post {
                    onQrCodeScanned(decodedText)
                }
            }
        } catch (_: Exception) {
            // Continue analyzing next frame
        } finally {
            image.close()
        }
    }

    private fun tryDecode(luminance: ByteArray, width: Int, height: Int): String? {
        val source = PlanarYUVLuminanceSource(
            luminance,
            width,
            height,
            0,
            0,
            width,
            height,
            false
        )
        // Attempt 1: HybridBinarizer
        try {
            val result = reader.decodeWithState(BinaryBitmap(HybridBinarizer(source)))
            return result.text
        } catch (_: Exception) {
            reader.reset()
        }

        // Attempt 2: GlobalHistogramBinarizer (handles laptop screen backlight/glare)
        try {
            val result = reader.decodeWithState(BinaryBitmap(GlobalHistogramBinarizer(source)))
            return result.text
        } catch (_: Exception) {
            reader.reset()
        }

        return null
    }

    private fun rotate90(data: ByteArray, width: Int, height: Int): ByteArray {
        val rotated = ByteArray(width * height)
        for (y in 0 until height) {
            for (x in 0 until width) {
                rotated[x * height + height - y - 1] = data[y * width + x]
            }
        }
        return rotated
    }

    fun reset() {
        lastDetectedTime = 0L
    }
}
