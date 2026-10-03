$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$privatePath = Join-Path $projectPath '.state\private'
New-Item -ItemType Directory -Path $privatePath -Force | Out-Null
$accountSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $privatePath /inheritance:r /grant:r "*${accountSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw 'Protect the private folder before enabling HTTPS.' }
& (Join-Path $projectPath '.venv\Scripts\python.exe') -m backend.tls
if ($LASTEXITCODE -ne 0) { throw 'Certificate generation failed.' }
$certificate = Join-Path $projectPath '.state\private\tls\G16 Dashboard CA.cer'
Import-Certificate -FilePath $certificate -CertStoreLocation 'Cert:\CurrentUser\Root' | Select-Object Subject,Thumbprint
Write-Host 'HTTPS prepared. Restart the dashboard task to enable it.'
Write-Host 'Install G16 Dashboard CA.cer from Downloads on the Redmi as a CA certificate, then use https:// URLs.'
