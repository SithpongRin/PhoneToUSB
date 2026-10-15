package com.phonetousb

import android.app.Application
import com.phonetousb.data.repository.ReceiverRepository
import com.phonetousb.data.repository.TransferRepository
import com.phonetousb.network.SignalingClient
import com.phonetousb.updater.GitHubUpdateManager
import kotlinx.coroutines.*

class PhoneToUSBApplication : Application() {
    lateinit var signalingClient: SignalingClient
    lateinit var receiverRepository: ReceiverRepository
    lateinit var transferRepository: TransferRepository
    lateinit var updateManager: GitHubUpdateManager

    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        signalingClient = SignalingClient(this)
        receiverRepository = ReceiverRepository(this)
        transferRepository = TransferRepository()
        updateManager = GitHubUpdateManager(this)

        // Connect to coordination service
        signalingClient.connect()

        // Background presence polling loop for paired receivers
        applicationScope.launch {
            while (isActive) {
                try {
                    val rids = receiverRepository.receivers.value.map { it.receiverId }
                    if (rids.isNotEmpty() && signalingClient.connectionState.value == "CONNECTED") {
                        signalingClient.queryPresence(rids)
                    }
                } catch (_: Exception) {}
                delay(10000)
            }
        }

        // Listen for presence updates from signaling client
        applicationScope.launch {
            signalingClient.receiverPresence.collect { presenceMap ->
                receiverRepository.updatePresence(presenceMap)
            }
        }
    }
}
