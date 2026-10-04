# Jarvis Command Center — installation and setup

Any supported Windows PC or laptop can run Jarvis Command Center in the background. The tablet opens it in a browser over your private Wi-Fi. No Android app or frontend build is required.

**Already installed?** Go to [Everyday use](#everyday-use) or [Update an existing installation](#update-an-existing-installation). Normal updates do not require a new certificate or fresh approval of the same browser.

## 1. Prepare your Windows PC

Install Git and 64-bit Python on Windows. The current installation was tested with **Python 3.14.2**. Both devices need the same private Wi-Fi, and the tablet browser must trust Android's installed CA certificates. Internet access is needed to install dependencies and to use Jarvis's OpenAI features.

Check the tools in PowerShell:

```powershell
git --version
python --version
```

The examples use `D:\TabletDashboard`. If you have no D: drive, choose another permanent folder and use that path throughout. The startup task stores the installation path.

```powershell
git clone https://github.com/SupradeepDanturti/g16-command-center.git D:\TabletDashboard
cd D:\TabletDashboard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The repository is private. Sign in with a GitHub account that has access if Git asks. If the project already exists on this laptop, skip cloning and use [the update steps](#update-an-existing-installation).

## 2. Set up trusted HTTPS

Run once in the project folder:

```powershell
.\scripts\setup-https.ps1
```

This creates this laptop's certificates, protects the private files, and installs the public CA for your Windows account. If Windows asks you to trust **G16 Command Center Local CA**, confirm that exact name before accepting.

The public **G16 Dashboard CA.cer** is exported to Desktop and Downloads. That is the tablet installation file. Keep the private files in `.state/private/` on the laptop.

If PowerShell blocks a helper because of its execution policy, invoke that specific project script with a process-scoped override:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-https.ps1
```

Use the same invocation for the other `.ps1` helpers if needed. It does not change the machine's saved execution policy.

## 3. Enable background startup

```powershell
.\scripts\install-startup.ps1
Start-ScheduledTask -TaskName 'G16 Command Center'
```

The app starts now and automatically whenever **you sign into Windows**. It runs silently in your desktop session, including on battery; no open terminal is needed. It does not serve before sign-in or while the laptop is asleep. Some Windows installations require an administrator to register the task; the task itself runs with your normal user privileges.

If Windows requests firewall access, allow the server on your trusted **Private** network. The dashboard uses **18761** and certificate setup uses **18760**. No router port forwarding is needed.

After startup, open **G16 Command Center.txt** on Desktop or in Downloads. It contains the tablet URL, laptop setup code, public certificate download URL, and CA fingerprint. The background process refreshes it when the laptop's network address changes.

For a temporary run in an open terminal, use this **instead of** the background task:

```powershell
.\scripts\start.ps1 -Lan
```

Stop it with **Ctrl+C** before starting the task on the same port. The temporary helper prints the setup code in the terminal; it does not create the connection text files or run the certificate-download listener. Transfer the exported public certificate by USB. Omit `-Lan` for laptop-only testing.

## 4. Set up the laptop browser

1. Open **https://localhost:18761** on the laptop.
2. On first access, enter the setup code from **G16 Command Center.txt** and choose **Set up this laptop**. A temporary run prints its code in the terminal instead.
3. Open **More → Device access**, where you approve the tablet next.

Use `localhost` for owner tasks such as approving devices and managing the key. The laptop's Wi-Fi IP address does not provide owner access, even when opened on the laptop itself.

## 5. Install the certificate on the Redmi

1. Copy **G16 Dashboard CA.cer** to the tablet using USB. Alternatively, download it from the connection file's setup URL: `http://LAPTOP_IP:18760`.
2. In tablet **Settings**, search for **CA certificate**. Choose the option to install a CA certificate and select the `.cer` file. Menus vary by Android/HyperOS version; you may need your tablet PIN.
3. If opening the file shows **“Install CA certificates in Settings”**, close the message and install through Settings. The message alone does not install it.
4. For an HTTP download, compare the installed certificate's **SHA-256 fingerprint** with the trusted laptop text file before using it. Use USB if you cannot verify it.

This is a one-time trust setup for this laptop. If the browser shows a certificate error, fix trust and the address before continuing; do not bypass the warning.

## 6. Approve and connect the tablet

1. Open the **HTTPS tablet URL** from **G16 Command Center.txt**, for example `https://192.168.2.12:18761`. Use your current address. `localhost` on the tablet points to the tablet itself.
2. Name the browser **Redmi Pad Pro** and tap **Request approval**. Leave the waiting page open.
3. On the laptop at **https://localhost:18761/#devices**, find the pending request under **Approved devices**. Match the tablet's name and request fingerprint, then choose **Approve**.
4. The tablet checks automatically; reload once if it still shows the waiting page.
5. Use landscape mode and tap the top-right **Fullscreen** button.

Approval is remembered for up to **180 days**, including server restarts. Keep using the same browser/profile and address. Clearing cookies, switching browser/profile, changing the hostname/IP, or revoking access requires fresh approval. The tablet can request approval without a setup code.

## Everyday use

Open the tablet bookmark after signing into the laptop. The dock has **Home, Live, Games, Apps, Clock, Ambient**, and **More**. More contains Hardware, Live graphs, System & controls, Device access, and Jarvis.

- **Home:** black-hole artwork, live readings, app shortcuts, playback and laptop volume. Hold volume up/down for repeated adjustments; release to stop.
- **Games:** search/filter installed games and choose **Play on PC**. Tap **Refresh** after installing/removing games. This is installed-game discovery; gameplay is not tracked.
- **Apps:** launch registered laptop applications. **YouTube opens on the laptop in Brave**, which must be installed.
- **Clock / Ambient:** flip clock or silent local movies. **Immersive view** hides the dock; **Back to display** restores it.
- **System & controls → Tablet settings:** backgrounds, motion, keep-awake, display size, and Jarvis microphone/speaker settings.

**Keep-awake starts automatically** while the approved page is visible. **Screen keep-awake → Active · screen stays on** confirms the browser granted it. If blocked, check battery saver and tap **Retry keep-awake**. Turning it off is remembered in that browser. It cannot override a manual tablet lock or laptop sleep.

## Add or remove app shortcuts

On your approved Windows browser at `https://localhost:18761/#system`, open **More → System & controls → App shortcuts**. Select from **Detected Windows apps**, then tap **Add app**. You can keep up to **25 apps total**; use **Remove** to free a slot. **Detect apps** checks again, with a 30-second discovery cache. Added apps appear on Apps; Home keeps the first eight. Tablets update their shared list within 15 seconds, or on reload.

This picker detects desktop executable shortcuts and installed packaged apps registered in the Windows Start menu, including ChatGPT and Claude. Added apps use their locally installed logos. Choose **Detect apps** after an installation; shortcuts needing arbitrary extra arguments may be absent. Shells, interpreters and installers are excluded. Changes save in ignored private state and persist after a server restart; your existing local configuration is retained as the initial list. After the first settings save, the private list takes precedence. Tablet browsers can launch saved apps; registration remains restricted to the approved Windows owner.

Jarvis can open apps from the full detected list even if you have not added them to the Apps screen. Ask **“Jarvis, open ChatGPT,” “open Claude,”** or name another detected app. It first reads current available app IDs/names, then opens the matching app. This uses the same thirty-second Windows discovery cache and does not add a shortcut or count against the twenty-five saved-app limit. New apps and shortcut edits reach the next discovery without restarting Jarvis; use **Detect apps** after installing/removing an app. Ambiguous names prompt a question; unavailable apps fail visibly. Browser buttons continue to launch saved shortcuts only.

## Optional: set up Jarvis

Jarvis uses the **laptop microphone and speaker**. The tablet controls its switch and shows activity; it does not record your voice. The dashboard works without installing Jarvis.

### Install the local voice components

```powershell
cd D:\TabletDashboard
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe scripts/install-voice.py
.\scripts\restart-server.ps1
```

The installer downloads checksum-verified Piper Jarvis and wake-word models into private local state. It does not install another assistant's frontend. If running manually, stop/start that server instead of using the scheduled-task restart helper.

### Choose audio and save the key

1. In the approved laptop browser at **https://localhost:18761**, open **More → Jarvis**.
2. Expand **Manage API key**, paste your OpenAI API key into the password field, and choose **Save key**. Do not put it in chat, source files, or Git. Saving confirms encrypted storage, not billing/model access. API billing is separate from ChatGPT subscriptions.
3. With Jarvis off, choose **PC microphone**. For the current webcam, use **Microphone (Logi Webcam C920e)**. Tap refresh after connecting a microphone. Enable desktop microphone access in Windows Settings if necessary.
4. Choose **Jarvis speaker**. **Auto · built-in speakers** prefers Realtek speakers independently of Windows' headphone output. Another listed speaker can be selected. Missing speakers produce an error rather than a headphone fallback.
5. Choose **Preview voice**, then **Turn on Jarvis**.

Audio selection is also in **More → System & controls**. Turn Jarvis off before changing audio devices or **Follow-up listening**.

### Conversation, alerts, and history

To open another website in Brave, say **“Jarvis, open Wikipedia,” “open NASA's website,”** or provide its web address. The agent supplies a complete HTTP or HTTPS URL for the site you requested; no saved app/website shortcut is required. If the official address is uncertain, it uses native search first; if the site name is ambiguous, it asks which one. It opens one new tab per request, sharing the PC-control limit with app launches/media. It does not click website controls, change accounts, install downloads or confirm page loading. File/script/browser/OS schemes and URLs with embedded credentials are refused. Brave must be installed; another browser is not selected automatically.

Try **“Jarvis, open YouTube,” “open Steam,” “how much memory am I using?”**, or **“search NASA for a recent mission update.”** After a reply, speak again within **15 seconds** without repeating the wake phrase. Follow-up listening offers Off, 15, or 30 seconds. Silence or a closing phrase such as “thank you” returns it to wake listening.

Jarvis can also switch the dashboard: **“I want to play games”** opens Games; **“what is the weather?”** opens Weather & air quality for this browser's selected city; **“show the next F1 race”** opens F1. Ask to show Home, Live performance, Apps, Hardware, Live graphs, Clock, Focus timer, Ambient, Now playing, System & controls, Device access, Rest & alarms, Widgets or Jarvis. Opening a screen does not launch a game/app, start a timer, enter Rest or operate its controls. Enable Weather/F1 in **System & controls → Tablet settings → Optional widgets** first, and select a city for weather; otherwise the request opens that setup area without enabling online feeds.

Voice navigation reaches already connected, visible approved browsers and holds automatic rotation for two minutes like touch. New/reloaded, hidden or reconnecting browsers do not replay old requests. Requests expire after ten seconds and are cancelled by disabling Jarvis or locking Windows. Finish an open dialog before asking to change screens. In active Rest, say **“Jarvis, wake up”** first. Reload the laptop/tablet after this update and turn Jarvis on again after the required backend restart.

To choose an Ambient scene by voice, say **“Change the screen to Ambient mode, Event horizon,” “Show Black hole in Ambient,”** or ask to switch to another available scene. Jarvis first reads the current scene options, then requests the matching scene and opens Ambient. Unknown or unclear choices prompt a question rather than a guessed ID. **“Open Ambient”** alone keeps the current scene. Scene changes preserve paused motion/reduced motion and save the selection on each receiving browser.

Ambient buttons, background choices and voice options share **`config/ambient-scenes.json`**. To add a local scene, register a unique ID with `name`, `description`, `file` (local filename stem), `type` (`video/webm` or `video/mp4`) and `credit`, and place its matching movie and `.jpg` poster in `frontend/assets/`. The catalog accepts at most 32 valid local entries; unavailable files and invalid entries are excluded. Reload displays after changing the catalog to load their updated choices; an enabled Jarvis reads fresh options on its next turn without changing its prompt or voice code. No URL, path or command can be supplied by the voice model.

To customise Jarvis's wording, edit the local **`backend/jarvis_prompt.txt`**. It uses tagged role/style/actions/apps/screens/search/security/examples sections and substitutes **`{now}`** with the current local time. The file is loaded each conversation turn, so later wording edits need no worker restart. Tools and authorization remain defined and checked separately in code. Jarvis uses the **OpenAI Agents SDK** over Responses, with parallel tool calling enabled and tracing disabled. You can ask **“Open Steam, show games and read my CPU”** in one request. One physical PC control, one screen request and one hardware read may share a turn; app and Ambient discovery have independent read slots. Physical controls run one at a time and duplicate calls never repeat an action. App discovery sends available IDs/names to OpenAI for matching, without executable paths or launch arguments. Install/update `requirements-voice.txt` before the backend restart for this SDK migration.

Say **Jarvis**, pause briefly, then give the command. The dedicated local model also accepts **Hey Jarvis**. Rapid name-plus-command speech can be missed; your room, microphone and pronunciation still affect recognition.

This app uses `gpt-transcribe` for recognition and `gpt-6-luna` for interpretation/replies. Wake detection and Piper speech run locally. Command audio and conversation context go to OpenAI; web search returns clickable sources. Audio is not saved. The latest **500 text exchanges** persist privately; the latest six conversation exchanges provide context. Only the localhost owner can **Clear history**, which also stops Jarvis.

**Alerts on / Alerts off** controls hardware warnings: CPU/RAM **90% or above**, or GPU temperature **70°C or above**, across three fresh readings. Jarvis waits for idle wake listening and speaks through the dedicated speaker. All warnings share a **one-hour cooldown across restarts**. Alerts off cancels warning playback without turning Jarvis off.

Every screen, including Clock, Ambient and Rest, shows Jarvis activity during a request, processing, speech, follow-up and warnings. The idle wake-word badge appears only on Home; it stays hidden on all other screens. Widgets reserve a separate strip for active Jarvis, and other screens use a compact header overlay. Closing the webpage leaves Jarvis running. **Turn off Jarvis** releases its microphone and models. Windows lock pauses listening. A server restart always starts Jarvis **off**; turn it back on after updating/restarting.

See [JARVIS_SPEC.md](spec/JARVIS_SPEC.md) or **Setup & supported commands** on Jarvis for details.

## Update an existing installation

Use the existing folder and preserve `.state/` and `config/*.local.json`. Do not clone over the working installation. These steps assume the checkout is on **main**. Preserve any local edits or branch work before pulling.

```powershell
cd D:\TabletDashboard
git status --short --branch
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If the update changes your installed Jarvis dependencies, also run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

After backend/dependency changes:

```powershell
.\scripts\restart-server.ps1
```

For an installed Jarvis, this update adds the Jarvis wake model. Before restarting, run `.\.venv\Scripts\python.exe scripts/install-voice.py` to install its checksum-verified model and license. This preserves the saved key, voice preferences, history and device approvals.

For frontend/documentation-only updates, reload the browser without restarting the server. Reload both laptop/tablet pages after updating; re-enable Jarvis after a server restart. Normal updates preserve approvals, certificates, encrypted key, preferences, and conversation history.

## Stop, restart, change the port, or disable startup

Run in the project folder. Stop the background app until the next sign-in or manual start:

```powershell
Stop-ScheduledTask -TaskName 'G16 Command Center'
```

Start it again:

```powershell
Start-ScheduledTask -TaskName 'G16 Command Center'
```

Restart safely:

```powershell
.\scripts\restart-server.ps1
```

Change the background dashboard port, for example to **18762**:

```powershell
.\scripts\install-startup.ps1 -Port 18762
.\scripts\restart-server.ps1
```

Update bookmarks/firewall rules as needed using the refreshed connection file. Certificate setup stays on **18760**. Temporary runs need `-Port 18762` explicitly; their default stays 18761.

Stop the app and remove automatic startup:

```powershell
.\scripts\remove-startup.ps1
```

This keeps the project and private state. Do not move the folder while the startup task still points there.

## Troubleshooting

### ERR_EMPTY_RESPONSE on the tablet

Check the address: **port 18761 requires `https://`**. Old `http://192.168…:18761` bookmarks cause this error. Only certificate setup on 18760 uses HTTP.

### Certificate warning

Install **G16 Dashboard CA.cer** through Android Settings, verify its fingerprint for HTTP downloads, and use the current address from the laptop text file. Check device clocks. Do not replace the CA or delete `.state/` for a normal connection issue.

### Cannot reach the laptop

Keep the laptop awake and signed in, on the same Wi-Fi. Check the current Wi-Fi IP, Private-network firewall rule, and router guest/client isolation. A DHCP reservation can keep the laptop address stable.

Check the task:

```powershell
Get-ScheduledTask -TaskName 'G16 Command Center' | Select-Object TaskName, State
```

Open **https://localhost:18761/api/health** on the laptop (substitute your configured port). A running server returns `ok: true`; that alone does not mean the tablet is approved.

### No Approve button

Use the **approved owner browser at `https://localhost:18761/#devices`**. The Wi-Fi IP does not grant owner access. Finish laptop setup if it shows the access form. Match the pending tablet name/fingerprint. Expired requests need a new request from the tablet.

### Jarvis cannot hear me or is silent

Check the selected **PC microphone** and **Jarvis speaker**, not only Windows' defaults. Turn Jarvis off, reconnect/refresh devices, select them, preview the voice, and enable it. Check desktop microphone permissions. A saved key does not confirm API billing, internet access, or access to the configured models.

### App/game fails to open

Confirm it is installed. YouTube requires Brave. Use **Games → Refresh** for new games. Add supported desktop apps using **More → System & controls → App shortcuts** on Windows. Initial trusted app overrides go in ignored `config/apps.local.json`; once saved in settings, the private shortcut list takes precedence. Game overrides use `config/games.local.json`. Initial app overrides require a server restart. Formats are in [README.md](README.md#configure-applications).

### Where are logs and data?

- `.state/private/server.log` and rotated backups: operational logs, roughly 6 MB total across three files.
- `.state/private/devices.sqlite3`: browser approvals and hashed credentials.
- `.state/private/voice/history.sqlite3`: the latest 500 Jarvis text exchanges.
- `.state/private/voice/`: encrypted key, audio/preferences, alert cooldown, downloaded models.
- `.state/private/tls/`: HTTPS certificates and protected private keys.

Graph history stays **in memory for up to one hour** and resets on restart. It is not stored in the device database. Audio is not saved. Keep private state out of Git/shared folders; encrypted keys belong to this Windows account and are not a portable setup package for another laptop.

See [SECURITY.md](SECURITY.md) for trust boundaries and [VALIDATION.md](VALIDATION.md) for checks actually performed.

## Now playing, focus and automatic display

After updating dependencies and restarting through `scripts/restart-server.ps1`, reload the tablet once. Existing approvals and certificates remain valid.

**More → Now playing** follows the Windows-selected player. Start Spotify on the laptop or play a YouTube video in Brave. Artwork, title, artist and available album information update automatically. Previous/play/pause/next affect that session; unsupported buttons are disabled. Progress and seeking appear only when the player reports a valid duration and seek support. Laptop volume down/mute/up are also available; holding down/up repeats the existing Windows volume steps. These buttons do not claim an absolute volume or mute state.

Artwork keeps its original proportions and uses a local backdrop. The dashboard serves the image supplied by Windows without a remote artwork lookup. Some Brave YouTube sessions provide only a 150 × 83 thumbnail and no duration: a better page layout cannot recover missing image detail, and the seek bar stays hidden. This is a player limitation. Spotify should expose its own session while playing; a background Spotify window alone does not select it. If details remain unavailable, verify the player appears in Windows media controls and reload after the backend update.

**Clock → Focus timer**, or the Home shortcut, opens the large laptop-owned countdown. Start, pause/resume, skip and reset it from any approved browser. Defaults are 25-minute focus, 5-minute short break and 15-minute long break after four completed focus phases. Each phase waits for you to start the next. Reloading preserves the timer; overdue recovery after a server restart is silent. A system-clock change pauses for review. Durations and optional completion speech are under **More → System & controls → Tablet settings → Focus timer**. Pause before changing durations. Announcements require Jarvis already enabled, idle and the laptop unlocked; they never turn listening on or use a cloud request.

## Rest mode and alarm

Open **More → Rest & alarms**, **Clock → Rest & alarms**, or `/#rest`. Keep the laptop plugged in and signed in, with the dashboard server running. Rest turns supported **external desk monitors** off through DDC/CI while keeping Windows and the server awake. Enable DDC/CI in each monitor's own menu if needed. Unsupported monitors show an error; the dashboard never falls back to Windows system sleep. Windows Sleep, lid-close sleep policy and low-battery shutdown still take precedence. For an already-closed lid, keep the existing desk configuration that lets Windows run with the lid closed.

1. Choose **Set alarm**, select the date/time and complete **It's time to…**, for example `wake up` or `join your meeting`. Time uses this device's timezone. One shared alarm is kept on the laptop; saving replaces the previous alarm and prevents ordinary idle sleep while armed.
2. Choose **Jarvis spoken announcement** if the optional voice is installed. It uses the selected Jarvis speaker and says “Sir, it's time to wake up,” preceded by a chime. **Test Jarvis alarm** previews a fixed phrase for up to ten seconds. Neither needs an API key or internet, opens a microphone or enables listening. Preview and alarm firing stop conversational Jarvis to avoid overlapping audio; turn listening back on explicitly afterward. Rest entry keeps an already-enabled Jarvis session running.
3. Tap **Enter Rest mode** and accept the confirmation. **Checking desk monitors through your dock…** may take several seconds; this step is read-only, and the off command follows only after it succeeds. The tablet shows a dim clock and next alarm; backgrounds and screen rotation pause. **Brighten controls** brightens the page for 15 seconds. Android hardware brightness is unchanged, and browser **Screen awake** can keep the tablet display on.
4. Use **Wake PC displays** to exit early. At the alarm time, the laptop requests monitor On and visible connected dashboards show **Snooze 5 min** / **Dismiss**. Voice can play with Windows locked and conversational Jarvis off. It repeats every 30 seconds and stops after ten minutes. **Cancel alarm** removes an armed alarm; snoozing does not automatically re-enter Rest.

First try a two-minute alarm while at the desk. Confirm the monitors go off, the tablet remains connected with the lid closed, the alarm sounds and the monitors return. If a monitor cannot be restored through DDC/CI, use its power button. A process crash or cable change can lose its temporary handle. Manual Windows sleep prevents the laptop server/alarm from running; this feature cannot wake an actually sleeping system remotely.

With **Jarvis on** and Windows unlocked, say **“Jarvis, enter rest mode.”** Jarvis first says “I'll enter Rest mode, sir,” checks the monitors and enters the same shared Rest mode. It keeps its models loaded and resumes wake listening, including after button entry. Say **“Jarvis, wake up”** to restore the monitors and the tablet's previous page; Jarvis then says “Displays awake, sir” and continues listening. Both commands preserve your alarm. Say **Jarvis**, pause briefly, then say the command. The dedicated local Jarvis model also recognizes the older Hey Jarvis phrase. Optional “please,” wake-phrase punctuation and a trailing “Jarvis” are accepted in recognized command text. Failed requests explain why in **Jarvis → History**. Off, Windows lock, worker replacement or expiry cancel pending actions. Windows lock pauses listening; voice wake does not unlock Windows or resume an actually sleeping laptop. A server restart leaves Jarvis off until you enable it again. Normal command transcription still needs your configured API key and internet.

Reloads retain the laptop alarm; future alarms also survive server restarts. Overdue/ringing recovery is silent and shows **Missed**. Clock changes show **Paused** for review. Review and save a new time after either state. The private file is `.state/private/alarms.json`; normal updates preserve it. See [REST_ALARM_SPEC.md](spec/REST_ALARM_SPEC.md) for detailed behavior.

If Rest shows **Not found**, the browser loaded new static files against an older backend: update the checkout, run `scripts/restart-server.ps1`, and reload. This feature includes backend changes and needs that restart; static-only edits do not.

**Tablet settings → Display behavior** holds independent, initially off switches for night dimming, slow screen rotation, playing-media switching and recognized-game switching. Default night hours are 22:00–07:00 in this viewing device's timezone; dimming affects page artwork/readings, while Android retains hardware-brightness control. Brighten temporarily lasts 15 minutes. Rotation defaults to Home/Clock/Ambient every 120 seconds; choose at least two screens. Touch holds your view for two minutes, and More/settings/dialogs, immersive view, a running/paused Focus view, a hidden tab or stale connection suppress navigation. Games take priority over background music. **Stay on this screen** pins the view until **Resume automatic display**. Settings are remembered per browser.

## Optional extra thermal readings

Extra sensors are off by default. HWiNFO is not installed by the dashboard. If you choose it, open its Sensors window on the laptop and enable Shared Memory Support. Non-Pro 64-bit shared memory stops after 12 hours and needs manual enabling again; [HWiNFO's license matrix](https://www.hwinfo.com/licenses/) documents the limit.

In the approved owner browser at **https://localhost:18761**, open **More → Hardware → Extra sensor setup**. Turn extra sensors on, refresh the sensor list, and compare labels/current values against HWiNFO. Select the actual CPU package temperature, fan RPM entries, individual physical SSD temperature entries, and explicit CPU/GPU thermal-throttling flags. Save the mapping. Do not map a core temperature as CPU package or a power-limit flag as thermal throttling. Separate drive readings remain separate from partition usage. Mapping is laptop-private and uses stable sensor/reading identities.

Missing, unmapped, stopped, expired or incompatible readings show Unavailable and stale values clear within five seconds. Fan control and thermal intervention are not implemented. This Dell's CPU/fan/SSD/throttle readings remain unverified until compared with a running provider; working NVIDIA readings continue independently.


## Optional widgets

After updating, use `scripts/restart-server.ps1` for the new backend endpoints and reload the tablet. Existing approvals and CA trust remain valid. Jarvis listening starts off after a backend restart; enable it again if wanted.

Open **More → System & controls → Tablet settings → Optional widgets**. All widget switches start off in a new browser.

- Check **Extra clock faces**, choose **Minimal**, **Analog** or **Moon phase**, then **Save optional widgets**. Open **Clock**; its **Clock face** selector switches among enabled faces and Flip. These faces work offline. Moon phase and illumination are approximate cycle calculations. Turning extras off restores Flip. Focus and Rest remain accessible.
- For **Weather & air quality**, type a city in **Find a city**, tap **Find city**, select a matching result, check the Weather switch and save. Search sends the city query to Open-Meteo through the PC; viewing Weather sends the selected rounded city coordinates. It does not request GPS location. **More → Widgets → Weather & air** shows Celsius, wind in km/h, three forecast days, sunrise/sunset and modelled US AQI/PM values. AQI comes from CAMS models, not a local sensor. Open-Meteo's free service is for personal non-commercial use; source credits stay visible.
- Check **F1 next race** and save. Open **More → Widgets → Next race** for the next scheduled race this season, optional qualifying and a countdown to the provider's start time. Displayed start times use your browser's timezone. Live laps/results/timing are unavailable.

Choices and the city are remembered separately on each browser. **More → Widgets** appears only with an online widget enabled. Switching off both removes it; disabling one removes that tab. Add **Widgets** to **Display behavior → Slow screen rotation** along with another screen to rotate to your last-selected widget. Rotation stays opt-in and skips Widgets when both switches are off.

Online feeds require PC internet access. Unavailable fields show an em dash. A failed update may retain labelled cached data for a bounded period before becoming unavailable; source/update times remain visible. The PC shares a bounded memory cache; there are no browser-to-provider requests, API key fields or saved feed history. Leaving/hiding Widgets or entering Rest stops its browser polling. Immersive view and screen keep-awake reuse the existing controls. Widget readings scroll inside the screen when space is tight; the tabs, immersive exit and screen controls stay visible. Normal view leaves room for the dock; immersive view uses the full display. Active Jarvis occupies its own strip above the readings.

This release adds clock faces, Weather/AQI and F1 only. Sports scores, flights, transit, commute and restaurants are not yet implemented. See [WIDGETS_SPEC.md](spec/WIDGETS_SPEC.md) and [VALIDATION.md](VALIDATION.md) for limits and verified behavior.
