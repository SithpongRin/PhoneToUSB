@echo off
title Install USB File Transfer Shortcuts
cd /d "%~dp0"

echo Creating Desktop and Start Menu shortcuts...
python -c "import app; app.create_desktop_and_start_menu_shortcuts(); print('Done!')" 2>nul
if %errorlevel% neq 0 (
    if exist "USB_Transfer.exe" (
        powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell;$s=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'USB File Transfer.lnk'));$s.TargetPath=(Resolve-Path 'USB_Transfer.exe');$s.WorkingDirectory=(Get-Location);$s.Save();$m=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'USB File Transfer.lnk'));$m.TargetPath=(Resolve-Path 'USB_Transfer.exe');$m.WorkingDirectory=(Get-Location);$m.Save();Write-Output 'Shortcuts created successfully!'"
    )
)

echo [SUCCESS] Shortcut created on Desktop and Start Menu!
echo To pin to Taskbar:
echo 1. Open Windows Start Menu
echo 2. Search 'USB File Transfer'
echo 3. Right-click and choose 'Pin to taskbar'
echo.
pause
