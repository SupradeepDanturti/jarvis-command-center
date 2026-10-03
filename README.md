# G16 Command Center

A local touchscreen dashboard for a Dell G16, opened in a Redmi Pad Pro browser. The laptop runs the backend; the tablet displays telemetry and sends registered controls over Wi-Fi.

**Current build:** ten responsive pages with a custom G16 identity, a clock, local ambient video/animations, an automatically detected game library, real CPU/RAM/storage/network/battery readings, NVIDIA sensors when available, graphs, HTTPS with remembered approved browsers, app launching, and Windows media keys. No cloud assets or frontend build step.

Read [SPEC.md](SPEC.md) for the complete target, implementation decisions, security model, and roadmap.

The display uses a small floating dock: **Home, Live (performance), Games, Apps, Clock, Ambient**. **More** opens Hardware, Live graphs, System & controls, and Device access. Home shows one large live reading with compact vitals and launcher icons. Clock and Ambient fill the display; Games uses a sideways poster gallery. There is no permanent sidebar or overview card grid.

All pages have local moving artwork behind the interface, with dimmer backgrounds under detailed readings and the flip clock. By default Home/Hardware/Clock use Event horizon, Live/graphs use Neon drift, Games uses NASA's Black hole, and Apps/System/Device access use Aurora. **More → System & controls → Tablet settings → Background scene** lets you pick one scene for all pages or **Match each screen**. **Pause backgrounds** keeps a still image; preferences are remembered on this browser. Backgrounds pause while the page is hidden, awaiting approval, or using reduced motion. Ambient keeps its own full-screen scene and playback controls; only one video plays at a time.

**Clock** uses a classic split-flap face: hours and minutes flip when they change, with 12/24-hour modes and immersive view. Reduced-motion settings show immediate updates. **Ambient** offers richer Event horizon, Neon drift and Aurora movies, plus NASA's **Black hole** visualization. All four are included locally.

Tablet layouts adjust to both width and the visible browser height, leaving space for the dock and Android safe areas. Landscape keeps the main composition and shortcuts above the dock; portrait centers the live reading and arranges shortcuts in two rows. Rotate normally or use Fullscreen; neither is required to make the layout fit. After an update, reload the tablet page to load the latest styles. Short phone windows and detailed settings can scroll.

Approved browsers automatically report their current display size, visible area, orientation, pixel scale and fullscreen mode while this page is visible. On the laptop, **More → Device access** shows the latest size beside each reporting browser. Reports refresh on resizing/fullscreen changes and every 30 seconds; only the latest report is kept in memory for five minutes. For manual troubleshooting, the tablet’s **More → System & controls → Tablet settings** includes **Display size** and **Copy display details**. Reload once after installing this update to enable automatic reports.

## Run on Windows

```powershell
cd D:\TabletDashboard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\setup-https.ps1
.\scripts\start.ps1 -Lan
```

For laptop-only use omit `-Lan`. Default port is **18761**, chosen to avoid common development ports; override with `-Port 18762`. Use one server worker. If your PowerShell policy blocks the script, run the equivalent directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 18761 --no-access-log --no-proxy-headers --ssl-certfile .state/private/tls/server.pem --ssl-keyfile .state/private/tls/server-key.pem
```

## Connect the Redmi tablet

1. Connect the tablet and laptop to the same private Wi-Fi.
2. Copy **G16 Dashboard CA.cer** from laptop Downloads to the tablet using USB, or download it from the background server's setup-only page at `http://LAPTOP_IP:18760`. If downloading, verify the installed certificate's SHA-256 fingerprint against the trusted laptop connection text file.
3. In tablet Settings, search **CA certificate** and install the file as a CA certificate. Opening the downloaded file directly may show “Install CA certificates in Settings”; follow that instruction.
4. Open the **HTTPS** Wi-Fi address, e.g. `https://192.168.1.100:18761`. Name the browser and request approval.
5. On the laptop, open `https://localhost:18761/#devices`, or choose **More → Device access**. First-time laptop access uses the setup code from **G16 Command Center.txt** on Desktop or in Downloads; tap **Set up this laptop**. In **Approved devices**, match the tablet request's fingerprint and approve it. The same list also appears on System.
6. Tap Fullscreen for a dedicated dashboard view. Swipe horizontally on the dashboard to change pages.

Windows may request firewall access; allow only your trusted local network for this server. If connection fails, verify the Wi-Fi address, port, firewall, and that your Wi-Fi does not isolate devices. No router port forwarding is needed. Approved browsers are remembered for 180 days across restarts, unless revoked or their cookies are cleared. New browsers always require laptop approval. See [SECURITY.md](SECURITY.md) for the full flow and limitations.

The dashboard uses HTTPS. Old `http://` bookmarks on port 18761 produce an empty response because this port now expects TLS. Port 18760 serves only the public certificate and setup instructions, with no credentials, telemetry, or control endpoints. Actual tablet sleep/wake behavior depends on Android and browser settings.

## Start automatically when signing into Windows

```powershell
.\scripts\install-startup.ps1
Start-ScheduledTask -TaskName 'G16 Command Center'
```

This installs a user-specific Task Scheduler entry that launches `.venv\Scripts\pythonw.exe` silently at sign-in. It runs in your desktop session so app launching and media controls work, runs on battery, has no time limit, and retries failed starts up to three times at one-minute intervals. No password is stored and administrator privileges are not requested by the task. Windows permissions may require an administrator to register it on some machines.

