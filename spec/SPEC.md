# Jarvis Command Center — implementation specification

Version 0.3 • 2026-10-03 • Windows PC/laptop host + tablet browser surface; Dell G16/Redmi physically validated

## Product contract

The tablet is an independent browser control surface connected to a Windows PC or laptop over a private LAN. The PC collects telemetry, launches configured apps, and performs supported controls. No desktop streaming, display extension, cloud server, or Corsair branding is involved. The interface feels like a dedicated desk display: screen-level compositions, bold typography, large live readings, a floating dock, full-screen clock/artwork, and a poster gallery. A permanent sidebar, overview card grid, and repeated status strips are absent.

Primary layout is landscape, with a responsive portrait layout. Support current Chromium-based Android browsers and Windows Edge/Chrome. Design around flexible viewport dimensions rather than assuming the tablet's panel resolution equals its CSS viewport.

## First build: delivered scope

- FastAPI serves local HTML/CSS/JavaScript assets and authenticated REST + WebSocket APIs.
- One shared sampler collects CPU utilization/per-core load/reported clock, RAM, disk capacity/read/write, aggregate network throughput/adapters/IPs, battery/AC status, hostname, OS, and uptime.
- NVIDIA temperature, utilization, clock, memory, and power are read with a fixed `nvidia-smi` query if available. Other GPU vendors are reported unavailable until adapters are added.
- Overview, Gaming, Game library, Hardware, Live graphs, Applications, Clock, Ambient, System, and Device access pages share a single connection and sampler. Gaming emphasizes live utilization; FPS remains unavailable pending RTSS. Device access provides a dedicated approval/revocation list, also available on System.
- Custom geometric G16 emblem, consistent glyphs, dark open compositions, ivory/sage typography, locally served app logos, and a floating touch dock. Home, Performance, Games, Apps, Clock, and Ambient are primary screens; Hardware, Live graphs, System, and Device access are in More. Brave and a fixed YouTube-in-Brave shortcut join the app defaults.
- Clock offers split-flap local time, date/timezone, 12/24-hour format and immersive view. Screen keep-awake is enabled by default across all approved pages, with a remembered opt-out. Ambient offers three original local silent WebM loops plus NASA's edge-on Black hole MP4, pause/resume, reduced-motion support, and remembered visual preferences.
- Game library discovers installed Steam/Epic/GOG/Riot titles from launcher records, with filtering/search/refresh and ID-only launch dispatch. Local Steam artwork requires approved browser access. Portable/unsupported titles can use ignored laptop-side registrations. Running-game state remains future work.
- Registered apps launch by ID; running state matches configured process names. Default URI registrations depend on an installed Windows handler, so launch may fail with a visible error.
- Windows media keys support play/pause, previous/next, mute, and volume steps. Delivery is acknowledged; actual playback state and numerical system volume are not inferred.
- Graph ranges: 30 seconds, 1 minute, 5 minutes, 15 minutes, 1 hour. History is in-memory and starts when the server starts. No fabricated prehistory.
- Pairing, session expiry, same-origin controls, reconnection, stale indicators, fullscreen, automatic screen wake lock, swipe navigation, and touch-responsive layouts.
- Optional silent startup at Windows user sign-in on dedicated port 18761, with current connection instructions exported to Desktop and Downloads and refreshed after network changes.
- HTTPS, laptop-approved browsers remembered for 180 days across restarts, revocation, a persistent local device registry, and a setup-only public certificate download on port 18760. See ../SECURITY.md for enrollment and trust boundaries.

## Information architecture and future acceptance criteria

### Personal assistant foundation

More includes **Connections**, **Personalization**, and **Today**. The approved HTTPS direct-loopback owner can import a Google Desktop OAuth client, explicitly enable account access separately from the microphone, connect a verified account and request a bounded primary-calendar agenda for the saved timezone. Credentials are DPAPI-protected; agenda payloads remain transient and outside the shared telemetry/voice history. All agent harness code and persona assets are under `backend/agent/`. See [setup and implementation boundaries](ASSISTANT_FOUNDATION.md) and [the broader plan](PERSONAL_ASSISTANT_PLAN.md). Calendar writes, other service adapters, memory facts, delegated agents and scheduled responsibilities remain future work.

The target comprises 12 feature pages. Seven feature pages plus Clock, Ambient, and Device access are implemented (ten tabs). Remaining feature pages will appear when their integrations work.

