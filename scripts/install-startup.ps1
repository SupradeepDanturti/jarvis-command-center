param([ValidateRange(1024, 65535)][int]$Port = 18761)
$ErrorActionPreference = 'Stop'
$taskName = 'G16 Command Center'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
$runnerPath = Join-Path $PSScriptRoot 'run-server.py'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the virtual environment and install requirements before enabling startup.'
}
$accountName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"{0}" --port {1}' -f $runnerPath, $Port) -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $accountName
$principal = New-ScheduledTaskPrincipal -UserId $accountName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask -and $existingTask.Actions.Execute -ne $pythonPath) {
    throw 'A task with this name belongs to another installation. It was not changed.'
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Local Dell G16 touchscreen dashboard. Starts silently at user sign-in, including on battery.' -Force | Out-Null
Write-Host "Enabled '$taskName' at sign-in for $accountName on port $Port."
Write-Host 'Use Start-ScheduledTask -TaskName ''G16 Command Center'' to start it now.'
Write-Host 'Connection address and pairing code update in G16 Command Center.txt on Desktop and in Downloads.'
Write-Host 'The rolling log is in the project .state folder.'
