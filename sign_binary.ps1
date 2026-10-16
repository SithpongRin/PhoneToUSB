$ErrorActionPreference = "Stop"
Write-Host "Creating Code Signing Certificate..."
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=Sithpong Rin, O=PhoneToUSB" -KeyUsage DigitalSignature -FriendlyName "PhoneToUSB Publisher" -CertStoreLocation "Cert:\CurrentUser\My" -NotAfter (Get-Date).AddYears(10)

Write-Host "Exporting Public Certificate..."
Export-Certificate -Cert $cert -FilePath "PhoneToUSB.cer" -Force | Out-Null

Write-Host "Signing USB_Transfer.exe..."
try {
    Set-AuthenticodeSignature -FilePath "dist\USB_Transfer.exe" -Certificate $cert -TimestampServer "http://timestamp.digicert.com"
} catch {
    Set-AuthenticodeSignature -FilePath "dist\USB_Transfer.exe" -Certificate $cert
}

Write-Host "Verifying Signature..."
Get-AuthenticodeSignature -FilePath "dist\USB_Transfer.exe" | Format-List
