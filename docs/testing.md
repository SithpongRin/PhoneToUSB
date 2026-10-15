# PhoneToUSB Automated & Manual Testing Specification

## 1. Overview

This document details the automated test suite, coverage criteria, and manual cross-network integration test procedures for PhoneToUSB.

---

## 2. Automated Test Matrix

| Component | Test File | Description | Execution Command |
| :--- | :--- | :--- | :--- |
| **Windows Receiver** | `windows-receiver/tests/test_receiver.py` | 9 unit tests: Ed25519 key persistence, digital signature challenge/verify, directory listing, traversal protection, atomic chunk streaming, SHA-256 validation, pairing tokens, device revocation. | `pytest windows-receiver/tests/ -v` |
| **Backend Coordination** | `backend/tests/test_backend.py` | 5 unit tests: Health endpoint, presence queries, ephemeral Coturn HMAC-SHA1 tokens, sliding window rate limiter, Ed25519 WebSocket challenge handshake. | `pytest backend/tests/ -v` |
| **Integration Test** | `tests/test_end_to_end_integration.py` | Full simulated lifecycle: Discovery -> Pairing -> Filesystem browsing -> Chunked upload -> Atomic write -> Directory refresh -> Download integrity. | `pytest tests/test_end_to_end_integration.py -v` |
| **Android Application** | `android-app/app/src/test/` | SemVer comparisons for GitHub update manager, client-side path normalization and safety checks. | `./gradlew test` |

---

## 3. Manual Cross-Network Verification Checklist

When testing between real physical devices:
1. **Prerequisites**:
   - Host laptop connected to Network A (e.g. Home Wi-Fi).
   - Android smartphone connected to Network B (e.g. 4G/5G Cellular Data).
   - Authoritative USB Flash Drive plugged into Laptop.
   - Coordination Backend running on an Internet-accessible IP or domain.
2. **Steps**:
   - Launch `PhoneToUSB.exe` on Laptop. Verify green "USB Ready" and "Online" indicators.
   - Click "Generate Pairing QR Code".
   - Open PhoneToUSB on Android phone. Scan QR code.
   - Click "Approve" on Laptop dialog.
   - Confirm Android switches to "USB Browser" and shows real folders (`Documents/`, `Photos/`).
   - Select and upload a 50 MB video or PDF.
   - Confirm Windows receiver writes file chunks to `.phonetoUSB/temp/*.part`.
   - Confirm completion and atomic move to target folder.
   - Check Windows File Explorer: file physically exists on the USB drive.
