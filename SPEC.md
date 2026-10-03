# G16 Command Center — implementation specification

Version 0.1 • 2026-10-03 • Dell G16 host + Redmi Pad Pro touch surface

## Product contract

The tablet is an independent browser control surface connected to the laptop over a private LAN. The laptop collects telemetry, launches configured apps, and performs supported controls. No desktop streaming, display extension, cloud server, or Corsair branding is involved. The experience takes inspiration from compact touchscreen hardware dashboards: dark modular panels, readable metrics, thin borders, sparklines, and large controls.

Primary layout is landscape, with a responsive portrait layout. Support current Chromium-based Android browsers and Windows Edge/Chrome. Design around flexible viewport dimensions rather than assuming the tablet's panel resolution equals its CSS viewport.

## First build: delivered scope

- FastAPI serves local HTML/CSS/JavaScript assets and authenticated REST + WebSocket APIs.
- One shared sampler collects CPU utilization/per-core load/reported clock, RAM, disk capacity/read/write, aggregate network throughput/adapters/IPs, battery/AC status, hostname, OS, and uptime.
- NVIDIA temperature, utilization, clock, memory, and power are read with a fixed `nvidia-smi` query if available. Other GPU vendors are reported unavailable until adapters are added.
- Overview, Gaming, Hardware, Live graphs, Applications, and System pages share a single connection and sampler. Gaming emphasizes live utilization; FPS remains unavailable pending RTSS.
- Registered apps launch by ID; running state matches configured process names. Default URI registrations depend on an installed Windows handler, so launch may fail with a visible error.
- Windows media keys support play/pause, previous/next, mute, and volume steps. Delivery is acknowledged; actual playback state and numerical system volume are not inferred.
- Graph ranges: 30 seconds, 1 minute, 5 minutes, 15 minutes, 1 hour. History is in-memory and starts when the server starts. No fabricated prehistory.
- Pairing, session expiry, same-origin controls, reconnection, stale indicators, fullscreen, optional screen wake lock, swipe navigation, and touch-responsive layouts.
- Optional silent startup at Windows user sign-in on dedicated port 18761, with current connection instructions exported to Desktop and Downloads and refreshed after network changes.

## Information architecture and future acceptance criteria

The target comprises 12 pages. The six initial pages are implemented; remaining pages will appear when their integrations work.

1. **Overview:** CPU/GPU/RAM overview, short graphs, resource capacity, quick launch, media keys. Later add temperatures, fan speeds, SSD temperature, and FPS when their sources are connected.
2. **Gaming:** GPU and CPU clocks/power/temperatures/load, RAM/VRAM, FPS/frame time/1% lows. RTSS data must be associated with the active process; unsupported games show unavailable.
3. **Hardware:** per-core CPU readings, effective clocks, power/limits/throttling, GPU hotspot/controllers/limits/fans, RAM capacity/cache/speed, each drive's temperature/health/capacity/activity. Every sensor shows its source and timestamp.
4. **Live graphs:** selectable range and metrics, bounded payloads, gaps for missing samples. Long ranges aggregate server-side. Initial history lasts one hour in RAM; durable storage is optional later.
5. **Apps:** categories, names, icons, installation/launch errors, process state. Initial configuration is laptop-side JSON. A later laptop-only editor validates executable paths and arguments before registration.
6. **Games:** trusted executable/launcher/Steam App ID registrations, arguments, artwork, running state. Never accept executable paths from the tablet launch request.
7. **Media:** Windows Global System Media Transport Controls for title/artist/artwork/playback/seek. Spotify-specific integration only if system media APIs do not meet needs. No Spotify cloud account required for basic keys.
8. **OBS:** local OBS WebSocket authentication, scenes/sources/audio, recording/stream state/duration/bitrate/drops. Store OBS secret only on the laptop. Show disconnected states and require confirmation before starting a stream.
9. **System:** audio, microphone, supported brightness, Wi-Fi/Bluetooth state, battery/AC, lock/sleep/restart/shutdown. Destructive controls require an explicit confirmation and short-lived server-issued action nonce. Power actions are absent from the first build.
10. **Network:** active adapter, SSID/signal when obtainable, LAN addresses, throughput history. Measured throughput is not advertised link speed or an internet speed test. Ping/packet loss targets must be explicit and bounded.
11. **Laptop:** battery health where accessible, AC/power mode, thermals/fans, display resolution/refresh, uptime/Windows version. Dell thermal controls require a documented supported interface; no speculative firmware writes.
12. **Macros:** laptop-defined named sequences of registered actions with visible progress, cancellation and bounded execution. Reuse app/media/OBS adapters; reject unknown actions. No general-purpose shell or scripting endpoint.

