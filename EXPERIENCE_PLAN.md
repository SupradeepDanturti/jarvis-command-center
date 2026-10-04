# Desk experience feature plan

Status: proposed implementation plan; none of the features below are delivered by this document.

Prepared 2026-10-03 for the Dell G16 7630 and Redmi Pad Pro. The owner requested a detailed plan first. Implementation will follow in separate feature PRs, left for the owner's review.

## Outcome and build order

The tablet should show what matters at the desk: the current song, a focus countdown, the active game's performance, or a quiet clock/artwork display. Preserve one composition per screen, large readings, the floating dock, local assets, and configuration in More.

Build in this order:

1. **Now playing:** extend the working Windows media monitor with metadata, artwork and supported timeline controls.
2. **Focus timer:** add a laptop-owned timer visible on Clock, with optional local Jarvis announcements.
3. **Display automation:** add optional night dimming and slow rotation, then media/game context switching once reliable activity signals exist.
4. **Deeper sensors:** discover and verify this Dell's actual sensors, then expose only supported readings through an optional adapter.

Start sensor discovery early alongside the first phase; its dependency/setup decision must not hold up the other three features. This order is dependency-based, not a promised delivery date.

## Verified starting point

- The clean checkout starts from main at `38302af`. Documentation describes eleven existing screens, including Jarvis; some older portions of SPEC.md still describe the earlier ten-screen build.
- `backend/media.py` reads the Windows-selected media session twice per second. Playback status already reaches Home/System through `backend/main.py` and the existing authenticated WebSocket. Metadata, artwork, timeline and seeking are absent.
- `frontend/screens.js` provides the full-screen flip clock and ambient collection. `frontend/app.js` owns navigation, rendering, approval and connection state. Existing background/wake modules handle visibility and reduced motion.
- `backend/telemetry.py` deliberately returns null CPU temperature, CPU power, storage temperature and fans. NVIDIA temperature already comes from the fixed `nvidia-smi` query.
- Read-only Windows inventory identified **Dell G16 7630 / Intel Core i7-13650HX**. No HWiNFO/LibreHardwareMonitor/Open Hardware Monitor/Afterburner/RivaTuner installation appeared in the checked Windows uninstall records, and no HWiNFO/RTSS/Afterburner process appeared in the checked process list. Common HWiNFO install folders also yielded no installation. Portable installs elsewhere remain possible; CPU/fan/SSD sensor availability is unverified.
- Jarvis is optional, starts off, uses a separate worker and dedicated speaker, and already supports locally synthesized hardware warnings. Timer announcements need their own bounded event type and cancellation policy.
- These are code/documentation and read-only inventory findings. They do not verify physical tablet appearance, audio, seeking, game detection or new hardware sensors.

## 1. Now playing

### Screen and interaction

- Add **Now playing** under More and a compact title/artist shortcut beside Home's existing media controls. Keep the current six primary dock destinations so the dock remains readable.
- Landscape: large album artwork on one side, title/artist/player and playback controls on the other. Portrait: artwork above the controls. Use a local neutral artwork fallback.
- Show elapsed/total time and a seek slider only for a valid supported timeline. For a live stream or missing duration, show an honest live/unknown-duration state rather than a fabricated progress bar.
- Preserve Home/System media keys and held-volume behavior. The new screen uses session-specific play/pause/previous/next where Windows reports support; unsupported actions are disabled with an explanation.
- Refresh metadata when the track/session changes and resample state after commands. Paused players keep their last verified current track; an ended/disappearing session clears it. A missing title says "Track details unavailable" without borrowing another player's metadata.
- First release follows the Windows-selected session. A manual player picker, lyrics, Spotify account integration and system-volume slider are separate future scope.

### Implementation contract

