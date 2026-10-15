package com.phonetousb.ui.camera

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.*
import com.google.zxing.common.HybridBinarizer
import java.nio.ByteBuffer

class QrCodeAnalyzer(
    private val onQrCodeScanned: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val reader = MultiFormatReader().apply {
        val map = mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE))
        setHints(map)
    }

    private var isScanned = false

    override fun analyze(image: ImageProxy) {
        if (isScanned) {
            image.close()
            return
        }

        val buffer: ByteBuffer = image.planes[0].buffer
        val data = ByteArray(buffer.remaining())
        buffer.get(data)

        val width = image.width
        val height = image.height

        val source = PlanarYUVLuminanceSource(
            data,
            width,
            height,
            0,
            0,
            width,
            height,
            false
        )
        val binaryBitmap = BinaryBitmap(HybridBinarizer(source))

        try {
            val result = reader.decodeWithState(binaryBitmap)
            isScanned = true
            onQrCodeScanned(result.text)
        } catch (_: NotFoundException) {
            // Frame does not contain QR code, ignore and continue
        } catch (_: Exception) {
            // Ignore formatting or decoding exceptions
        } finally {
            image.close()
        }
    }

    fun reset() {
        isScanned = false
    }
}
