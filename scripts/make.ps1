param(
    [Parameter(Mandatory)][ValidateSet('help', 'install', 'install-dev', 'install-voice', 'https', 'run', 'run-local', 'startup', 'start', 'stop', 'restart', 'remove-startup', 'test', 'check')][string]$Target,
    [string]$Python = 'python',
    [ValidateRange(1024, 65535)][int]$Port = 18761,
    [ValidateSet(0, 1)][int]$Jarvis = 1,
    [ValidateSet(0, 1)][int]$Assistant = 1
)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$venvPython = Join-Path $projectPath '.venv\Scripts\python.exe'

function Invoke-Python([string[]]$Arguments) {
    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Require-Python {
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run make install first.' }
}

function Install-Dependencies([string]$Requirements) {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Invoke-Python -Arguments @('-m', 'pip', 'install', '-r', $Requirements)
}

function Require-Https {
    foreach ($name in @('server.pem', 'server-key.pem')) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectPath ".state\private\tls\$name"))) {
            throw 'Run make https before starting the dashboard.'
        }
    }
}

function Get-StartupTask {
    $task = Get-ScheduledTask -TaskName 'G16 Command Center'
    if ($task.Actions.Execute -ne (Join-Path $projectPath '.venv\Scripts\pythonw.exe')) {
        throw 'This startup task belongs to another installation.'
    }
    return $task
}

$options = @{ NoJarvis = ($Jarvis -eq 0); NoAssistant = ($Assistant -eq 0) }
switch ($Target) {
    'help' {
        @'
make install          Create/reuse .venv; install dashboard + Jarvis and models
make install JARVIS=0 Install dashboard only
make install-dev      Install dashboard and test dependencies
make install-voice    Install optional Jarvis dependencies and verified models
make https            Prepare HTTPS and Windows CA trust (one-time setup)
make run              Run HTTPS in this terminal for PC + tablet; Ctrl+C stops
make run-local        Run HTTPS for the PC only
make startup          Register silent sign-in startup with these options
make start / stop     Start/stop this installation's registered background task
make restart          Safely restart the registered task with its saved options
make remove-startup   Stop and unregister this installation's startup task
make test             Run the backend test suite (install-dev first)
make check            Check all frontend/script JavaScript (requires Node.js)

Defaults: PORT=18761 JARVIS=1 ASSISTANT=1 PYTHON=python
Example: make run JARVIS=0 ASSISTANT=0 PORT=18762
Background options are saved by make startup; start/restart use that task.
No target deletes private state, approvals, certificates or saved connections.
'@ | Write-Host
    }
    'install' {
        Install-Dependencies 'requirements.txt'
        if ($Jarvis) {
            Install-Dependencies 'requirements-voice.txt'
            Invoke-Python -Arguments @('scripts/install-voice.py')
        }
    }
    'install-dev' { Install-Dependencies 'requirements-dev.txt' }
    'install-voice' {
        Require-Python
        Install-Dependencies 'requirements-voice.txt'
        Invoke-Python -Arguments @('scripts/install-voice.py')
    }
    'https' { Require-Python; & "$PSScriptRoot\setup-https.ps1" }
    { $_ -in 'run', 'run-local' } {
        Require-Python
        Require-Https
        & "$PSScriptRoot\start.ps1" -Lan:($Target -eq 'run') -Port $Port @options
        exit $LASTEXITCODE
    }
    'startup' {
        Require-Python
        Require-Https
        & "$PSScriptRoot\install-startup.ps1" -Port $Port @options
    }
    'start' { Require-Https; Get-StartupTask | Start-ScheduledTask }
    'stop' { Get-StartupTask | Stop-ScheduledTask }
    'restart' { Require-Https; & "$PSScriptRoot\restart-server.ps1" }
    'remove-startup' { & "$PSScriptRoot\remove-startup.ps1" }
    'test' { Require-Python; Invoke-Python -Arguments @('-m', 'pytest', '-q') }
    'check' {
        Get-ChildItem frontend/*.js, scripts/*.cjs | ForEach-Object {
            & node --check $_.FullName
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
}