- Extend `MediaMonitor` with async metadata/timeline sampling and bounded thumbnail reads. Keep the existing `status`, `available` and `sampledAt` fields compatible with Home/System.
- Add opaque `sessionId` and `trackRevision` identifiers, title/artist/album/player, position/start/end, playback rate, timeline update time, supported controls, and an authenticated artwork URL. Do not expose executable paths or remote thumbnail URLs.
- Publish a coherent snapshot: capture session/track revision before async reads and reject late results after a session or track change. A metadata failure must not stop the telemetry sampler or leave another track's artwork visible.
- Preserve the current half-second playback sampling. Cache unchanged metadata/artwork; do not copy image bytes into every WebSocket packet. Use a bounded retry/refresh interval so unsupported players cannot create a tight retry loop.
- Keep at most the current artwork in memory with a 2 MiB encoded-size cap. Accept validated PNG/JPEG/WebP raster data; reject oversized/unsupported content and use the fallback. Serve it through authenticated same-origin `/api/media/artwork/{revision}` with no-store caching. No browser-supplied path/URL, external fetching or permanent artwork archive.
- Add a strict authenticated, same-origin `POST /api/media/session-action` accepting only a current session/revision and an enumerated action. Add `POST /api/media/seek` accepting a current session/revision and finite seconds. Declare these before the existing `/api/media/{action}` route or replace that wildcard with explicit routes.
- Revalidate the current session, track, timeline and enabled control immediately before dispatch. Reject stale revisions and out-of-range/non-finite positions. Convert seconds to Windows' 100 ns position units at the adapter boundary. A false native result is a visible refusal, not success.
- A seek drag previews locally; commit once on release or keyboard commit. Preserve the slider DOM while dragging, permit one outstanding request, and cancel the interaction on navigation/disconnect/unpairing. Do not queue requests or retry physical actions automatically.
- Advance displayed progress from a fresh native position only while Playing, accounting for playback rate and timeline bounds. Freeze/clear it on stale connection; do not infer playback from sent keys. Treat all metadata as untrusted text.
- Verify the installed WinRT bindings for thumbnail streams/timestamps. Add pinned Windows-only stream dependencies only if required by the actual adapter; avoid a frontend framework or cloud dependency.

### Acceptance

- Correct title/artist/artwork for a supported player; missing artwork/title and multiple/disappearing sessions handled honestly.
- Playback changes made on the laptop reach the tablet; pause freezes progress; track change during metadata read/seek rejects the old result.
- Invalid/unsupported seek never dispatches; supported seek uses the correct session and position. Existing media key and hold checks continue passing.
- Unapproved, revoked and cross-origin clients cannot read private artwork/metadata or send commands. Oversized artwork and hostile title strings cannot break the page.
- Browser checks cover touch dragging, keyboard controls, all existing navigation, landscape/portrait and reconnect. Real player seeking and Redmi touch behavior require owner acceptance.

## 2. Focus timer and reminders

### Screen and interaction

- Clock offers **Clock / Focus** modes. Focus uses a large `MM:SS` countdown with a small local clock/date, a phase label, and Start/Pause/Resume/Reset/Skip controls. Preserve the immersive view and floating dock.
- Defaults: 25-minute focus, 5-minute short break, 15-minute long break after four completed focus sessions. Allow simple custom durations from 1 to 180 minutes in More.
- Each phase ends visibly and waits for an explicit start of the next phase by default. Optional automatic progression is off initially. Resetting an active session asks for confirmation.
- Show a small active-timer shortcut on Home. Starting a timer does not force navigation; **Show timer** opens Clock's Focus mode and pins that view while the session is active.
- Completion is always visual. Jarvis announcements are a separate opt-in, off by default. First release excludes calendar reminders, free-form scheduled messages and browser background alarms.

### State and lifecycle

- Own one shared timer on the laptop so approved laptop/tablet browsers agree. Store only current timer state/settings in ignored, ACL-protected `.state/private/focus.json`; do not save a work-session diary.
- Add `backend/focus.py` for validated state transitions, persistence and completion IDs. Add `frontend/focus.js` for rendering/controls. Use authenticated snapshot/command endpoints and the existing shared WebSocket; no sampler per browser.
- Commands are strictly enumerated and carry a state revision. Serialize transitions under a lock; simultaneous/stale browser commands return a conflict and refresh instead of double starting/skipping. Durations are bounded integers.
- Use a monotonic clock during a live process and a wall-clock deadline for recovery after restart. Return server time/deadline with snapshots; clients anchor remaining time locally so laptop/tablet clock skew cannot change the timer. Never decrement by counting browser ticks.
- Hiding/reloading/disconnecting a browser does not stop the timer. Reconcile at foreground/reconnect. After laptop suspend, account for elapsed time; if one phase expired, finish it once and wait for the next phase rather than replaying a sequence of missed breaks.
- On a backend restart, recover the current timer. If its deadline passed, show completion once. Detect contradictory/invalid saved times or major system-clock jumps and pause with a review message rather than inventing remaining time or firing duplicate announcements.
- Track a unique phase/completion ID and persist the terminal transition before announcing it. Browser redraws, reconnects and worker restarts cannot repeat the same completion. Prefer a missed announcement to duplicate speech after a crash.

