param([switch]$Lan, [ValidateRange(1024, 65535)][int]$Port = 18761)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error 'Run: python -m venv .venv, then .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
}
$bindAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
Write-Host "Laptop: http://localhost:$Port" -ForegroundColor Green
if ($Lan) {
    Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'
    } | ForEach-Object { Write-Host "Tablet candidate ($($_.InterfaceAlias)): http://$($_.IPAddress):$Port" }
    Write-Host 'Use the Wi-Fi adapter address. Both devices must be on the same network.'
}
& $pythonPath -m uvicorn backend.main:app --host $bindAddress --port $Port --no-access-log
