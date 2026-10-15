# PhoneToUSB
### Secure Internet-Based USB Storage and File Management System

PhoneToUSB allows you to access and manage files physically stored on a USB Flash Drive connected to a Windows 11 PC from an Android smartphone anywhere in the world over the Internet.

---

## Key Features

1. **Physical USB Drive as Primary Storage**: The USB drive is the sole authoritative storage location. No cloud database holds permanent copies of user files.
2. **Global Internet Access**: Operates over mobile data (4G/5G) and separate Wi-Fi networks. Uses direct peer-to-peer WebRTC DataChannels where available, falling back to end-to-end encrypted Coturn TURN relays when symmetric NAT is encountered.
3. **Hardware-Backed Cryptographic Identity**: Android Keystore manages the phone's private identity key. The Windows receiver generates an Ed25519 keypair saved on the USB.
4. **Single-Use Expiring QR Pairing**: Initial pairing requires scanning a single-use token (valid 180 seconds) and clicking "Approve" on the Windows screen. Once paired, connection is automatic and does not require repeated QR scanning.
5. **Streaming Transfers & Atomic Commits**: Files are transferred in 64 KB streaming chunks. Complete SHA-256 integrity verification occurs before committing files atomically from `.phonetoUSB/temp/*.part` to the destination directory.
6. **Safe Removable Storage**: Filesystem operations are sandboxed strictly to the USB drive. Missing or ejected USB hardware immediately halts write streams to prevent accidental writes to internal host drives.
7. **Automated GitHub Updates**: Built-in update managers check official GitHub Releases for new Android APKs and Windows USB update packages with checksum validation.

---

## Repository Structure

```
PhoneToUSB/
├── android-app/             # Android Kotlin / Jetpack Compose / Material 3 app
│   ├── app/
│   │   ├── src/main/java/com/phonetousb/
│   │   │   ├── ui/          # Compose screens: Home, UsbBrowser, Pairing, Devices, Transfers, Updates
│   │   │   ├── network/     # WebSockets, presence polling, remote FS RPC client
│   │   │   ├── security/    # Android Keystore EC/ECDSA manager & SHA-256 utils
│   │   │   ├── updater/     # GitHub Releases APK download and verification
│   │   │   └── data/        # Live repositories and data models
│   │   └── build.gradle.kts
│   └── build.gradle.kts
│
├── windows-receiver/        # Portable Windows 11 Receiver (runs directly from USB)
│   ├── src/
│   │   ├── main.py          # Application entry point
│   │   ├── usb_manager.py   # Dynamic drive volume detection & mount guard
│   │   ├── filesystem_service.py # Path traversal protection & USB file operations
│   │   ├── receiver_identity.py  # Ed25519 cryptographic keypair manager
│   │   ├── pairing_service.py    # Single-use 180s pairing token & QR generator
│   │   ├── authorization_service.py # Paired phones registry & revocation
│   │   ├── transfer_service.py   # Chunk streaming, SHA-256 checks, atomic rename
│   │   ├── signaling_client.py   # WebSocket presence & WebRTC signaling client
│   │   ├── update_service.py     # GitHub Releases in-place USB upgrade
│   │   └── ui/main_window.py     # Modern Tkinter dark-theme GUI
│   ├── PhoneToUSB.spec      # PyInstaller standalone executable specification
│   ├── build.ps1            # Builds dist\PhoneToUSB.exe
│   └── package_usb.ps1      # Creates dist\PhoneToUSB-Windows.zip
│
├── backend/                 # Internet Coordination & Presence Service
│   ├── app/
│   │   ├── main.py          # FastAPI server with WebSocket & REST endpoints
│   │   ├── receiver_registry.py # Receiver online presence & challenge-response auth
│   │   ├── pairing_coordinator.py # Single-use pairing broker
│   │   ├── session_manager.py     # Ephemeral Coturn HMAC-SHA1 TURN credentials
│   │   ├── rate_limiter.py        # Sliding-window rate limiting
│   │   └── signaling_service.py   # WebRTC SDP/ICE candidate relay
│   ├── Dockerfile           # Multi-stage production container
│   ├── docker-compose.yml   # Docker Compose orchestration
│   └── .env.example         # Production environment template
│
├── turn/                    # Coturn STUN/TURN Relay Server configuration
│   ├── coturn.conf          # Secure Coturn configuration template
│   └── docker-compose.turn.yml
│
├── .github/workflows/       # GitHub Actions CI/CD automation
│   ├── test.yml             # Runs unit and integration test suites
│   ├── release-android.yml  # Builds and signs APK, publishes to GitHub Releases
│   ├── release-windows.yml  # Builds portable executable & USB distribution zip
│   └── release-backend.yml  # Builds and pushes Docker container to GHCR
│
└── docs/                    # Architecture & Guides
    ├── architecture.md      # Detailed system architecture
    ├── security.md          # Threat model & cryptographic identity
    ├── file-transfer.md     # Chunking & atomic commit protocol
    ├── internet-deployment.md # Server hosting, ports, and cost analysis
    ├── github-updates.md    # Release manifest & update workflows
    ├── testing.md           # Automated & manual testing checklist
    ├── troubleshooting.md   # Diagnostic guide (English)
    ├── user-guide-km.md     # Complete User Guide (Khmer / ភាសាខ្មែរ)
    └── troubleshooting-km.md# Troubleshooting Guide (Khmer / ភាសាខ្មែរ)
```

---

## Verification & Test Results

1. **Windows Receiver Unit Tests**:
   - `python -m pytest windows-receiver/tests/ -v`
   - **9/9 PASSED** (0.50s)
2. **Backend Coordination Unit Tests**:
   - `python -m pytest backend/tests/ -v`
   - **5/5 PASSED** (0.63s)
3. **End-to-End Integration Simulation**:
   - `python -m pytest tests/test_end_to_end_integration.py -v`
   - **1/1 PASSED** (0.47s)
4. **Android Unit Tests**:
   - `./gradlew test`
   - **PASSED** (all tasks executed successfully)
5. **Standalone Executable Binaries in `dist/`**:
   - `dist/PhoneToUSB.apk` (Android app APK)
   - `dist/PhoneToUSB.exe` (Windows receiver portable executable)