1. **Overview:** CPU/GPU/RAM overview, short graphs, resource capacity, quick launch, media keys. Later add temperatures, fan speeds, SSD temperature, and FPS when their sources are connected.
2. **Gaming:** GPU and CPU clocks/power/temperatures/load, RAM/VRAM, FPS/frame time/1% lows. RTSS data must be associated with the active process; unsupported games show unavailable.
3. **Hardware:** per-core CPU readings, effective clocks, power/limits/throttling, GPU hotspot/controllers/limits/fans, RAM capacity/cache/speed, each drive's temperature/health/capacity/activity. Every sensor shows its source and timestamp.
4. **Live graphs:** selectable range and metrics, bounded payloads, gaps for missing samples. Long ranges aggregate server-side. Initial history lasts one hour in RAM; durable storage is optional later.
5. **Apps:** categories, names, icons, installation/launch errors, process state. Initial configuration is laptop-side JSON. The approved Windows owner can add detected desktop or packaged app IDs or remove shortcuts in System settings, with a 25-app total limit and private atomic persistence. The picker never accepts browser-supplied paths or arguments.
6. **Games:** trusted executable/launcher/Steam App ID registrations, arguments, artwork, running state. Never accept executable paths from the tablet launch request.
7. **Media:** Windows Global System Media Transport Controls for title/artist/artwork/playback/seek. Spotify-specific integration only if system media APIs do not meet needs. No Spotify cloud account required for basic keys.
8. **OBS:** local OBS WebSocket authentication, scenes/sources/audio, recording/stream state/duration/bitrate/drops. Store OBS secret only on the laptop. Show disconnected states and require confirmation before starting a stream.
9. **System:** audio, microphone, supported brightness, Wi-Fi/Bluetooth state, battery/AC, lock/sleep/restart/shutdown. Destructive controls require an explicit confirmation and short-lived server-issued action nonce. Power actions are absent from the first build.
10. **Network:** active adapter, SSID/signal when obtainable, LAN addresses, throughput history. Measured throughput is not advertised link speed or an internet speed test. Ping/packet loss targets must be explicit and bounded.
11. **Laptop:** battery health where accessible, AC/power mode, thermals/fans, display resolution/refresh, uptime/Windows version. Dell thermal controls require a documented supported interface; no speculative firmware writes.
12. **Macros:** laptop-defined named sequences of registered actions with visible progress, cancellation and bounded execution. Reuse app/media/OBS adapters; reject unknown actions. No general-purpose shell or scripting endpoint.

## Architecture

`Redmi browser → same-origin HTTPS/WSS → FastAPI → telemetry/control adapters → Windows`

- Backend: Python 3.14, FastAPI, Uvicorn, psutil. A thread collects potentially blocking sensor readings so HTTP/WebSocket handlers remain responsive.
- Frontend: dependency-free modules in plain JavaScript and CSS; all assets are served by the laptop. A frontend framework can be introduced if custom widget composition warrants it.
- Configuration: `config/apps.json` defaults; ignored `config/apps.local.json` override for machine-specific app paths. Games are discovered from local launcher metadata with optional ignored `config/games.local.json` additions. Macros/settings will follow the same local override pattern.
- Auth state: random startup recovery code in console and ignored `.state/private/pairing-code.txt`; approved device credentials are stored only as hashes in `.state/private/devices.sqlite3`. Secure HttpOnly cookies authenticate approved browsers for up to 180 days, surviving server restart. Recovery codes change on restart. Remote code possession alone never grants approval; device management requires an owner credential and a direct loopback connection.
- Sample schema: UTC ISO timestamp, source, CPU, optional GPU, memory, drives/disk rates, network, optional battery, system, integration status. Missing values are `null`; the UI shows an em dash or unavailable label.
- Initial sample/push interval: approximately 1 second. NVIDIA query every 2 seconds; app process refresh every 15 seconds. Sample overhead may extend the interval. Next stage separates fast 500 ms load readings, medium 1 s metrics, and slow 5–10 s static metadata.
- Single sampler per process. Start Uvicorn with one worker. Per-client WebSocket sends the newest shared snapshot; it never spawns a hardware sampler.
- History: up to 3,600 snapshots; `/api/history` selects by timestamp and downsamples to at most 241 returned snapshots while retaining the newest. Each contains UTC timestamps for correct spacing. Server restart clears history.

## API contract

- `GET /api/health`: public availability/version only.
- `GET /api/auth`: this browser's approval state and whether local device management is available.
- `POST /api/pair`: `{code,name?}`; localhost setup creates an approved owner browser; remote requests create only pending enrollment. Five attempts per address per minute.
- `POST /api/device/request`: `{name}`; no-code enrollment request, blocked from telemetry/controls until approved. Pending cookie/request expires in ten minutes.
- `POST /api/device/activate`: finish an approved request and remember this browser with a persistent cookie.
- `GET /api/devices`, `POST /api/devices/{id}/approve`, `POST /api/devices/{id}/revoke`: direct-loopback owner browser only. Revocation also closes the live WebSocket.
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
4. Tablet installs the public CA certificate once, requests browser approval, and the laptop owner matches its fingerprint before approving. Subsequent REST/WebSocket connections authenticate with the remembered browser cookie.
5. UI shows live connection only after receiving a current sample. Disconnection marks readings stale immediately; an open socket without recent samples is marked stale after five seconds.
6. Reconnection uses exponential backoff with jitter up to approximately ten seconds. Android foregrounding retries a closed connection. Session rejection reopens pairing.

