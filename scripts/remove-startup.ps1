$ErrorActionPreference = 'Stop'
$taskName = 'G16 Command Center'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host 'Dashboard startup is already disabled.'
    return
}
if ($task.Actions.Execute -ne $pythonPath) {
    throw 'The task belongs to another installation. It was not changed.'
}
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host 'Dashboard stopped and automatic startup disabled.'
