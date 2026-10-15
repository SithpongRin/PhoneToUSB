# PhoneToUSB Windows Receiver Build Script
# Builds standalone portable PhoneToUSB.exe using PyInstaller

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " Building PhoneToUSB Portable Receiver  " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Ensure dependencies installed
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet

# Clean past build artifacts
Write-Host "Cleaning previous build directories..." -ForegroundColor Yellow
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build

# Run PyInstaller
Write-Host "Packaging PhoneToUSB.exe with PyInstaller..." -ForegroundColor Yellow
pyinstaller --clean PhoneToUSB.spec

if (Test-Path "dist\PhoneToUSB.exe") {
    $exeSize = (Get-Item "dist\PhoneToUSB.exe").Length / 1MB
    Write-Host "SUCCESS: Built dist\PhoneToUSB.exe ($([Math]::Round($exeSize, 2)) MB)" -ForegroundColor Green
} else {
    Write-Error "Build failed: dist\PhoneToUSB.exe not found!"
}
