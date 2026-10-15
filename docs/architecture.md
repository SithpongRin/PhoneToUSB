# PhoneToUSB Architecture Specification

## 1. Executive Summary

**PhoneToUSB** is a secure, Internet-based USB storage and remote file management system. The core design principle is:
> **The physical USB Flash Drive plugged into a Windows 11 machine is the sole authoritative storage location.** The Android mobile application is the authenticated remote interface that allows browsing, uploading, downloading, and managing actual files stored on that USB drive over the Internet from anywhere in the world.

The system does **not** rely on cloud storage to hold permanent copies of user files. Remote communication operates peer-to-peer (via WebRTC DataChannels) when NAT traversal permits, and falls back to end-to-end encrypted TURN relays when symmetric NATs or restrictive firewalls prevent direct peer connectivity.

---

## 2. High-Level System Architecture

```mermaid
flowchart TD
    subgraph AndroidDevice ["Android Device (Mobile Data / Remote Wi-Fi)"]
        A_UI["Compose UI (File Browser, Transfers, Pairing)"]
        A_Security["Android Keystore (Client Identity Keypair)"]
        A_TransferEngine["Transfer Engine (Chunking, SHA-256, Flow Control)"]
        A_Net["WebRTC / WSS Client"]
    end

    subgraph InternetInfrastructure ["Internet Coordination Infrastructure"]
        CoordService["Backend Signaling & Presence Service (FastAPI / WSS)"]
        TurnServer["Coturn STUN / TURN Relay (Fallback Encrypted Relay)"]
    end

    subgraph WindowsHost ["Windows 11 PC (Home / Office Network)"]
        W_Signaling["Signaling & Peer Client"]
        W_Auth["Authorization Service (Known Phone Registry)"]
        W_USBDetector["USB Volume Detector & Watcher"]
        W_FSService["Filesystem & Safe Atomic Writer"]
        W_GUI["Desktop UI (Status, Pairing QR, Approvals, Transfers)"]
        W_Identity["Receiver Cryptographic Identity (.phonetoUSB/identity.json)"]
    end

    subgraph USBHardware ["Authoritative Physical USB Drive"]
        USB_Root["USB Root / Data Directory (Documents, Photos, etc.)"]
        USB_Hidden[".phonetoUSB/ (Config, Receiver Identity, Logs, Security Registry)"]
    end

    A_Net <-->|HTTPS / WSS (Presence & SDP/ICE Signaling)| CoordService
    W_Signaling <-->|HTTPS / WSS (Presence & SDP/ICE Signaling)| CoordService
    A_Net <-->|STUN Binding Requests| TurnServer
    W_Signaling <-->|STUN Binding Requests| TurnServer

    A_Net <-.->|Direct Encrypted WebRTC DataChannel (P2P)| W_Signaling
    A_Net <-.->|Relayed Encrypted WebRTC DataChannel (TURN)| TurnServer
    TurnServer <-.->|Relayed Encrypted WebRTC DataChannel| W_Signaling

    W_FSService <--> USB_Root
    W_Identity <--> USB_Hidden
    W_USBDetector -.->|Monitors Mount & Eject| USBHardware
```

---

## 3. Component Breakdown

### 3.1 Android Mobile Application (`android-app`)
- **UI Framework**: Modern Jetpack Compose with Material 3 design system. No emojis used in UI icons; clean Vector Drawables.
- **Remote File Browser**: Shows live directory listings directly queried from the USB drive. Differentiates folders from files, handles sorting (name, size, modification date, type), and displays connection states (Online, Offline, USB Missing).
- **Transfer Engine**: Handles chunked streaming transfers (64 KB chunks), client-side SHA-256 calculation, transfer progress, cancellation, retry, and parallel queues.
- **Security Engine**: Generates and stores the device's Ed25519/ECDSA private key in Android Keystore (hardware-backed when available). Handles QR code pairing, public key attestation, and signature verification on session messages.
- **GitHub Updater**: Periodically checks official GitHub Releases for update metadata, verifies APK integrity and signature identity, and guides the user through standard Android package installer workflows.

