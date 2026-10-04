# Jarvis Command Center

Jarvis Command Center: a local touchscreen dashboard with PC telemetry, app and media controls, and an optional voice assistant for any tablet and Windows PC or laptop.

Run it on your Windows desktop or laptop and open it from a tablet browser over your private network. The PC hosts the dashboard; the tablet shows readings and sends approved controls. The project is public at [SupradeepDanturti/jarvis-command-center](https://github.com/SupradeepDanturti/jarvis-command-center).

**Compatibility:** designed for Windows PCs and laptops, with a responsive display for any tablet using a supported HTTPS browser. Available sensors, NVIDIA readings, monitor power controls, microphone/speaker choices and browser keep-awake depend on the machine and browser. Unsupported readings remain unavailable. Physical validation so far uses a Dell G16 and Redmi Pad Pro; that hardware is a tested setup, not a requirement.

**Current build:** seventeen responsive pages with Jarvis branding, a clock, Rest mode and an alarm, local ambient video/animations, an automatically detected game library, real CPU/RAM/storage/network/battery readings, NVIDIA sensors when available, graphs, HTTPS with remembered approved browsers, app launching, Windows media keys, and an optional owner-only Google Calendar briefing with editable preferences. No cloud assets or frontend build step.

**Personal assistant:** on the PC at **https://localhost:18761**, open **More → Connections** for Google Cloud/Desktop-client setup, then enable account access and connect Google. **More → Personalization** sets the agenda address/style/timezone; **More → Today → Brief me for today** checks your primary calendar. Account access and microphone listening start off independently. Calendar writes, Gmail, Sheets, Health, durable memory and background tasks are later milestones. See [assistant setup and boundaries](spec/ASSISTANT_FOUNDATION.md).

Read [the dashboard specification](spec/SPEC.md) for the complete target, implementation decisions, security model, and roadmap. All specifications and design plans are indexed in [spec/](spec/README.md).

**Desk experience:** **More → Now playing** shows the Windows-selected Spotify/Brave session's artwork, title and artist, with session-specific playback controls and progress/seeking when supported. **Clock → Focus timer** adds a shared PC countdown. **More → System & controls → Tablet settings** holds opt-in night dimming, slow rotation, context switching and timer settings. **Hardware** has optional read-only HWiNFO sensor mapping; real extra readings remain unavailable until the owner enables and verifies the provider. See [SETUP.md](SETUP.md#now-playing-focus-and-automatic-display) and the original [experience plan](spec/EXPERIENCE_PLAN.md).


**Optional widgets:** enable original Minimal, Analog and approximate Moon phase clock faces, Weather/AQI or an F1 race countdown in **More → System & controls → Tablet settings → Optional widgets**. All start off; choices stay on this browser. Extra faces appear on Clock, and enabled online screens open from **More → Widgets**. Online data is fetched and cached by the PC; all frontend code/artwork stays local. See [the how-to](SETUP.md#optional-widgets) and [widget specification](spec/WIDGETS_SPEC.md).

**Installation and how-to:** follow [SETUP.md](SETUP.md) for the complete Windows, HTTPS, background startup, tablet pairing, everyday use, Jarvis, update, and troubleshooting walkthrough. Already installed? Go directly to [the update steps](SETUP.md#update-an-existing-installation).

**Rest & alarms:** open it from More or Clock. Enter Rest mode turns supported DDC/CI desk monitors off, keeps the PC/server awake and leaves a dim tablet clock. An enabled Jarvis stays running: say **“Jarvis, enter rest mode”** or **“Jarvis, wake up”** while Windows is unlocked. One shared PC alarm can restore monitors and say “Sir, it's time to wake up,” with five-minute snooze and dismissal. Alarm speech uses the installed Jarvis voice without a microphone, cloud request or API key, including while Windows is locked. See [the how-to](SETUP.md#rest-mode-and-alarm) and [specification](spec/REST_ALARM_SPEC.md).

The display uses a small floating dock: **Home, Live (performance), Games, Apps, Clock, Ambient**. **More** opens Now playing, Hardware, Live graphs, System & controls, Device access, and Jarvis. Home greets you with “At your service,” giving the black-hole artwork the center, with a compact heading, one horizontal CPU/vitals/media strip, and launcher icons. Clock and Ambient fill the display; Games uses a sideways poster gallery with compact covers and 44px Play buttons. There is no permanent sidebar or overview card grid.

With Jarvis enabled, ask **“I want to play games,” “what is the weather?”**, or **“show the clock”** to switch active approved dashboard displays. Every main page, Focus, Weather and F1 has a voice destination. Weather/F1 retain this browser's opt-in settings; missing setup opens Optional widgets. Screen requests do not operate the controls on that page. See [voice navigation](SETUP.md#conversation-alerts-and-history).

For a particular Ambient scene, say **“Change the screen to Ambient mode, Event horizon”** or **“Show Black hole in Ambient.”** Jarvis discovers the available options from the same local catalog as the scene buttons, then selects the requested scene. New registered scenes need no voice-name mapping or prompt edits. Pause and reduced-motion preferences are preserved.

Home's sound controls include previous/play-pause/next and **volume down, mute/unmute, volume up**. They control sound on the PC through Windows media keys; every button remains available in narrow layouts. **Hold volume down/up** to adjust continuously: one step immediately, then repeat after 400 ms until released. A tap keeps Windows' normal volume step (typically two percentage points). Repeats stop when you release, slide off the button, change pages, hide the browser, lose connection, or a command fails; requests do not pile up behind a slow connection. A continuous hold is bounded to ten seconds; lift and hold again if needed.

The play/pause button on Home and System shows **Pause while Windows reports Playing**, and **Play while Paused or Stopped**, including changes made directly on the PC. This follows Windows' currently selected media session, sampled twice a second and shared through the live connection. Players that do not expose Windows media-session state retain a generic **Play or pause** button; we do not infer playback from a sent key. Reload the tablet after updating to load these controls.

All pages have local moving artwork behind the interface, with dimmer backgrounds under detailed readings and the flip clock. Home always uses NASA's **Black hole**, with the source credit displayed. By default Hardware/Clock use Event horizon, Live/graphs use Neon drift, Games uses Black hole, and Apps/System/Device access use Aurora. **More → System & controls → Tablet settings → Background scene** lets you pick one scene for the other pages or **Match each screen**. **Pause backgrounds** also pauses Home; preferences are remembered on this browser. Backgrounds pause while the page is hidden, awaiting approval, or using reduced motion. Ambient keeps its own full-screen scene and playback controls; only one video plays at a time.

**Clock** uses a classic split-flap face: hours and minutes flip when they change, with 12/24-hour modes and immersive view. Reduced-motion settings show immediate updates. **Ambient** offers richer Event horizon, Neon drift and Aurora movies, plus NASA's **Black hole** visualization. All four are included locally.

Tablet layouts adjust to both width and the visible browser height, leaving space for the dock and Android safe areas. Landscape keeps the main composition and shortcuts above the dock; portrait reflows the telemetry strip and arranges shortcuts in two rows. Rotate normally or use Fullscreen; neither is required to make the layout fit. After an update, reload the tablet page to load the latest styles. Short phone windows and detailed settings can scroll.

Approved browsers automatically report their current display size, visible area, orientation, pixel scale and fullscreen mode while this page is visible. On the PC, **More → Device access** shows the latest size beside each reporting browser. Reports refresh on resizing/fullscreen changes and every 30 seconds; only the latest report is kept in memory for five minutes. For manual troubleshooting, the tablet’s **More → System & controls → Tablet settings** includes **Display size** and **Copy display details**. Reload once after installing this update to enable automatic reports.

## Run on Windows

For a new installation, use the ordered [installation guide](SETUP.md). The short commands below are for a temporary terminal run; the background task described later also publishes connection files and serves tablet certificate setup.

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

## Connect a tablet

1. Connect the tablet and laptop to the same private Wi-Fi.
2. Copy **G16 Dashboard CA.cer** from laptop Downloads to the tablet using USB, or download it from the background server's setup-only page at `http://LAPTOP_IP:18760`. If downloading, verify the installed certificate's SHA-256 fingerprint against the trusted laptop connection text file.
3. In tablet Settings, search **CA certificate** and install the file as a CA certificate. Opening the downloaded file directly may show “Install CA certificates in Settings”; follow that instruction.
4. Open the **HTTPS** Wi-Fi address, e.g. `https://192.168.1.100:18761`. Name the browser and request approval.
5. On the PC, open `https://localhost:18761/#devices`, or choose **More → Device access**. First-time laptop access uses the setup code from **G16 Command Center.txt** on Desktop or in Downloads; tap **Set up this laptop**. In **Approved devices**, match the tablet request's fingerprint and approve it. The same list also appears on System.
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

Logs rotate in `.state/private/server.log` (three files of up to approximately 2 MB each). Device approvals persist in `.state/private/devices.sqlite3`; this database contains hashed credentials and device metadata, not telemetry history. Use `scripts/restart-server.ps1` to restart safely after backend changes. Existing task names, certificate names and `G16 Command Center.txt` connection files retain their installed names so updates preserve startup and CA trust. To stop and disable automatic startup:

```powershell
.\scripts\remove-startup.ps1
```

The server starts when you sign into your account, after Windows boots. It does not control applications before sign-in. Update the tablet's bookmark to the new port. The PC's Wi-Fi IP can change; a router DHCP reservation can keep the tablet URL stable.

## Configure applications

The default launcher includes Steam, Discord, Spotify, Brave, YouTube, OBS, Files, Settings, and Terminal. Edge is excluded from the default shortcuts. Brand logos are stored locally. Brave is detected in standard machine/user installation locations. **YouTube opens on the PC in Brave**, with a fixed URL argument; it does not play on the tablet or use your default browser. Website tiles show “Open in Brave” rather than pretending to know which browser tab is open.

On the approved Windows browser at `https://localhost:18761`, open **More → System & controls → App shortcuts**. Choose an app from **Detected Windows apps**, then **Add app**. Use **Remove** to free a slot, or **Detect apps** to check installations again (discovery is cached for 30 seconds). The limit is **25 apps total**, including defaults. Apps shows the full list; Home keeps its first eight shortcuts. Tablets receive the shared list automatically within 15 seconds, or immediately after reload.

Detection reads Windows App Paths and Start Menu executable shortcuts, plus installed packaged apps registered in the Windows Start menu, including ChatGPT and Claude. Packaged apps launch through their fixed Windows application identity; browsers still submit only a detected ID. Local executable icons and packaged-app logos are shown automatically for added apps. Shortcuts requiring arbitrary arguments, scripts/URLs, interpreters, shells and installers remain excluded; unregistered portable apps may not appear. App additions/removals save privately in ignored `.state/private/apps.json` and survive server restarts without changing `config/apps.local.json`. Only the direct-loopback owner can manage them; browsers submit a detected ID, never executable paths or arguments. Jarvis discovers the full available inventory on request, using the thirty-second Windows cache, without restarting after shortcut changes.

For initial custom registrations, copy `config/apps.json` to `config/apps.local.json` and edit it **on the PC**, then restart the backend. The local override is excluded from Git. Once the settings picker has saved a list, `.state/private/apps.json` takes precedence over that initial configuration.

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

Clock and Ambient already fill the display. Tap **Immersive view** to hide the dock and request browser fullscreen. **Back to display** or Escape restores the controls.

**Keep-awake starts automatically on every approved screen**, including after reloading. It requests the browser's screen wake lock while the dashboard is visible, releases it when you leave, and requests it again when you return. Browser releases trigger retries with a delay of 2 seconds, increasing up to 30 seconds. It does not need a playing background or fullscreen.

Check **More → System & controls → Tablet settings → Screen keep-awake**: **Active · screen stays on** means the browser actually granted the lock. **Turn keep-awake off** restores normal screen sleep and remembers that choice in this browser; tap **Keep screen awake** to enable it again. Clock/Ambient's **Screen awake** button also turns it off; **Keep awake** enables it. Unpairing releases the lock.

If the status says **Blocked by browser**, check the tablet's Battery saver setting, then tap **Retry keep-awake**. Use the trusted HTTPS address in a browser with screen wake-lock support. Android or the browser can decline or release a request; this feature cannot override an unsupported browser, a manual screen lock, or an operating-system restriction. Reload the tablet once to load this update.

Three original 1280×720, 16-second loops and their posters are included in the repository. To regenerate them with installed Edge and a separately available Playwright package, run `node scripts/render-ambient.cjs`; the script accepts `G16_PLAYWRIGHT_PATH` as described in VALIDATION.md and also extracts the NASA movie's poster if the local movie is present. The NASA movie itself is unmodified. Asset sources and credits are in [ASSETS.md](ASSETS.md).

## Installed games

**Games** detects installed games from all registered Steam libraries, Epic installation manifests, GOG registry entries, and Riot installation metadata. It excludes Steam redistributables, Unreal Engine/plugins, incomplete installations, and missing installation paths. Swipe/scroll the poster gallery sideways to see more games. Locally cached Steam artwork is displayed when available; other games get a branded fallback cover. Game artwork remains on the PC and is served only to approved browsers.

Search by title, filter by launcher, and tap **Play on PC**. Steam and Epic launch through their registered launcher protocols; Riot uses its client with fixed product/patchline arguments; GOG launches its registered executable. The tablet sends only the detected game ID. Opt-in automatic display can recognize a foreground executable inside a trusted game installation or an exact local registration. Launchers/helpers and ambiguous matches are excluded; unsupported foreground processes cause no automatic switch.

Opening Games checks the library, with a one-minute discovery cache. **Refresh** rescans immediately after you install or remove a game. Portable games and launchers without a supported local record need a trusted laptop registration in ignored `config/games.local.json`:

```json
[
  {"name":"My game","target":"D:\\Games\\MyGame\\Game.exe","args":[]}
]
```

Only existing executable files are accepted; do not register shells or interpreters. These local registrations supplement automatic discovery. No launcher account login or online ownership scan is performed.

## Jarvis voice on the PC

Open **More → Jarvis** on the approved laptop browser. Expand **Manage API key** if a key is already saved. Paste your OpenAI API key into the password field and choose **Save key**. Do not paste it into chat, source files, or Git. Windows encrypts it for the current user in the existing private-state directory; saving does not validate billing or model access.

Choose a **PC microphone**, **Preview voice**, then **Turn on Jarvis**. The same microphone dropdown is also in **More → System & controls**, with an **Open Jarvis** shortcut. Selection persists across restarts. Tap the refresh arrow after connecting a webcam/headset. Stereo Mix is excluded; the integrated webcam's nearby microphone is Windows' Microphone Array. Headset/USB inputs are listed when Windows exposes a compatible capture device. The user's Logitech is **Microphone (Logi Webcam C920e)**.

Say “Jarvis, open YouTube,” “open Discord,” “turn the volume down,” or “how much memory am I using?” Wake detection and the synthetic Jarvis-style voice run locally on the CPU. The short command clip/text and tool results go to OpenAI. Jarvis can open available apps from the full **Detected Windows apps** catalog as well as saved shortcuts, even when they are not selected for the Apps screen. It discovers the current IDs/names before choosing one; opening an app does not save a shortcut. Media controls and hardware status are also supported; no arbitrary shell, shutdown or smart-home control.

Ask **“Jarvis, open Wikipedia”** or give a website address to open it in Brave. The agent can supply a complete HTTP or HTTPS URL for your requested website, without a saved shortcut. Uncertain site names use native web search to find the official address; ambiguous requests prompt a question. Website opening shares the one PC-control limit with app/media actions. This requests a browser tab; it does not confirm page loading or interact with accounts/forms.

Say **“Jarvis, introduce yourself”** or **“play your introduction”** to hear the saved introduction through your selected Jarvis speaker. Its wording lives in **`backend/agent/jarvis_intro.txt`**, read on each request and limited to five hundred characters so it plays in full. The exact commands use the recognized transcript directly; no conversation-model request is needed, though speech transcription still uses OpenAI. Other introduction requests can use the registered `play_intro` tool and always speak the saved wording. It never plays automatically at startup. The system prompt now includes contextual persona examples for clear confirmations, occasional dry wit and factual capabilities.

The **OpenAI Agents SDK** handles conversation turns with parallel tool calling enabled and tracing disabled. Ask **“Open Steam, show games and read my CPU”** to combine one PC control, one screen request and one hardware read. Parent dispatch remains serialized, and repeated tool calls reuse their original result. The spoken-style system prompt is editable in **`backend/agent/jarvis_prompt.txt`** and loaded each turn. Update the optional voice dependencies before restarting after this migration.

OpenAI uses **GPT Transcribe** (`gpt-transcribe`) for speech recognition and **GPT-6 Luna** (`gpt-6-luna`, reasoning effort `none`) for command interpretation and replies. Piper generates the final voice locally, routed to the **Jarvis speaker** independently of Windows’ default output. **Auto · built-in speakers** selects the Realtek speaker endpoint rather than headphones. You can select another detected speaker on Jarvis or System & controls; changing it requires Jarvis to be off. If the speaker disappears, Jarvis reports an error instead of switching to headphones. The system prompt asks for Jarvis-style British phrasing and dry wit. Native OpenAI **web search** handles searches and current information; clickable sources appear beside the answer rather than being read aloud.

After Jarvis replies, speak again within **15 seconds** without another “Jarvis”. **Follow-up listening** offers Off, 15 or 30 seconds; turn Jarvis off before changing it. Silence or “thank you” returns to wake-word listening.

**Jarvis** has an Iron Man theme with a red/gold helmet image and cyan reactor rings. Home can show a small armed indicator; other screens stay quiet while awaiting the wake word. Active recording, understanding, processing, speech, follow-up and warnings show the current phase/reply. Widgets reserve a separate activity strip above their readings; other screens use a compact header overlay, including immersive Clock/Ambient and Rest. The Home HUD includes live CPU/RAM/GPU readings. Activity never captures taps and hides on disconnect, expired voice status or unpairing; motion respects reduced-motion settings.

**Alerts on / Alerts off** controls local spoken hardware warnings while Jarvis is running. CPU or memory at **90%**, or GPU temperature at **70°C**, must appear in three fresh readings. Warnings wait until Jarvis is listening for its wake word, then speak through the dedicated speaker using Piper without an OpenAI request. All warnings share a **one-hour cooldown** stored on this laptop across worker/server restarts; if readings remain high, another warning may sound after that hour. Switching alerts off cancels pending warning audio without turning Jarvis off. No alerts run while Jarvis is off or Windows is locked.

**Your conversations** saves the latest 500 text exchanges, action results and sources privately on this laptop across restarts. The latest six conversation exchanges (excluding automatic hardware warnings) accompany each OpenAI turn so follow-up answers retain context. Audio is not saved. Scroll the history or choose **Earlier conversations**; the localhost owner can choose **Clear history**, which also turns Jarvis off.

Closing the webpage keeps Jarvis running. **Turn off Jarvis** releases the microphone and models. Listening pauses while Windows is locked and while processing/speaking. A server restart always starts with Jarvis off. Any approved browser can toggle it; only an approved direct-localhost owner can save or remove the key. OpenAI API billing is separate from ChatGPT subscriptions.

Optional setup on a new laptop:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe scripts/install-voice.py
```

The installer downloads only the ONNX runtime voice/wake models into ignored private state and verifies pinned checksums. It does not install another assistant's UI. See [JARVIS_SPEC.md](spec/JARVIS_SPEC.md) and the **Setup & supported commands** link on the Jarvis screen.

## Sensor availability

- **psutil:** CPU utilization, per-core load, reported clock, RAM, drives, aggregate disk/network rates, battery/AC, uptime.
- **NVIDIA:** temperature, GPU utilization/clock, VRAM and power when `nvidia-smi` is on PATH. Unsupported fields show unavailable.
- **Later:** HWiNFO detailed CPU/SSD temperatures, fans and additional sensors; RTSS FPS/frame times; OBS control; full media metadata; game process status; macros and power controls.

Graph history begins at startup, lasts at most one hour in memory, and resets on restart. Missing sensors show `—` or unavailable. The app does not use demo readings. Network throughput is traffic across adapters, not an internet speed test.

## Development checks

Changes must use a feature branch and a pull request to main. Direct commits/pushes to main are prohibited. The human owner reviews and completes merges; agents leave PRs awaiting approval. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, owner exception for self-authored PRs, and GitHub enforcement.

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
