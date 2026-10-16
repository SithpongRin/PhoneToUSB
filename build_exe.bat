@echo off
title Build USB_Transfer.exe
cd /d "%~dp0"

python -m pip install flask segno pyinstaller
python -m PyInstaller --noconfirm --onefile --noconsole --clean --icon "app_icon.ico" --name "USB_Transfer" app.py

if exist "dist\USB_Transfer.exe" (
    copy /Y "dist\USB_Transfer.exe" "USB_Transfer.exe" >nul
    echo [SUCCESS] Built USB_Transfer.exe successfully!
) else (
    echo [ERROR] Failed to build USB_Transfer.exe
)
pause