Use `-Port` when installing to choose a different port, then restart the task. The manual startup default remains 18761. Stop any manually started dashboard before starting the task on the same port. Duplicate background starts are ignored.

The background server writes **G16 Command Center.txt** to your Desktop and Downloads, containing the tablet URL and current pairing code. These files update after every server restart and check for network address changes every 30 seconds. Redirected Windows folders (such as a OneDrive Desktop) are respected. They are local files and are never served by the dashboard or committed to Git.

The code is also saved in `.state/private/pairing-code.txt`. To view it directly:

```powershell
Get-Content .state\private\pairing-code.txt
```

Logs rotate in `.state/private/server.log` (three files of up to approximately 2 MB each). Device approvals persist in `.state/private/devices.sqlite3`; this database contains hashed credentials and device metadata, not telemetry history. Use `scripts/restart-server.ps1` to restart safely after changes. To stop and disable automatic startup:

```powershell
.\scripts\remove-startup.ps1
```

The server starts when you sign into your account, after Windows boots. It does not control applications before sign-in. Update the tablet's bookmark to the new port. The laptop's Wi-Fi IP can change; a router DHCP reservation can keep the tablet URL stable.

## Configure applications

The default launcher includes Steam, Discord, Spotify, Brave, YouTube, OBS, Edge, Files, Settings, and Terminal. Brand logos are stored locally. Brave is detected in standard machine/user installation locations. **YouTube opens on the laptop in Brave**, with a fixed URL argument; it does not play on the tablet or use your default browser. Website tiles show “Open in Brave” rather than pretending to know which browser tab is open.

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

## Clock and ambient screens

Open **Clock** for the split-flap time display. Switch between 12-hour and 24-hour time. It uses the viewing device's local time and timezone.

Open **Ambient** and choose **Event horizon** for golden orbiting dust and a starfield, **Neon drift** for a synthwave sun and flowing light rails, **Aurora** for luminous curtains over mountains and a lake, or **Black hole** for NASA's edge-on accretion disk visualization. All movies are silent and play locally without internet streaming. Pause/resume motion with the playback button; reduced-motion preferences start with motion paused. Hidden tabs pause the video. Scene selection, pause and clock format are remembered in this browser; no authentication secrets are stored with these preferences.

Clock and Ambient already fill the display. Tap **Immersive view** to hide the dock and request browser fullscreen. **Back to display** or Escape restores the controls. **Keep awake** requests the browser's screen wake lock while visible; Android may release it when you switch apps or turn off the screen.

Three original 1280×720, 16-second loops and their posters are included in the repository. To regenerate them with installed Edge and a separately available Playwright package, run `node scripts/render-ambient.cjs`; the script accepts `G16_PLAYWRIGHT_PATH` as described in VALIDATION.md and also extracts the NASA movie's poster if the local movie is present. The NASA movie itself is unmodified. Asset sources and credits are in [ASSETS.md](ASSETS.md).

## Installed games

**Games** detects installed games from all registered Steam libraries, Epic installation manifests, GOG registry entries, and Riot installation metadata. It excludes Steam redistributables, Unreal Engine/plugins, incomplete installations, and missing installation paths. Swipe/scroll the poster gallery sideways to see more games. Locally cached Steam artwork is displayed when available; other games get a branded fallback cover. Game artwork remains on the laptop and is served only to approved browsers.

Search by title, filter by launcher, and tap **Play on laptop**. Steam and Epic launch through their registered launcher protocols; Riot uses its client with fixed product/patchline arguments; GOG launches its registered executable. The tablet sends only the detected game ID. Game processes and gameplay status are not yet tracked.

Opening Games checks the library, with a one-minute discovery cache. **Refresh** rescans immediately after you install or remove a game. Portable games and launchers without a supported local record need a trusted laptop registration in ignored `config/games.local.json`:

```json
[
  {"name":"My game","target":"D:\\Games\\MyGame\\Game.exe","args":[]}
]
```

Only existing executable files are accepted; do not register shells or interpreters. These local registrations supplement automatic discovery. No launcher account login or online ownership scan is performed.

## Sensor availability

- **psutil:** CPU utilization, per-core load, reported clock, RAM, drives, aggregate disk/network rates, battery/AC, uptime.
- **NVIDIA:** temperature, GPU utilization/clock, VRAM and power when `nvidia-smi` is on PATH. Unsupported fields show unavailable.
- **Later:** HWiNFO detailed CPU/SSD temperatures, fans and additional sensors; RTSS FPS/frame times; OBS control; full media metadata; game process status; macros and power controls.

Graph history begins at startup, lasts at most one hour in memory, and resets on restart. Missing sensors show `—` or unavailable. The app does not use demo readings. Network throughput is traffic across adapters, not an internet speed test.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
node --check frontend/app.js
```

GitHub Actions runs the API/sensor tests and JavaScript syntax check on Windows. The user confirmed physical Redmi HTTPS pairing and dashboard access work. Host app/media behavior still needs an on-device check. See [VALIDATION.md](VALIDATION.md) for reproducible browser checks and [AGENTS.md](AGENTS.md) for project development guidance.

## Project layout

`backend/` — APIs, pairing, sampler and control dispatch

`frontend/` — standalone touch UI, charts and connection handling

`config/` — trusted app registrations

`scripts/` — Windows startup helper

`tests/` — authorization, control boundary and telemetry tests

`.state/` — generated local pairing state (ignored)
