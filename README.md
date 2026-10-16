# Phone to USB File Transfer (Offline WiFi)

A standalone Windows desktop application that transfers files (documents, images, videos, audio up to 2GB) directly from any mobile browser into a connected USB flash drive over local WiFi without requiring Internet access or Cloud services.

## Features

- **Direct Phone-to-USB:** Upload files directly to any selected USB flash drive.
- **Offline Local WiFi:** Works without Internet; requires only a shared WiFi network or mobile hotspot.
- **Multi-USB Drive Selector:** When multiple USB drives are plugged in, an interactive selector lets you pick the destination drive.
- **Rotating QR Code & Security:** SVG QR code rotates on a configurable timer (5 minutes or 10 minutes) with a 6-digit access code and one-click direct share links.
- **Modern Responsive UI:** Clean web interface with Dark and Light mode toggle, smooth transitions, and animated file upload progress.
- **No Installation Required:** Portable single-file Windows executable with custom application icon and desktop shortcut support.
- **In-App Auto Update:** Built-in automatic update system checking and downloading new releases directly from GitHub Releases.
- **Automated GitHub Actions:** Automated CI/CD workflow that compiles the executable and publishes new GitHub releases on every push.

## How to Run

### Option 1: Standalone Executable (Recommended)
1. Download `USB_Transfer.exe` from the GitHub Releases page.
2. Double-click `USB_Transfer.exe`.
3. The application will start silently and open your default web browser to the dashboard.

### Option 2: Run with Python
1. Ensure Python 3.10+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```
   Or double-click `START.bat`.

### Building Standalone Executable
To build `USB_Transfer.exe` locally using PyInstaller:
```bash
build_exe.bat
```
Or execute:
```bash
pyinstaller --noconfirm --onefile --noconsole --clean --icon "app_icon.ico" --name "USB_Transfer" app.py
```

## How to Use

1. Insert your USB flash drive into the Windows PC.
2. Connect your mobile phone and Windows PC to the same WiFi network (or phone hotspot).
3. Open `USB_Transfer.exe` (or run `START.bat`).
4. If multiple USB drives are connected, select the desired drive on the screen.
5. Scan the QR code displayed on the screen with your phone camera, or enter the 6-digit access code.
6. Select and upload files from your phone directly into the USB drive.

## License
MIT
