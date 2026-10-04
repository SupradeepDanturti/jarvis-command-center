"""Bounded discovery of desktop apps from trusted Windows registrations only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

# Never turn a discovered shell/interpreter or installer into a voice shortcut.
BLOCKED = re.compile(r'^(?:cmd|powershell|pwsh|wscript|cscript|mshta|rundll32|regsvr32|reg|'
                     r'python\w*|py\w*|node|npm|bash|sh|wsl|conhost|wt|windowsterminal|'
                     r'powershell_ise|regedit|winget|wmic|schtasks|certutil|bitsadmin|'
                     r'mmc|msiexec|install\w*|unins\w*|setup\w*|update\w*)\.exe$', re.I)

# This fixed script reads shortcuts; it never executes them or accepts browser input.
SHORTCUT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$shell = New-Object -ComObject WScript.Shell
$folders = @([Environment]::GetFolderPath('StartMenu'), [Environment]::GetFolderPath('CommonStartMenu'))
$items = @(foreach ($folder in $folders) {
  if ($folder -and (Test-Path -LiteralPath $folder)) {
    Get-ChildItem -LiteralPath $folder -Filter *.lnk -Recurse -File -ErrorAction SilentlyContinue |
      Select-Object -First 500 | ForEach-Object {
        try {
          $link = $shell.CreateShortcut($_.FullName)
          # Arguments, scripts, URLs and UWP aliases are outside this picker.
          if (-not $link.Arguments) {
            @{name=$_.BaseName; target=$link.TargetPath}
          }
        } catch {}
      }
  }
})
ConvertTo-Json -InputObject $items -Compress
'''


def app_path_records():
    import winreg
    records = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths',
                                    0, winreg.KEY_READ | view) as key:
                    for index in range(min(winreg.QueryInfoKey(key)[0], 500)):
                        try:
                            name = winreg.EnumKey(key, index)
                            with winreg.OpenKey(key, name) as entry:
                                target = winreg.QueryValueEx(entry, '')[0]
                            records.append({'name': Path(name).stem, 'target': target})
                        except OSError:
                            continue
            except OSError:
                continue
    return records


def shortcut_records():
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', SHORTCUT_SCRIPT],
                            capture_output=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW,
                            check=True)
    if len(result.stdout) > 2_000_000:
        raise ValueError('App discovery response too large')
    rows = json.loads(result.stdout.decode('utf-8-sig'))
    return rows if isinstance(rows, list) else []


def executable_path(target):
    if not isinstance(target, str) or len(target) > 1024:
        return None
    path = Path(os.path.expandvars(target.strip().strip('"')))
    if not path.is_absolute() or not re.fullmatch(r'[A-Za-z]:', path.drive) or path.suffix.lower() != '.exe' or BLOCKED.match(path.name):
        return None
    try:
        if not path.is_file():
            return None
        resolved = path.resolve()
    except OSError:
        return None
    if resolved.suffix.lower() != '.exe' or BLOCKED.match(resolved.name):
        return None
    return resolved


def discover_apps():
    if os.name != 'nt':
        return []
    # Prefer the human-readable Start Menu name over a registry executable name.
    rows = shortcut_records() + app_path_records()
    apps = {}
    for row in rows[:2000]:
        if not isinstance(row, dict):
            continue
        path = executable_path(row.get('target'))
        name = row.get('name')
        if path is None or not isinstance(name, str) or not name.strip():
            continue
        if re.search(r'uninstall|unins\b|\bsetup\b|\bupdate\b', name, re.I):
            continue
        identity = str(path).casefold()
        if identity in apps:
            continue
        app_id = 'detected-' + hashlib.sha256(identity.encode()).hexdigest()[:24]
        apps[identity] = {'id': app_id, 'name': re.sub(r'[\x00-\x1f\x7f]', '', name).strip()[:80],
                          'target': str(path), 'args': [], 'process': path.name,
                          'category': 'Installed apps', 'icon': 'apps', 'color': '#a9bacf', 'detected': True}
    return sorted(apps.values(), key=lambda app: app['name'].casefold())[:500]