Use trusted-local-network firewall access only. No automatic firewall changes, router forwarding, or remote internet exposure. An optional user-installed scheduled task starts the server silently at Windows sign-in via `scripts/install-startup.ps1`; it uses the interactive user account, runs on battery, ignores duplicate instances, and retries failures. Dashboard controls use HTTPS; remote plaintext requests are rejected. A separate HTTP listener on port 18760 serves only the public certificate and setup instructions. Users must verify a downloaded certificate's fingerprint against the trusted laptop connection file, or transfer it via USB. Fullscreen requires a touch gesture; automatic tablet wake/kiosk behavior depends on Android/browser settings and is not guaranteed by a website.

## UI constraints

- Landscape-first screen compositions sized against the visible browser width and height. Reserve shared space for the floating dock and device safe areas; keep primary actions clear of navigation with browser chrome visible or in fullscreen. Portrait centers the main reading and uses two shortcut rows.
- Approved browsers report their own display size, visible area, orientation, scale and fullscreen state on connection, resizing and a 30-second visible-page heartbeat. Keep only the latest bounded report in memory for five minutes, show it to the direct-loopback owner in Device access, and offer a local display readout/copy button under Tablet settings. These reports describe the browser viewport, not hardware identity or advertised panel resolution.
- Primary touch controls at least 48 CSS px; graph range controls have a 48 px height and at least 44 px width.
- Use system fonts, high-contrast text, lime primary accent, cyan/purple/orange sensor colors, tabular numeric readings.
- Navigation supports taps and deliberate horizontal swipes outside controls. No hover-only features.
- Do not re-create primary control DOM for every telemetry tick; preserve touch interactions and focus.
- Missing telemetry never creates plausible fake values. Raw sensor source and disconnected integration state remain accessible.
- Fullscreen and keep-awake failures display an explanation. Respect reduced-motion preferences.
- Request screen wake lock automatically after approval and on reload, regardless of the selected page. Require a visible approved page and trusted HTTPS; release on hiding, page exit or unpairing. Reacquire after visibility/focus/fullscreen/page restoration and unexpected browser releases, with retries backing off from 2 to 30 seconds. Deduplicate pending requests and release stale results so hiding, disabling or unpairing cannot resurrect a lock. Tablet settings reports actual active/off/paused/blocked/unsupported status and offers retry; persist explicit opt-out in this browser. Keep-awake cannot override browser or OS restrictions.
- Clock uses two split-flap panels for hours/minutes, synchronizes both halves after each change, and shows immediate updates on initial load, returning from a hidden page, or with reduced motion enabled. Original static atmospheric artwork provides the page backdrop fallback. Event horizon, Neon drift and Aurora are original rendered video loops so particle rendering does not run on the tablet. Black hole uses an unmodified, credited NASA local video. Scene switching preserves pause, uses a scene-specific still poster, and ignores superseded playback attempts.
- One shared fixed, non-interactive video backdrop serves all ordinary pages and the clock, with dark overlays for readability. Match scenes to pages by default and offer a browser-local scene override and pause button in Tablet settings. Respect reduced motion and pause while hidden or unapproved. Hide/pause the backdrop on Ambient so only its dedicated movie plays. Reuse the included movies and still posters; no additional streaming or tablet particle renderer is required.
- Home composition: keep NASA's Black hole regardless of the scene override for other pages; the global background pause still applies. Leave the center open for the movie, place a smaller introductory heading at upper left and the Games shortcut at upper right, then a single unboxed CPU/vitals/media strip and launcher row above the dock. Replace the processor circle with a 42–58px reading, small percent sign and slim live trace. Reflow groups on narrower screens, preserve 100% value fit, and retain honest unavailable readings. Display NASA's individual source credit beside the artwork.
- Home provides previous/play-pause/next and volume-down/mute/volume-up controls via the existing registered Windows media IDs. Keep all six controls visible with at least 44px touch targets; wrap their groups on narrow screens. The volume buttons send key actions rather than claiming a current absolute volume or mute state.

## Milestones

The next owner-selected increments are detailed in [EXPERIENCE_PLAN.md](EXPERIENCE_PLAN.md): Now playing, Focus, display automation and deeper sensors. That document preserves the original acceptance criteria. Media, timer and display behavior are now implemented together; the optional sensor adapter still needs owner setup and comparison with this Dell's actual HWiNFO readings.

**M1 — Foundation (this build):** local server, pairing, real psutil/NVIDIA data, touch UI, graphs/reconnection, registered launcher, basic media keys, tests, repository/CI.