## Architecture

`Redmi browser → same-origin HTTP/WebSocket → FastAPI → telemetry/control adapters → Windows`

- Backend: Python 3.14, FastAPI, Uvicorn, psutil. A thread collects potentially blocking sensor readings so HTTP/WebSocket handlers remain responsive.
- Frontend: dependency-free modules in plain JavaScript and CSS; all assets are served by the laptop. A frontend framework can be introduced if custom widget composition warrants it.
- Configuration: `config/apps.json` defaults; ignored `config/apps.local.json` override for machine-specific app paths. Future games/macros/settings follow the same local override pattern.
- Auth state: random startup pairing code in console and ignored `.state/pairing-code.txt`; random server-side sessions with 12-hour expiry. Restart invalidates sessions and changes the pairing code.
- Sample schema: UTC ISO timestamp, source, CPU, optional GPU, memory, drives/disk rates, network, optional battery, system, integration status. Missing values are `null`; the UI shows an em dash or unavailable label.
- Initial sample/push interval: approximately 1 second. NVIDIA query every 2 seconds; app process refresh every 15 seconds. Sample overhead may extend the interval. Next stage separates fast 500 ms load readings, medium 1 s metrics, and slow 5–10 s static metadata.
- Single sampler per process. Start Uvicorn with one worker. Per-client WebSocket sends the newest shared snapshot; it never spawns a hardware sampler.
- History: up to 3,600 snapshots; `/api/history` selects by timestamp and downsamples to at most 241 returned snapshots while retaining the newest. Each contains UTC timestamps for correct spacing. Server restart clears history.

## API contract

- `GET /api/health`: public availability/version only.
- `POST /api/pair`: `{code}`; correct code sets HttpOnly, SameSite=Strict cookie. Five attempts per remote address per minute.
- `POST /api/logout`: revoke current session and delete cookie.
- `GET /api/system`: current authenticated snapshot; 503 until a valid sample exists.
- `GET /api/history?seconds=60`: authenticated history; seconds between 30 and 3,600.
- `GET /api/apps`: sanitized registrations with availability/running state; target executable and arguments are excluded.
- `POST /api/apps/launch`: `{id}` only. Unknown IDs fail; extra fields fail validation. Launch acknowledgement is not a guarantee the app remained running.
- `POST /api/media/{action}`: enumerated media key names only. Unknown names fail.
- `WS /ws`: authenticated same-origin session; `{type:'telemetry', data, errors}` every approximately 1 second. Session expiration closes with policy code 1008.

REST mutations require an Origin matching the request authority. No CORS wildcard, shell execution, unauthenticated LAN bypass, access tokens in URLs, or third-party frontend requests. API responses disable caching. Browser cookies use Secure on HTTPS and HttpOnly on all transports.

## Connection and operational behavior

