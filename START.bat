@echo off
cd /d "%~dp0"
taskkill /F /IM USB_Transfer.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
if exist "USB_Transfer.exe" (
    start "" "USB_Transfer.exe"
) else (
    start "" pythonw app.py
)
exit
