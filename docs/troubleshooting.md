# PhoneToUSB Technical Troubleshooting & Diagnostic Guide

## 1. Diagnostics Overview

PhoneToUSB logs non-sensitive diagnostics to `.phonetoUSB/logs/receiver.log` on the USB drive. When diagnosing issues, inspect this file first.

---

## 2. Common Issues & Solutions

### 2.1 Receiver Shows "USB Not Ready"
- **Cause**: Application was launched from host `C:\` drive instead of the USB flash drive, or the drive is write-protected.
- **Solution**: Copy `PhoneToUSB.exe` directly to the USB drive root and launch it from there. Verify the drive is not locked with a physical write-protect switch.

### 2.2 Android App Reports "Receiver Offline"
- **Cause 1**: The Windows PC entered sleep mode, suspending background network sockets.
  - **Fix**: Adjust Windows power settings so the PC does not sleep while plugged in.
- **Cause 2**: Restrictive firewall blocking WebSocket traffic.
  - **Fix**: Ensure port 443 (WSS) and TURN ports 3478/5349 are allowed.

### 2.3 QR Pairing Fails or Times Out
- **Cause**: Pairing tokens expire strictly after 180 seconds to prevent replay attacks.
  - **Fix**: Generate a fresh QR code on the PC and scan it promptly.

### 2.4 File Transfer Interrupted Mid-Stream
- **Safeguard in action**: PhoneToUSB writes files to `.phonetoUSB/temp/<id>.part`.
- **Behavior**: If a transfer is disconnected, the incomplete `.part` file is quarantined or purged. Existing user files are never corrupted. Once reconnected, retry the transfer.