**M2 — Sensors:** inspect this Dell's exact sensor sources; implement HWiNFO shared-memory adapter behind a capability check. Confirm current HWiNFO licensing and shared-memory availability before selection. Add sensor ID mapping, timestamps, thermal limits, drives/fans. Integrate RTSS without inventing unsupported global FPS.

**M3 — Library and media:** games config, robust app discovery, laptop-side configuration editor, system media sessions and actual volume/microphone feedback.

**M4 — Windows and OBS:** explicit confirmations/nonces for power actions; local OBS integration and recording/streaming state. Errors remain isolated per adapter.

**M5 — Macros and personalization:** registered action sequences, widget/page layout persistence, theme controls, portrait polish, durable history/export if needed.

**M6 — Dedicated tablet operation:** stable local hostname/passkey evaluation, startup lifecycle polish and Android kiosk guidance. Local HTTPS and revocable remembered-browser access are already implemented. Measure performance on the actual Redmi Pad Pro.

## Verification and release gates

- Tests exercise pairing/rate limits/session expiry, unauthenticated REST/WS rejection, cross-origin control/WS rejection, unregistered executable denial, extra-field denial, shell-free launch dispatch, sanitized catalog, bounded history, sensor failures and missing values.
- JavaScript syntax check plus browser visual/functional inspection at landscape and portrait sizes.
- Manually pair the physical Redmi tablet on Wi-Fi, launch one installed app and confirm host behavior, test volume/playback, suspend/reopen browser, and interrupt/reconnect Wi-Fi before declaring tablet validation complete.
- Verify NVIDIA values against local NVIDIA tools and later HWiNFO sensor labels against HWiNFO itself.
- Do not test real sleep/restart/shutdown during automated checks.

## Open choices to resolve during later milestones

Exact Dell G16 CPU/GPU/model and sensor access; installed HWiNFO/RTSS/OBS versions and permissions; preferred Android browser and kiosk approach; trusted app/game paths; desired macros; local HTTPS name/certificate strategy; whether long-term history is useful. These do not block the foundation.

Technical references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/), [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/), [psutil](https://psutil.io/).

## Delivered desk experience

Optional native widgets add a fourteenth page without changing the primary dock. More → System & controls → Tablet settings holds opt-in extra clock faces, Weather/AQI and F1, all off by default. Clock retains Flip and adds original Minimal, Analog and approximate Moon phase faces. More → Widgets opens one enabled online composition at a time. Fixed-provider reads and caches run on the PC; the tablet still requests only same-origin assets/data. See [WIDGETS_SPEC.md](WIDGETS_SPEC.md) for scope, provider limits, privacy and verification.

Now playing is a screen-level composition with original-aspect artwork, artwork haze, player identity, large title/artist, supported session controls, optional timeline/seek, laptop volume keys, screen pin and immersive view. A shared Windows monitor emits bounded text, current-only validated artwork, capability flags and a clamped timeline. Native metadata may lack a useful timeline or offer a tiny thumbnail; the dashboard does not fabricate either. Seek/transport revalidate the selected session and track before dispatch.

Focus is a mode on Clock, owned/persisted by the laptop with monotonic live timing, wall-clock restart recovery, revision conflicts and exactly-once completion. Defaults are 25/5/15 minutes, a long break after four completed focuses, manual phase starts and no speech. Optional idle local Jarvis announcements are cancellable and excluded from conversation history.

Display behavior is browser-local and opt-in: scheduled night scene dimming, 30–600-second rotation (default 120), a two-minute manual hold, explicit pin and stable media/game transitions. Settings, dialogs, touch/seek/commands, presentation, active Focus view, visibility and freshness gate automatic navigation. Foreground executable matching uses trusted game installations/exact registrations, rejects helpers and ambiguity, and never infers gaming from load or launch.

Hardware supports an optional bounded HWiNFO SM2 read-only adapter, owner mapping by stable reading IDs, recognized units, freshness and explicit throttling flags. CPU/fan/physical-drive readings remain null until mapped against a verified provider inventory. HWiNFO installation, licensing and this Dell's native sensor comparison remain owner setup; FPS and hardware control remain outside this update.

Rest & alarms adds a thirteenth implemented page, linked from More and Clock. Confirmed Rest entry powers supported external monitors off through fixed DDC/CI commands while Windows display/system/process requests keep the server awake. Approved browsers show a dim clock with the shared next alarm, and restore their previous pages on exit. One persisted laptop-owned alarm supports optional microphone-free local Jarvis speech, five-minute snooze, dismissal, silent missed recovery and clock-change pause. Windows system Sleep is not requested or remotely recoverable. See [REST_ALARM_SPEC.md](REST_ALARM_SPEC.md) for safeguards and monitor compatibility limits.
