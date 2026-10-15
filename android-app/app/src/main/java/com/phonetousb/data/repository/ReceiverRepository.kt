package com.phonetousb.data.repository

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.phonetousb.data.model.ReceiverInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class ReceiverRepository(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("phonetousb_receivers", Context.MODE_PRIVATE)
    private val gson = Gson()

    private val _receivers = MutableStateFlow<List<ReceiverInfo>>(emptyList())
    val receivers: StateFlow<List<ReceiverInfo>> = _receivers

    private val _selectedReceiver = MutableStateFlow<ReceiverInfo?>(null)
    val selectedReceiver: StateFlow<ReceiverInfo?> = _selectedReceiver

    init {
        loadReceivers()
    }

    private fun loadReceivers() {
        val json = prefs.getString("paired_list", "[]")
        val type = object : TypeToken<List<ReceiverInfo>>() {}.type
        val list: List<ReceiverInfo> = gson.fromJson(json, type) ?: emptyList()
        _receivers.value = list
        if (_selectedReceiver.value == null && list.isNotEmpty()) {
            _selectedReceiver.value = list.first()
        }
    }

    private fun saveReceivers(list: List<ReceiverInfo>) {
        _receivers.value = list
        prefs.edit().putString("paired_list", gson.toJson(list)).apply()
        if (_selectedReceiver.value == null && list.isNotEmpty()) {
            _selectedReceiver.value = list.first()
        } else if (_selectedReceiver.value != null && list.none { it.receiverId == _selectedReceiver.value?.receiverId }) {
            _selectedReceiver.value = list.firstOrNull()
        }
    }

    fun addReceiver(receiver: ReceiverInfo) {
        val current = _receivers.value.toMutableList()
        val index = current.indexOfFirst { it.receiverId == receiver.receiverId }
        if (index != -1) {
            current[index] = receiver
        } else {
            current.add(receiver)
        }
        saveReceivers(current)
        _selectedReceiver.value = receiver
    }

    fun selectReceiver(receiverId: String) {
        _selectedReceiver.value = _receivers.value.find { it.receiverId == receiverId }
    }

    fun removeReceiver(receiverId: String) {
        val current = _receivers.value.filter { it.receiverId != receiverId }
        saveReceivers(current)
    }

    fun updatePresence(presenceMap: Map<String, Boolean>) {
        val current = _receivers.value.map { r ->
            val online = presenceMap[r.receiverId] ?: false
            r.copy(isOnline = online, lastSeen = if (online) System.currentTimeMillis() else r.lastSeen)
        }
        _receivers.value = current
        _selectedReceiver.value = current.find { it.receiverId == _selectedReceiver.value?.receiverId }
    }
}
