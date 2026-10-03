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

For laptop-only use omit `-Lan`. Default port is 8000; override with `-Port 8001`. Use one server worker. If your PowerShell policy blocks the script, run the equivalent directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## Connect the Redmi tablet

1. Connect the tablet and laptop to the same private Wi-Fi.
2. Open the **Wi-Fi adapter** URL printed by the startup script, e.g. `http://192.168.1.100:8000`.
3. Enter the eight-character pairing code printed in the laptop terminal. It is also saved in `.state/pairing-code.txt` on the laptop.
4. Tap Fullscreen for a dedicated dashboard view. Swipe horizontally on the dashboard to change pages.

Windows may request firewall access; allow only the private network for this server. If connection fails, verify the Wi-Fi address, port, firewall, and that your Wi-Fi does not isolate devices. No router port forwarding is needed. The code changes and paired sessions reset when the server restarts. Sessions expire after 12 hours.

HTTP is intended for a trusted private LAN and does not encrypt traffic. Local HTTPS and individual device management are planned. Browser screen wake lock generally requires HTTPS; fullscreen works over HTTP. Actual tablet sleep/wake behavior depends on Android and browser settings.

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
