package com.phonetousb.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.io.File
import java.io.InputStream
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Signature

object KeyStoreManager {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "PhoneToUSB_Client_Identity"

    fun getOrCreateClientId(context: Context): String {
        val pubKey = getOrCreatePublicKey(context)
        val digest = MessageDigest.getInstance("SHA-256").digest(pubKey.encoded)
        val hex = digest.joinToString("") { "%02x".format(it) }
        return "p2u-client-${hex.substring(0, 16)}"
    }

    fun getOrCreatePublicKey(context: Context): java.security.PublicKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val kpg = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
            val parameterSpec = KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
            )
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false)
                .build()
            kpg.initialize(parameterSpec)
            kpg.generateKeyPair()
        }
        return keyStore.getCertificate(KEY_ALIAS).publicKey
    }

    fun getPublicKeyBase64(context: Context): String {
        val pubKey = getOrCreatePublicKey(context)
        return Base64.encodeToString(pubKey.encoded, Base64.NO_WRAP)
    }

    fun signData(data: ByteArray): String {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val privateKeyEntry = keyStore.getEntry(KEY_ALIAS, null) as KeyStore.PrivateKeyEntry
        val signature = Signature.getInstance("SHA256withECDSA").apply {
            initSign(privateKeyEntry.privateKey)
            update(data)
        }
        return Base64.encodeToString(signature.sign(), Base64.NO_WRAP)
    }
}

object CryptoUtils {
    fun calculateFileSha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(65536)
            var bytesRead: Int
            while (input.read(buffer).also { bytesRead = it } != -1) {
                digest.update(buffer, 0, bytesRead)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    fun calculateStreamSha256(inputStream: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(65536)
        var bytesRead: Int
        while (inputStream.read(buffer).also { bytesRead = it } != -1) {
            digest.update(buffer, 0, bytesRead)
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