### Optional Jarvis speech

- Send only a fixed local phrase such as "Your focus session is complete. Time for a short break." through a new timer-reminder event. No microphone recording, transcription, cloud request or new model tool is needed.
- Speak only when announcements are enabled, Jarvis is already running, Windows is unlocked, the worker generation is current and Jarvis is idle. Use the selected Jarvis speaker; never switch to headphones/default output on failure.
- Use a separate timer-reminder switch/event, independent of hardware alerts and their one-hour cooldown. Queue at most one reminder for at most 60 seconds; drop it if it cannot be delivered in that window. Never interrupt a conversation.
- Turning announcements off, resetting/replacing the timer, disabling Jarvis or locking Windows cancels pending/ongoing reminder audio. Jarvis stays off after server restart. Expired reminders are not replayed when Jarvis is later enabled or Windows unlocked.
- Keep timer reminders out of conversation history and model context. The existing bounded private conversation history retains its current semantics.

### Acceptance

- Start/pause/resume/reset/skip, phase order, custom bounds, duplicate commands and two-browser conflicts are deterministic.
- Remaining time survives reload/reconnect, hidden tabs, suspend and server restart; system-clock changes do not silently corrupt it. Only one completion event occurs.
- No voice dependency is needed for a visual timer. Tests prove reminder opt-in, idle-only dispatch, expiry, deduplication and cancellation on reset/lock/disable without microphone/audio side effects.
- Countdown layout and controls fit the physical tablet's reported 1280x800 viewport and existing nine-size touch matrix. Physical announcement timing/audibility remains an owner check.

## 3. Smarter display behavior

### Controls and defaults

- Add **Display behavior** in More -> System & controls -> Tablet settings. Night dimming, page rotation, switch-for-media and switch-for-games are four independent opt-ins; all start off.
- Save validated display preferences per browser alongside existing visual preferences, without credentials or private metadata. One tablet's choices must not change another browser's display.
- Suggested night preset: **22:00-07:00**, retaining approximately **35% of the normal dashboard brightness**. Use the viewing device's local time and handle midnight, daylight-saving/timezone changes and foreground return. Equal start/end times are invalid.
- Dimming changes rendered dashboard content, not Android hardware brightness. Darken artwork more than text, keep controls readable, and leave pairing/critical error dialogs readable. Provide **Brighten for 15 minutes** and an immediate off switch. Do not claim hardware brightness or waking a sleeping tablet.
- Suggested slow rotation: **Home -> Clock -> Ambient**, two minutes per screen. Allow an approved list of display pages and a bounded 30-second to 10-minute dwell. Never rotate into settings, Device access or Jarvis/history. Static/reduced-motion preferences still apply.
- Manual touch/keyboard/scroll/navigation holds the current page for two minutes. After that hold, start a full new dwell; never make a surprise immediate switch. **Stay on this screen** pins until explicitly unpinned. Immersive view is pinned until exited.

### Navigation arbitration

Centralize all navigation in one function/controller; today's swipe handler changes `state.page` directly and must join the same policy as dock taps, links, hash changes and automatic navigation.

Evaluate candidates in this order:

1. Approval/error dialogs, hidden/unpaired/stale state, open menus/forms, pointer drags/held controls, explicit pin/immersive view or current manual hold block automatic navigation.
2. Clock's explicitly selected active Focus view stays pinned until completion or manual navigation. A timer running in the background does not seize the screen.
3. A reliably recognized **foreground game**, stable for five seconds, selects **Live** when game switching is enabled.
4. A valid current media session that has been **Playing for five seconds**, with no higher-priority foreground game, selects **Now playing** when media switching is enabled.
5. Otherwise resume the selected slow rotation or return to the last manually selected display page if rotation is off.

- Enter automatic context once per activity transition rather than forcing its page on every sample. When context ends, wait ten stable seconds before returning. A manually selected page starts the full manual hold and prevents repeated stealing by unchanged activity.
- Do not treat a merely installed game, launched game, running Steam client, high GPU usage or paused media as active gaming/playback. Background music must not replace a foreground game's Live screen.
- Pause automation in More/details/settings even after the manual hold expires; explicitly return to a display page to resume. Reconnect/foreground resumes with a fresh dwell and stability window, never catches up on missed rotations.
- Show automation/pin status and controls in More, with a temporary notice on an automatic context change; do not add a permanent status bar. Switching automation off cancels pending decisions immediately.

