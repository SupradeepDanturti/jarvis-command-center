# G16 Command Center

A local touchscreen dashboard for a Dell G16, opened in a Redmi Pad Pro browser. The laptop runs the backend; the tablet displays telemetry and sends registered controls over Wi-Fi.

**Foundation build:** six responsive pages, real CPU/RAM/storage/network/battery readings, NVIDIA sensors when available, history graphs, paired device access, configured app launching, and Windows media keys. No cloud assets or frontend build step.

Read [SPEC.md](SPEC.md) for the complete target, implementation decisions, security model, and roadmap.

## Run on Windows

```powershell
cd D:\TabletDashboard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\start.ps1 -Lan
```

For laptop-only use omit `-Lan`. Default port is **18761**, chosen to avoid common development ports; override with `-Port 18762`. Use one server worker. If your PowerShell policy blocks the script, run the equivalent directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 18761 --no-access-log
```

## Connect the Redmi tablet

1. Connect the tablet and laptop to the same private Wi-Fi.
2. Open the **Wi-Fi adapter** URL printed by the startup script, e.g. `http://192.168.1.100:18761`.
3. Enter the eight-character pairing code from **G16 Command Center.txt** on Desktop or in Downloads for the background server. For manual runs it is printed in the terminal and saved in `.state/pairing-code.txt`.
4. Tap Fullscreen for a dedicated dashboard view. Swipe horizontally on the dashboard to change pages.

Windows may request firewall access; allow only the private network for this server. If connection fails, verify the Wi-Fi address, port, firewall, and that your Wi-Fi does not isolate devices. No router port forwarding is needed. The code changes and paired sessions reset when the server restarts. Sessions expire after 12 hours.

HTTP is intended for a trusted private LAN and does not encrypt traffic. Local HTTPS and individual device management are planned. Browser screen wake lock generally requires HTTPS; fullscreen works over HTTP. Actual tablet sleep/wake behavior depends on Android and browser settings.

## Start automatically when signing into Windows

```powershell
.\scripts\install-startup.ps1
Start-ScheduledTask -TaskName 'G16 Command Center'
```

This installs a user-specific Task Scheduler entry that launches `.venv\Scripts\pythonw.exe` silently at sign-in. It runs in your desktop session so app launching and media controls work, runs on battery, has no time limit, and retries failed starts up to three times at one-minute intervals. No password is stored and administrator privileges are not requested by the task. Windows permissions may require an administrator to register it on some machines.

Use `-Port` when installing to choose a different port, then restart the task. The manual startup default remains 18761. Stop any manually started dashboard before starting the task on the same port. Duplicate background starts are ignored.

The background server writes **G16 Command Center.txt** to your Desktop and Downloads, containing the tablet URL and current pairing code. These files update after every server restart and check for network address changes every 30 seconds. Redirected Windows folders (such as a OneDrive Desktop) are respected. They are local files and are never served by the dashboard or committed to Git.

The code is also saved in `.state/pairing-code.txt`. To view it directly:

```powershell
Get-Content .state\pairing-code.txt
```

Logs rotate in `.state/server.log` (three files of up to approximately 2 MB each). To stop and disable automatic startup:

```powershell
.\scripts\remove-startup.ps1
```

The server starts when you sign into your account, after Windows boots. It does not control applications before sign-in. Update the tablet's bookmark to the new port. The laptop's Wi-Fi IP can change; a router DHCP reservation can keep the tablet URL stable.

## Configure applications

Copy `config/apps.json` to `config/apps.local.json` and edit it **on the laptop**. Restart the backend to reload. The local override is excluded from Git.

```json
[
  {
    "id": "editor",
    "name": "VS Code",
    "category": "Development",
    "icon": "<> ",
    "color": "#76dbe7",
    "target": "C:\\Users\\YOUR_USER\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
    "args": [],
    "process": "Code.exe"
  }
]
```

The UI sends only the registered ID. Executables run without a shell; configured arguments are separate array items. Do not register a shell or interpreter as an unrestricted command gateway. URI handlers are allowed only for the predefined Steam, Discord, Spotify, Edge and Settings schemes. Installation of a URI handler is verified by Windows when launched; the UI reports failures. Running status uses configured process names, so it is an indicator rather than a full process ownership model.

## Sensor availability

- **psutil:** CPU utilization, per-core load, reported clock, RAM, drives, aggregate disk/network rates, battery/AC, uptime.
- **NVIDIA:** temperature, GPU utilization/clock, VRAM and power when `nvidia-smi` is on PATH. Unsupported fields show unavailable.
- **Later:** HWiNFO detailed CPU/SSD temperatures, fans and additional sensors; RTSS FPS/frame times; OBS control; full media metadata; games; macros and power controls.

Graph history begins at startup, lasts at most one hour in memory, and resets on restart. Missing sensors show `—` or unavailable. The app does not use demo readings. Network throughput is traffic across adapters, not an internet speed test.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
node --check frontend/app.js
```

GitHub Actions runs the API/sensor tests and JavaScript syntax check on Windows. Physical Redmi pairing and host app/media behavior still need an on-device check.

## Project layout

`backend/` — APIs, pairing, sampler and control dispatch

`frontend/` — standalone touch UI, charts and connection handling

`config/` — trusted app registrations

`scripts/` — Windows startup helper

`tests/` — authorization, control boundary and telemetry tests

`.state/` — generated local pairing state (ignored)
