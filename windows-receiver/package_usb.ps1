# PhoneToUSB USB Distribution Packager
# Creates PhoneToUSB-Windows.zip ready to extract onto any USB Flash Drive

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$DistExe = Join-Path $ScriptDir "dist\PhoneToUSB.exe"
if (-not (Test-Path $DistExe)) {
    Write-Host "dist\PhoneToUSB.exe does not exist. Running build.ps1 first..." -ForegroundColor Yellow
    & ".\build.ps1"
}

$StagingDir = Join-Path $ScriptDir "staging_usb"
$ZipOutput = Join-Path $ScriptDir "dist\PhoneToUSB-Windows.zip"

Write-Host "Preparing USB distribution package in $StagingDir..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $StagingDir
New-Item -ItemType Directory -Path $StagingDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $StagingDir "Documents") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $StagingDir "Photos") | Out-Null

Copy-Item $DistExe -Destination (Join-Path $StagingDir "PhoneToUSB.exe")
Copy-Item (Join-Path $ScriptDir "README.txt") -Destination (Join-Path $StagingDir "README.txt")

Write-Host "Compressing to $ZipOutput..." -ForegroundColor Cyan
Remove-Item -Force -ErrorAction SilentlyContinue $ZipOutput
Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipOutput -CompressionLevel Optimal

# Compute SHA-256
$hash = (Get-FileHash -Algorithm SHA256 $ZipOutput).Hash
Set-Content -Path (Join-Path $ScriptDir "dist\PhoneToUSB-Windows.zip.sha256") -Value "$hash *PhoneToUSB-Windows.zip"

Write-Host "=========================================" -ForegroundColor Green
Write-Host " USB Distribution Package Created:       " -ForegroundColor Green
Write-Host " $ZipOutput                              " -ForegroundColor Green
Write-Host " SHA-256: $hash                          " -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

Remove-Item -Recurse -Force $StagingDir