### Activity signals and integration

- Add `frontend/display-behavior.js` with explicit input events, time-based decisions and injected clocks for testing. Extend existing approval/connection/visibility/navigation lifecycle hooks rather than starting independent page timers.
- Media activity comes from the fresh shared `MediaMonitor` snapshot. It can be implemented without any new game tooling.
- Game context needs a bounded read-only `backend/activity.py` adapter: periodically map the Windows foreground window's process to executable paths inside a trusted discovered game's installation directory or an exact laptop-defined executable registration. No window title capture, desktop screenshots, process command-line logging or arbitrary app launching.
- Reuse GameLibrary's trusted local records; never accept browser process IDs/paths. Reject launchers/helpers and ambiguous matches. Permission errors, anti-cheat processes, unavailable paths or unsupported games produce **Game detection unavailable** and no automatic switch. Use stable IDs; send only the matched game's sanitized name/ID and observation time.
- Sample foreground/process state approximately every two seconds in an isolated nonblocking task. Treat it as fresh for at most five seconds; do not tie auto-navigation to old telemetry or scan every game directory every tick.
- Keep dimming independent from navigation and the existing wake lock. Reduced motion, one-playing-background-video, Home's fixed black-hole scene and manual background pause remain intact.
- Implement media switching first, then enable the game option only when its adapter and actual title mapping pass acceptance. FPS/RTSS is outside this plan.

### Acceptance

- Test midnight schedules, boundaries, timezone/DST changes, brighten override, invalid stored preferences and persistence.
- Test dwell/manual hold/pins, simultaneous media+game priorities, startup with active playback, foreground game enter/exit, unsupported games and setting-off cancellation.
- No page switches during a slider drag, held volume button, dialog, More interaction, hidden tab, stale link or unpairing. All manual navigation routes behave consistently.
- Fake-clock browser checks verify lifecycle without waiting through real multi-minute schedules. Existing navigation/background/wake/volume/touch checks still pass. Physical Redmi readability, smoothness and Android sleep behavior remain manual acceptance.

## 4. Deeper thermal monitoring

### Discovery gate

- Prefer an optional **read-only HWiNFO shared-memory adapter**, as already proposed in SPEC.md. First verify current shared-memory format, installed version/provider state and available sensors on this actual Dell. Do not add a driver, install a tool or buy a license during the planning change.
- A future owner setup step must choose/install/enable the provider and open Sensors/shared memory. HWiNFO's published license matrix limits non-Pro 64-bit shared memory to 12 hours, after which it is disabled and requires manual enabling; Pro removes that runtime limit. Surface provider loss honestly and do not automatically reset the limit or imply free continuous availability.
- If that dependency is unsuitable, evaluate another documented read-only provider as a separate decision. Do not install speculative hardware-access drivers, scrape changing UI text or substitute generic ACPI thermal-zone values for CPU package temperature.
- Capture a bounded local inventory and compare available labels/units/current values with the provider UI. Establish whether the CPU package temperature, CPU/GPU fan RPM, each SSD's temperature and thermal-throttling flags actually exist. Keep machine-specific mappings in ignored local configuration.

### Data and presentation

- Enhance **Hardware** with CPU package temperature, available fan readings, individual drive temperatures, and explicitly reported CPU/GPU thermal-throttling status. Add a compact CPU temperature to Live/Home only if it fits the established composition; detailed labels/sources stay in Hardware/More.
- Preserve NVIDIA's working adapter. Prefer a verified source per metric rather than silently blending conflicting CPU package/core maximum/GPU hotspot readings.
- Map stable sensor IDs plus device/reading identity and units; reject ambiguous labels. Do not map by array position or assume the maximum temperature is the CPU package.
- Represent every extra reading with value, unit, source, observation timestamp and availability reason. Unmapped readings remain null. Per-drive temperatures attach to verified physical drive IDs; do not copy one SSD temperature onto every partition.
- Throttling is **Yes / No / Unknown** from a fresh explicit flag. A hot CPU, low frequency or power limit alone is not proof of thermal throttling. Keep thermal/power-limit flags distinct.
- Read a fixed named mapping with read-only permissions, validate header/version/counts/offsets/record lengths and cap mapped size/record count before parsing. Reject malformed/truncated/incompatible data. Verify coherent update generations to avoid mixing samples.
- Run reads approximately every two seconds outside request handlers; let the common sampler incorporate only fresh bounded results. Never keep old temperatures live after the provider stops/freezes/expires; clear them within five seconds of the last verified provider update and show the reason. Dashboard utilization/media/timer features continue operating.
- No fan control, overclocking, firmware/EC writes or automatic thermal intervention. Preserve existing Jarvis warning thresholds; new thermal-warning policies require separately verified limits and are outside this first sensor increment.

