package com.phonetousb.data.repository

import com.phonetousb.data.model.TransferDirection
import com.phonetousb.data.model.TransferStatus
import com.phonetousb.data.model.TransferTask
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class TransferRepository {
    private val _tasks = MutableStateFlow<List<TransferTask>>(emptyList())
    val tasks: StateFlow<List<TransferTask>> = _tasks

    fun addTask(task: TransferTask) {
        val current = _tasks.value.toMutableList()
        current.add(0, task)
        _tasks.value = current
    }

    fun updateProgress(transferId: String, bytesTransferred: Long) {
        val current = _tasks.value.map { task ->
            if (task.transferId == transferId) {
                task.copy(
                    bytesTransferred = bytesTransferred,
                    status = TransferStatus.IN_PROGRESS
                )
            } else task
        }
        _tasks.value = current
    }

    fun completeTask(transferId: String) {
        val current = _tasks.value.map { task ->
            if (task.transferId == transferId) {
                task.copy(
                    bytesTransferred = task.totalBytes,
                    status = TransferStatus.COMPLETED
                )
            } else task
        }
        _tasks.value = current
    }

    fun failTask(transferId: String, error: String) {
        val current = _tasks.value.map { task ->
            if (task.transferId == transferId) {
                task.copy(
                    status = TransferStatus.FAILED,
                    error = error
                )
            } else task
        }
        _tasks.value = current
    }

    fun clearCompleted() {
        _tasks.value = _tasks.value.filter { it.status == TransferStatus.IN_PROGRESS || it.status == TransferStatus.QUEUED }
    }
}
