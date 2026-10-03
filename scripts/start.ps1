param([switch]$Lan, [ValidateRange(1024, 65535)][int]$Port = 18761)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error 'Run: python -m venv .venv, then .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
}
$bindAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$tlsPath = Join-Path $projectPath '.state\private\tls'
$scheme = if (Test-Path -LiteralPath (Join-Path $tlsPath 'server.pem')) { 'https' } else { 'http' }
Write-Host "Laptop: ${scheme}://localhost:$Port" -ForegroundColor Green
if ($Lan) {
    Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'
    } | ForEach-Object { Write-Host "Tablet candidate ($($_.InterfaceAlias)): ${scheme}://$($_.IPAddress):$Port" }
    Write-Host 'Use the Wi-Fi adapter address. Both devices must be on the same network.'
}
$serverArgs = @('-m','uvicorn','backend.main:app','--host',$bindAddress,'--port',"$Port",'--no-access-log','--no-proxy-headers')
if ($scheme -eq 'https') { $serverArgs += @('--ssl-certfile',(Join-Path $tlsPath 'server.pem'),'--ssl-keyfile',(Join-Path $tlsPath 'server-key.pem')) }
& $pythonPath @serverArgs