1. Laptop starts server; terminal displays pairing code.
2. Tablet and laptop join the same private Wi-Fi.
3. Start with `scripts/start.ps1 -Lan`; use the laptop's Wi-Fi IPv4 URL on port 18761.
4. Tablet enters startup code; cookie authenticates subsequent REST and WebSocket requests.
5. UI shows live connection only after receiving a current sample. Disconnection marks readings stale immediately; an open socket without recent samples is marked stale after five seconds.
6. Reconnection uses exponential backoff with jitter up to approximately ten seconds. Android foregrounding retries a closed connection. Session rejection reopens pairing.

Use private-network firewall access only. No automatic firewall changes, router forwarding, or remote internet exposure. An optional user-installed scheduled task starts the server silently at Windows sign-in via `scripts/install-startup.ps1`; it uses the interactive user account, runs on battery, ignores duplicate instances, and retries failures. This is available in the foundation following the user's startup request. Plain HTTP is an initial trusted-LAN transport; anyone able to inspect traffic can observe pairing/session data. HTTPS is the later transport milestone and also enables browser screen wake lock. Fullscreen requires a touch gesture; automatic tablet wake/kiosk behavior depends on Android/browser settings and is not guaranteed by a website.

## UI constraints

- Landscape-first modular grid; collapse columns in portrait and use bottom navigation on narrow screens.
- Primary touch controls at least 48 CSS px; graph range controls have a 48 px height and at least 44 px width.
- Use system fonts, high-contrast text, lime primary accent, cyan/purple/orange sensor colors, tabular numeric readings.
- Navigation supports taps and deliberate horizontal swipes outside controls. No hover-only features.
- Do not re-create primary control DOM for every telemetry tick; preserve touch interactions and focus.
- Missing telemetry never creates plausible fake values. Raw sensor source and disconnected integration state remain accessible.
- Fullscreen and keep-awake failures display an explanation. Respect reduced-motion preferences.

## Milestones

**M1 — Foundation (this build):** local server, pairing, real psutil/NVIDIA data, touch UI, graphs/reconnection, registered launcher, basic media keys, tests, repository/CI.

**M2 — Sensors:** inspect this Dell's exact sensor sources; implement HWiNFO shared-memory adapter behind a capability check. Confirm current HWiNFO licensing and shared-memory availability before selection. Add sensor ID mapping, timestamps, thermal limits, drives/fans. Integrate RTSS without inventing unsupported global FPS.

**M3 — Library and media:** games config, robust app discovery, laptop-side configuration editor, system media sessions and actual volume/microphone feedback.

**M4 — Windows and OBS:** explicit confirmations/nonces for power actions; local OBS integration and recording/streaming state. Errors remain isolated per adapter.

**M5 — Macros and personalization:** registered action sequences, widget/page layout persistence, theme controls, portrait polish, durable history/export if needed.

**M6 — Dedicated tablet operation:** local HTTPS provisioning, revocable per-device sessions, startup lifecycle polish and Android kiosk guidance. Measure performance on the actual Redmi Pad Pro.

## Verification and release gates

- Tests exercise pairing/rate limits/session expiry, unauthenticated REST/WS rejection, cross-origin control/WS rejection, unregistered executable denial, extra-field denial, shell-free launch dispatch, sanitized catalog, bounded history, sensor failures and missing values.
- JavaScript syntax check plus browser visual/functional inspection at landscape and portrait sizes.
- Manually pair the physical Redmi tablet on Wi-Fi, launch one installed app and confirm host behavior, test volume/playback, suspend/reopen browser, and interrupt/reconnect Wi-Fi before declaring tablet validation complete.
- Verify NVIDIA values against local NVIDIA tools and later HWiNFO sensor labels against HWiNFO itself.
- Do not test real sleep/restart/shutdown during automated checks.

## Open choices to resolve during later milestones

Exact Dell G16 CPU/GPU/model and sensor access; installed HWiNFO/RTSS/OBS versions and permissions; preferred Android browser and kiosk approach; trusted app/game paths; desired macros; local HTTPS name/certificate strategy; whether long-term history is useful. These do not block the foundation.

Technical references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/), [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/), [psutil](https://psutil.io/).