### Acceptance and scope fallback

- Parser checks cover malformed headers/offsets, unreasonable sizes, unknown versions/units, duplicate labels, NaN/infinity, stale provider timestamps, stopped provider and missing sensors. Fixtures stay in tests and never reach the live UI.
- Test ID mapping, unit conversion, per-drive association, tri-state throttling and integration failure isolation.
- Compare reported native temperatures/fans/flags against HWiNFO on this Dell at approximately the same time. Physical fan RPM and throttle flags are not declared verified until this comparison is performed; do not force thermal stress to manufacture a flag.
- If CPU temperature works but fans/SSD/throttling are absent, release the verified subset and label the rest unavailable. Sensor completeness is not a release gate for media/timer/display work.

## Delivery, documentation and validation

- Each implementation phase uses a `codex/` feature branch, appropriate checks, a commit/push and a PR targeting main. Leave review/merge to SupradeepDanturti; do not auto-merge or change protections.
- Preserve HTTPS/WSS, approved-browser access, same-origin mutations, direct-loopback owner management and the setup-only HTTP listener. New reads/artwork require approval; endpoints never accept arbitrary URLs, paths or command arrays.
- Browser display preferences are harmless local preferences. Shared timer state/sensor mapping remains in ignored private/local configuration. Never stage keys, certificates, device databases, logs, audio, conversation files or QA state.
- Backend increments run `.venv\Scripts\python.exe -m pytest -q`; changed JavaScript runs `node --check`. Use a new nonexistent ignored `.state/` basetemp if stale Windows temp ACLs require it. Never delete unrelated temp folders.
- Extend trusted Edge QA with deterministic media/timer/display/sensor mocks, and rerun relevant scripts in VALIDATION.md: browser, media-controls, tablet-layout, wake-lock, voice and security as affected. Fresh QA profiles revoke only their own credentials and never bypass certificate validation.
- Use the existing nine viewport sizes, including the reported physical Redmi 1280x800, to verify touch targets, dock clearance, sliders, portrait reflow and immersive views. Inspect screenshots; browser emulation does not replace physical acceptance.
- For each delivered phase update README.md, SETUP.md, SPEC.md and VALIDATION.md; update JARVIS_SPEC.md for timer speech and SECURITY.md for metadata/artwork/timer/activity/sensor privacy where applicable. Mark automated, native read-only and owner-confirmed physical checks separately.
- Restart only for installed backend changes, through `scripts/restart-server.ps1`, preserving approvals and CA trust. Static/frontend/documentation changes do not restart the working dashboard. This planning-only change needs no restart or runtime tests.

## Decisions carried forward

Recommended defaults are recorded above, so implementation can start without another planning round. Owner-adjustable choices belong in More: night hours/level, rotation list/dwell, the independent context switches, focus/break lengths and timer speech.

The remaining external dependency decision is the thermal provider and any license/setup it needs. It will be made after concrete sensor discovery, without presenting unverified temperatures or promising unsupported Dell controls. The first implementation PR should be **Now playing**, followed by Focus, display behavior and the verified sensor subset.

## Primary references

- [Windows media metadata](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmediaproperties?view=winrt-26100): title, artist, album and thumbnail stream.
- [Windows supported playback controls](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionplaybackcontrols?view=winrt-26100): capability checks, including position changes.
- [Windows seek API](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.trychangeplaybackpositionasync?view=winrt-26100): session-specific seeking in 100 ns units.
- [HWiNFO license matrix](https://www.hwinfo.com/licenses/): shared-memory runtime limits and manual re-enabling requirement.

References reviewed while preparing this plan. Native media metadata/seek behavior and HWiNFO shared-memory layout still require implementation-time verification.
