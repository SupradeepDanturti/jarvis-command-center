$ErrorActionPreference = 'Stop'
$taskName = 'G16 Command Center'
$projectPath = Split-Path -Parent $PSScriptRoot
$runnerPath = Join-Path $PSScriptRoot 'run-server.py'
$task = Get-ScheduledTask -TaskName $taskName
if ($task.Actions.Execute -ne (Join-Path $projectPath '.venv\Scripts\pythonw.exe')) {
    throw 'This startup task belongs to another installation.'
}
Stop-ScheduledTask -TaskName $taskName
$deadline = (Get-Date).AddSeconds(20)
do {
    $running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runnerPath) }
    if (-not $running) { break }
    if ((Get-Date) -gt $deadline) { throw 'Previous dashboard is still stopping. Start the task after it exits.' }
    Start-Sleep -Milliseconds 250
} while ($true)
Start-ScheduledTask -TaskName $taskName
Write-Host 'Dashboard background task restarted.'
