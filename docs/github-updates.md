# GitHub Releases Update System

## 1. Overview

Both the Android application and the portable Windows receiver support automated update discovery, integrity verification, and safe upgrades using **GitHub Releases**.

```
GitHub Repository Releases (API / Atom)
          │
          ├──> Android App: Checks latest tag, validates SHA-256 + Signing Certificate, prompts user to install.
          └──> Windows Receiver: Checks latest tag, downloads package, safely unpacks on USB without self-lockout.
```

---

## 2. Release Asset Manifest

Every official GitHub release attaches:
1. `PhoneToUSB-vX.Y.Z.apk` (Android Application APK)
2. `PhoneToUSB-vX.Y.Z-Windows.zip` (Portable USB distribution)
3. `release-manifest.json` (Cryptographic verification manifest)
4. `release-manifest.json.sig` (Ed25519 signature of the manifest created with the official release key)

### Structure of `release-manifest.json`:
```json
{
  "version": "1.0.0",
  "release_date": "2026-10-15T00:00:00Z",
  "mandatory": false,
  "changelog": "Initial production release of PhoneToUSB.",
  "android": {
    "version_code": 100,
    "version_name": "1.0.0",
    "filename": "PhoneToUSB-v1.0.0.apk",
    "sha256": "8f3...a9b",
    "min_sdk": 26,
    "target_sdk": 35
  },
  "windows": {
    "version": "1.0.0",
    "filename": "PhoneToUSB-v1.0.0-Windows.zip",
    "sha256": "4c2...e81"
  }
}
```

---

## 3. Update Procedures

### 3.1 Android Update Flow
1. **Periodic Query**: Queries `https://api.github.com/repos/{owner}/{repo}/releases/latest` with ETag caching (rate-limit friendly).
2. **SemVer Comparison**: Compares remote `version_code` against installed `BuildConfig.VERSION_CODE`.
3. **Download with Progress**: Downloads APK to app-private cache (`context.cacheDir/updates/`).
4. **Integrity Verification**: Calculates SHA-256 of the downloaded APK and verifies against `release-manifest.json`.
5. **System Installer**: Launches `android.content.Intent.ACTION_INSTALL_PACKAGE` or `ACTION_VIEW` with `FileProvider` URI and `FLAG_GRANT_READ_URI_PERMISSION`.

### 3.2 Windows Receiver In-Place USB Upgrade
Since Windows locks the running `PhoneToUSB.exe`, the receiver cannot overwrite its own executable directly:
1. Receiver downloads new `PhoneToUSB-vX.Y.Z-Windows.zip` to `.phonetoUSB/temp/update.zip`.
2. Verifies SHA-256.
3. Extracts new executable to `.phonetoUSB/temp/PhoneToUSB.new.exe`.
4. Spawns an atomic updater script (`update_helper.bat` or PowerShell) and requests the receiver GUI to shut down:
   ```cmd
   @echo off
   timeout /t 2 /nobreak >nul
   move /y ".phonetoUSB\temp\PhoneToUSB.new.exe" "PhoneToUSB.exe"
   start "" "PhoneToUSB.exe"
   del "%~f0"
   ```
5. Preserves all configuration in `.phonetoUSB/receiver_identity.json` and `.phonetoUSB/paired_devices.json` intact.