### 3.2 Portable Windows 11 Receiver (`windows-receiver`)
- **Portability**: Self-contained single-file or folder distribution running directly from the USB drive (`PhoneToUSB.exe`). Does not require Python, Git, or administrative installation on the host PC.
- **USB Detection & Volume Validation**: Dynamically resolves the drive letter and volume GUID corresponding to the executable's storage media using Windows Win32 APIs (`GetVolumeInformation`, `GetDriveType`). Constantly verifies write access and stops all file writes immediately if the USB drive is unmounted or removed.
- **Filesystem Service**: Strictly sandboxes file browsing and management to the user data root. Rejects directory traversal attempts (`..`, alternate data streams, reserved DOS devices `CON`, `PRN`, `AUX`, absolute drive references). Enforces atomic file writes via temporary `.part` files followed by SHA-256 checksum verification and atomic rename.
- **Pairing & Authorization**: Generates single-use expiring pairing tokens (valid 3 minutes), renders the pairing QR code, displays pairing authorization dialogs on the host PC, and persists approved phone public keys in `.phonetoUSB/paired_devices.json`.
- **Desktop UI**: Built using Python Tkinter with a clean dark/modern theme, showing real-time connectivity status, USB capacity and health, pairing QR codes, active transfer progress, and pairing approval modals.

### 3.3 Coordination & Signaling Backend (`backend`)
- **Service Stack**: Python 3.13 + FastAPI + Uvicorn + WebSockets.
- **Responsibilities**:
  - Secure receiver registration and presence heartbeat (30-second lease with automatic offline marking).
  - WebRTC signaling broker (exchanging SDP offers, answers, and ICE candidates over authenticated TLS WebSockets).
  - Single-use pairing coordination broker.
  - Ephemeral TURN credential issuance (via Coturn HMAC-SHA1 REST API secret).
  - Rate limiting (sliding window rate limit on IP and receiver IDs to prevent abuse and brute force).
- **Zero-Storage Principle**: The backend **never** receives, stores, or caches file contents, directory listings, or permanent user credentials. It acts strictly as an ephemeral connection broker.

### 3.4 TURN / STUN Relay Infrastructure (`turn`)
- **Software**: Coturn open-source TURN server.
- **Function**: Provides RFC 5389 STUN and RFC 5766/8656 TURN relay fallback for devices operating behind symmetric NATs or restrictive cellular carrier firewalls.
- **Privacy & Security**: Traffic passing through TURN is encrypted end-to-end via DTLS-SRTP/WebRTC SCTP. The TURN relay cannot inspect or tamper with transferred file chunks.

---

## 4. Communication & Protocol Flow

### 4.1 Connection Sequence (Every Session)
1. **Receiver Online**: When `PhoneToUSB.exe` launches on the Windows laptop, it verifies the USB is mounted, reads its persistent receiver identity (`receiver_id` and public key), and establishes a persistent WSS connection to `wss://backend.domain/ws/receiver`.
2. **Presence Broadcast**: The backend records the receiver as `ONLINE` in its presence registry.
3. **Android Discovery**: The Android app opens and connects to `wss://backend.domain/ws/client`. It sends its list of paired `receiver_id`s. The backend responds with their online/offline presence states.
4. **Signaling Exchange**: If the paired receiver is online, the Android app requests a connection session. The backend issues ephemeral TURN credentials to both peers and forwards WebRTC SDP Offers/Answers and ICE candidates.
5. **Direct / Relayed DataChannel**: The peers establish a WebRTC PeerConnection. WebRTC automatically selects direct P2P (via host or STUN srflx candidates) or relays through TURN.
6. **Session Authentication & Binding**: Once the DataChannel opens, the peers exchange a mutual cryptographic handshake (challenge-response signed by their respective private keys). This binds the DataChannel directly to the paired identities, completely preventing any man-in-the-middle or spoofing by an untrusted signaling server.

### 4.2 File System Protocol (JSON over DataChannel)
All management operations and file streams occur across dedicated channels on the authenticated connection:
- `FS_LIST`: Request directory listing with path, sorting, and pagination parameters.
- `FS_MKDIR`: Create a new folder.
- `FS_RENAME`: Safely rename a file or folder.
- `FS_DELETE`: Delete a file or folder with explicit client confirmation.
- `TRANSFER_START`: Negotiate file upload or download (filename, size, relative path, SHA-256).
- `TRANSFER_CHUNK`: Binary or Base64/framed file chunks with sequence numbers.
- `TRANSFER_FINISH`: Final validation, checksum comparison, and atomic commit.
