# Foundation validation — 2026-10-03

## Iron Man Jarvis HUD, dedicated speakers and hardware alerts

- 70 backend checks pass, including concrete speaker selection independent of headphone/default routing, selected-output PCM playback and cancellation, speaker/alerts origin/auth validation and persistence, combined exact thresholds, stale/invalid/duplicate sample rejection, global one-hour cooldown across policy reload/restart, idle/unlocked/enabled generation guards, system-alert history separation and spontaneous/cancelled warning playback without wake/STT/LLM calls.
- Trusted Edge voice checks pass for the sourced PNG helmet, red/gold controls, dedicated speaker preference, alerts switch, six active Home phases, idle/off lifecycle, black-hole preservation, live-readout layout, pointer-transparent media controls, fresh/disconnected/unpaired guards and reduced motion. All UI voice/media mutations are mocked; only QA credentials are revoked. Screenshots at 1280×800 are inspected locally.
- Home HUD content fits at 1280×800, 1280×720, 1024×600, 960×600, 412×915 and 640×400; configured voice controls fit above the 1280×800 dock. Browser checks record no page errors or CSP violations. The bars/rings visualize state and are not audio-spectrum measurements.
- Actual native enumeration detected the separate Speakers (2- Realtek(R) Audio) endpoint at the time of testing. Piper generated a short spoken preview in memory and the new explicit-endpoint helper completed playback on that speaker without changing Windows default output. Physical audibility still needs user confirmation.
- The server is restarted through the existing helper to load backend changes, preserving approvals, key and private history. Original navigation/background checks pass. Physical Redmi appearance, spontaneous threshold warnings and the alerts button during a live conversation still need acceptance after reloading and enabling Jarvis.

## Conversational Jarvis and native web search

- 61 backend checks pass, including persistence/pagination/500-record retention, six-exchange context across restart, approved history reads and owner deletion, revoked-device refusal, follow-up settings validation, speech timeout/cancellation/overflow and a complete mocked two-turn worker conversation with only one wake detection.
- Native Responses `web_search` was tested with the saved key and GPT-6 Luna: an official NASA search returned a concise update with a nasa.gov citation in approximately 4.4 seconds. The model has Jarvis-style system instructions. No laptop action was dispatched by that test.
- Trusted Edge checks cover saved history, action results, escaped inline sources (unsafe URLs rejected), follow-up settings and owner clear-history. Voice writes and microphone/playback are mocked; actual input enumeration and configuration status are read through trusted HTTPS without exposing the key.
- The configured 1280×800 Jarvis layout keeps controls above the dock, scrolls history separately and folds away the API key form. Screenshots are inspected locally. JavaScript syntax and the original browser navigation checks pass.
- The user confirmed spoken YouTube and Steam launches before this conversation update. Physical follow-up timing, local spoken web-search output, Windows-lock behavior and the Redmi Jarvis screen still require acceptance after reloading and enabling Jarvis.

## Jarvis laptop voice

- 56 backend tests pass, including DPAPI key encryption, owner/origin restrictions, revocation, strict tool arguments, locked/old-worker dispatch rejection, microphone selection, stop/unload and no retries of completed actions. Test temps use a new ignored directory. Optional voice dependencies are included in Windows CI.
- `scripts/voice-smoke.cjs` passes in trusted Edge at 1280×800: Jarvis navigation, a password key field that clears and never enters localStorage, voice preview readiness without a key, disabled listening until configured, both microphone dropdowns and shared selection, on/off controls and disabled input while running. All voice writes in this check are mocked; QA browser logs itself out and never modifies the user's voice settings/key.
- The existing browser smoke passes with the new screen available; pairing, native wake lock, original navigation/backgrounds, game library, media controls, reconnect and CSP are preserved. New JavaScript syntax checks and `pip check` pass.
- Actual downloaded ONNX models pass pinned checksums. Piper synthesized a 4.73-second sample in 1.9 seconds. A native process with Piper and the wake model used approximately 315 MB RSS after initialization and a silence inference. This is a single observed measurement, not a memory ceiling. No CUDA/Torch/local language model was installed.
- The user saved the API key through the approved laptop UI. A real `gpt-transcribe` request correctly transcribed locally synthesized “Hey Jarvis, how much memory am I using?”; `gpt-6-luna` selected `system_status`, read current hardware values through our adapter and returned a short reply. Piper synthesized that reply locally. The cloud round trip measured 5.12 seconds. No microphone or app/media action was invoked by this test; only the read-only hardware function was allowed.
- Windows initially used Stereo Mix as its default. Jarvis excludes it and offers compatible MME capture devices. After the user connected the Logitech C920e, its microphone was detected and selected, with identity saved across restart. Fresh-process enumeration and the dropdown refresh arrow support newly connected devices. A trusted native API/browser read verifies the current selection resolves to a detected input without exposing a key. The user subsequently confirmed spoken YouTube and Steam launches work. Conversational room timing, Windows-lock behavior and the Redmi Jarvis screen still require user acceptance.

```powershell
$env:G16_PLAYWRIGHT_PATH='C:\Users\suppu\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
node scripts/voice-smoke.cjs
```

## Playback state and held volume controls

- 39 backend checks passed on Windows/Python 3.14. New checks cover native playback-state mapping, disappearing/erroring players clearing old state, authenticated read-only media status, expired access, and playback snapshots in the existing authenticated WebSocket stream.
- The real Windows media-session API returned the active player's Paused status on this laptop. Reading state does not send media keys or capture track metadata. Windows-only WinRT dependencies are pinned in requirements.
- The complete trusted browser smoke check passed again: pairing, native keep-awake, all ten screens, fullscreen/ambient controls, responsive layouts, reconnect/logout, and no JavaScript or CSP errors. The background task was restarted with the existing helper to load the backend update; user approvals and certificate trust were preserved.
- `node scripts/media-controls-smoke.cjs` passed in trusted installed Edge: real status endpoint, mocked Playing/Paused/external state and Home/System icons, single-step taps, mouse and actual Chromium touch holds, release without an extra click, delayed responses without queued repeats, blur/navigation/disconnection/refusal stopping repeats, and keyboard activation. All physical media dispatch was intercepted; the user's volume and playback were not changed by QA. Only the test browser's credential was revoked.
- The user confirmed the earlier play/pause action works and that Windows volume taps change by two. Physical Redmi hold behavior and its icon after this update need confirmation after reloading.

- 27 backend tests passed locally on Windows/Python 3.14, including connection-file refresh, approved-device authorization, revocation, credential persistence, certificate renewal, isolated certificate-download routes, multi-library game discovery, invalid/stale game filtering, ID-only game dispatch, and Brave/YouTube argument resolution.
- JavaScript syntax check and Python compilation passed.
- Headless Microsoft Edge browser check passed: device pairing, live telemetry rendering, all ten pages, app logos, YouTube ID dispatch, clock format/immersive view, ambient playback/scenes, game catalog/search, graph range selection, dropped connection/reconnection, 1280×800 landscape, 800×1280 portrait, 412×915 narrow portrait, no horizontal overflow, logout revocation, and no page errors or CSP violations.
- Screenshots were visually inspected locally; generated artifacts are excluded from Git.
- Actual host detected NVIDIA GeForce RTX 4060 Laptop GPU, 20 logical CPU threads, approximately 16 GB RAM, and battery/AC information. Values are live, not fixtures.
- Local server is reachable over trusted HTTPS on port 18761. The user confirmed the physical Redmi was approved and its dashboard works after certificate setup. Real application launches and media-key behavior still need an on-device check. Automated launch tests mock dispatch to avoid opening applications unexpectedly.
- Test tooling emits a Starlette warning recommending `httpx2` for a future test-client migration; tests currently pass with the pinned `httpx` dependency.

## Reproduce optional browser check

Install Playwright separately if needed, then run `node scripts/browser-smoke.cjs` while the local server is running. The script uses installed Edge in headless mode and reads the current ignored `.state/private/pairing-code.txt`. For a bundled Playwright package, set `G16_PLAYWRIGHT_PATH` to its package directory. Screenshots are written to ignored `artifacts/`. Run `node scripts/security-smoke.cjs` to validate LAN browser approval/revocation; set `G16_TABLET_URL` to the laptop's current HTTPS LAN address if it differs from the development machine.

## Automatic screen keep-awake

- The previous implementation required a button tap, forgot that intent on reload, and did not track browser release events. Approved pages now request a screen wake lock automatically, track its actual state, and reacquire when returning to the page or after an unexpected release. Explicit opt-out persists in this browser; hiding, leaving and unpairing release the lock.
- `node scripts/wake-lock-smoke.cjs` passed controlled lifecycle checks: active/pending request reuse, visibility changes, browser release, retry delays capped at 30 seconds, repeated refusal without repeated toasts, manual recovery, persistent opt-out, late request completion after disabling, stale requests across hiding/returning, page exit/restore, unsupported browsers, and unpairing. These checks use controlled promises and events rather than waiting for physical tablet sleep.
- The trusted Edge browser check acquired an actual native `WakeLockSentinel` automatically, verified it was unreleased, checked the visible Active status, confirmed off survives reload and on reacquires after reload, exercised Clock's keep-awake controls, and verified release/recovery on simulated hidden/visible events plus release on unpairing. The complete navigation/playback/reconnection check passed with no page errors or CSP violations. QA credentials were revoked; user approvals were preserved.
- The touch layout check passed across nine viewport sizes with no reported layout issues or page errors. Modified JavaScript passed syntax checks and Git whitespace checks. Static frontend changes did not require a background-server restart or change certificate trust.
- Physical Redmi idle behavior still needs confirmation after reloading the tablet. Browser/Android restrictions, including Battery saver, can refuse the API; Tablet settings now reports Blocked or Unavailable rather than claiming a lock succeeded. API behavior and restrictions: [Chrome screen wake-lock documentation](https://developer.chrome.com/docs/capabilities/web-apis/wake-lock).

## Tablet sizing corrections

- The user's physical Redmi landscape photo showed the dock covering launcher shortcuts. Touch viewport checks reproduced overlap at 1280×720, 1024×600 and 960×600, and undersized navigation/launcher labels.
- Responsive rules now use visible viewport height, shared header/dock safe-area reservations, fluid type and portrait compositions. The Performance dock label is **Live** so every label stays readable on narrow screens. The stylesheet URL has a revision to refresh cached tablet styles on reload.
- `node scripts/tablet-layout-smoke.cjs` checks six primary screens across 1280×800, 1280×720, 1024×600, 960×600, 800×1280, 768×1024, 600×960, 412×915 and 640×400 with touch enabled. It checks page overflow, dock overlap, readable labels, tablet composition fit, full-height scenes, wide clock numerals, short-window scrolling and immersive rotation. It pairs a fresh QA browser and revokes only its own credential afterward. `--report` records issues without failing, for diagnosing a regression.
- Updated landscape/portrait Home, Apps, Games, Clock and Ambient screenshots were inspected in desktop Edge. These are browser viewport checks, not Android device emulation; the user still needs to reload the physical Redmi and confirm the revised appearance.
- Thirty backend tests passed, including approved-only display reporting, same-origin enforcement, rejection of device-ID spoofing/invalid sizes, local-owner-only reading, report expiry/capacity, and cleanup on revocation/logout. The display reports contain only layout details and are not written to the database or logs.
- The tablet check also verifies automatic size reports after resizing and entering/exiting fullscreen, live Display size text, and the copied diagnostic text (clipboard writes are mocked). Adding the display endpoint requires a background-server restart through the existing helper; existing approvals and CA files are preserved.
- After the user reloaded and entered fullscreen, the actual approved **Redmi Pad Pro** browser at 192.168.2.20 reported **1280×800** layout and visible area, **2×** pixel scale, **Landscape**, and **Fullscreen**. A second read confirmed a newer report. This verifies reporting from the physical tablet; visual satisfaction with the adjusted layout still needs user confirmation.
- A further physical-tablet report identified the processor label outside the curved ring and an oversized CPU reading. Home now sizes its complete reading from a single circle diameter; at 1280×800 the CPU font decreases from 168px to about 103px, with a smaller percent sign and more space around the label/trend/detail. The tablet browser check now tests all four corners of each element against the actual circular edge, including a 100% reading, rather than checking only the circle’s rectangular bounds. The 1280×800 screenshot was inspected; reload is needed to see this follow-up on the tablet.

## Visual screens and installed games

### App shortcut removal

- Removed Edge from the shared default app registry and its unused frontend glyph. Home and Apps use this same registry; the README launcher list is updated.
- Restarted the background server through `scripts/restart-server.ps1` to load the configuration. The trusted browser check confirmed there is no Edge entry in the server catalog, Home shortcuts or full Apps library, with the remaining navigation, media, wake-lock and playback checks passing. The QA browser revoked only its own credential.
- All 30 backend tests and modified JavaScript syntax checks passed. Existing approvals and CA trust were preserved. Open tablet pages need a reload to discard their old app tiles.

### Black-hole Home composition and sound controls

- Home now keeps the NASA Black hole movie even when another background is selected for the other pages. The browser check verifies that behavior and the visible NASA credit. The processor circle was replaced by a compact CPU value/live trace, with vitals and sound controls in an unboxed strip and app shortcuts below.
- Trusted Edge browser and touch layout checks passed after the change. Across nine sizes, the Home check verifies a 100% CPU reading fits beside the trace, the processor font stays at or below 60px, telemetry groups do not overlap, and controls avoid the dock. All six playback/volume controls stay visible and have at least 44×44px touch targets. Landscape and portrait screenshots were inspected locally.
- Volume down, mute and volume up were clicked with their HTTP dispatch mocked; each used POST and its fixed existing media ID. The check did not change the laptop's actual sound. Physical volume-key behavior and the revised Home appearance still need confirmation on the Redmi after reload.
- Clock checks exposed a test timing race between injected times and the real one-second tick. Fixed-time assertions now capture the clock state in the same browser evaluation that sets the time. The clock implementation was unchanged; the complete browser check passed afterward with no page errors or CSP violations.
- Updated frontend and check scripts passed JavaScript syntax and Git whitespace checks. No backend restart or authentication/CA change was required.

### Moving backgrounds across pages

- The trusted Edge browser check passed with local moving backgrounds on all nine ordinary screens, including Clock, and the dedicated scene on Ambient. It verifies the expected default scene per page, one shared backdrop player, negative stacking order and no pointer interception, muted inline looping, the scene override and pause surviving reload/navigation, reduced-motion pause/resume, simulated hidden/visible document events, and rapid page changes. Ambient hides and pauses the shared backdrop. No page errors or CSP violations were reported.
- The touch layout check passed across its nine viewport sizes and all Ambient choices after adding the new background settings. Updated 1280×800 Home/performance screenshots were visually inspected for contrast and readable controls. Physical Redmi playback performance still needs confirmation after reload; these checks use desktop Edge touch viewports.
- JavaScript syntax and Git whitespace checks passed. Static frontend files were updated without restarting the background server or changing approvals/CA trust. Background artwork reuses the previously bundled movies; no additional media or backend endpoint was introduced.

### Flip clock, Home atmosphere and expanded Ambient collection

- JavaScript syntax checks passed for the modified frontend and browser/rendering scripts. This update changes static assets and documentation only; the working background server was not restarted.
- Trusted Edge browser checks passed for the two-panel flip clock: simultaneous hour/minute rollover at midnight, synchronized settled halves, 12-hour midnight/noon labels, reduced-motion updates and immersive view.
- All four local movies decoded and played in Edge. Checks seek near each movie's end and observe an actual loop boundary, verify silent inline playback and valid still posters, preserve pause while changing scenes, restore the selected scene and pause after reload, and exercise rapid scene switching. The NASA scene shows its source credit. There were no page errors or CSP violations.
- Touch layout checks passed for six primary screens and all four Ambient choices across nine viewport sizes, including the physical Redmi's reported 1280×800 and short 640×400 windows. The enlarged collection controls and NASA credit fit without dock overlap or horizontal clipping. Automated checks preserve the user's devices and revoke only their QA credentials.
- Clock, Home and the expanded Ambient artwork screenshots were inspected locally. The user confirmed the preceding CPU circle/number correction on the physical Redmi. The new flip clock, background and movies still need a tablet reload and physical smoothness/appearance confirmation.

- The desk-display redesign passed real Edge checks with no sidebar or overview cards, a visible floating dock, Home fitting above the dock at 1280×800, all ten screens reachable (including the More menu), full-width Clock/Ambient, and no horizontal page overflow at 800×1280 or 412×915. Games uses its own horizontally scrolling poster rail; swiping it does not switch screens.

- Landscape, immersive-clock, ambient, game-library, and mobile screenshots were inspected. All artwork and brand logos are local; Steam covers are read from the existing authenticated laptop cache.
- Actual discovery found five installed titles across Steam, Epic, GOG and Riot: Counter-Strike 2, Red Dead Redemption 2, Sherlock Holmes: Crimes and Punishments, A Plague Tale: Requiem, and VALORANT. Unreal Engine, Fab/Quixel plugins, Steam redistributables, and stale League of Legends metadata were excluded.
- The backend was restarted through the scheduled-task helper to activate launcher changes; approved-device credentials and CA trust were preserved. Trusted HTTPS browser/security checks passed afterward.
- Game launch and Brave dispatch tests mock Windows process/protocol calls; no physical game or YouTube launch was performed during verification. The YouTube UI sends only its registered ID, and the backend test verifies the fixed URL is passed to the resolved Brave executable without a shell.
- The original video was rendered as a silent 16-second WebM loop; a real browser check observed playback returning to the start and verified motion stays paused with a reduced-motion preference. A page-switch playback race was reproduced and fixed. The newer physical Redmi layout and video smoothness still need user confirmation; earlier tablet connection/approval was user-confirmed.

## Background startup and port migration

- Installed `G16 Command Center` in Windows Task Scheduler with the current user's interactive, limited-privilege principal and a user-specific logon trigger.
- Verified the task starts `.venv/Scripts/pythonw.exe` and serves healthy HTTP responses on port 18761; the previous server on port 8000 was stopped and its listener is gone.
- Verified battery startup is allowed, switching to battery does not stop the task, execution time is unlimited, duplicate task starts are ignored, and failed launches retry three times at one-minute intervals.
- Actual Desktop resolves to the user's OneDrive Desktop; both that location and Downloads contain `G16 Command Center.txt` with the current pairing code and port-18761 URL. Files are maintained locally and excluded from the repository.
- Browser smoke checks passed against the background server on port 18761. PowerShell scripts parsed without errors; Python startup entry point compiled successfully.
- Reboot/logon behavior is configured and the task was started manually to validate its action; an actual laptop reboot was not performed.

## HTTPS and approved browsers

- Trusted HTTPS health and browser checks passed at localhost and the Wi-Fi IPv4 address. Browser certificate errors were not bypassed. Windows CA trust was explicitly confirmed by the user.
- Browser tests verified that an unknown LAN browser cannot access apps/telemetry, requires laptop approval, reconnects after page reload without a code, cannot manage other devices, and loses REST/WS access after revocation.
- Device credentials persisted when reopening the SQLite store and were denied after revocation; raw browser tokens were absent from database bytes.
- A separate HTTP setup-only listener was tested on port 18760. It returns the public CA download and instructions; credential, telemetry, control, and private-key paths return 404.
- Private-state Windows ACLs contain only this user's account, SYSTEM and administrators. The CA signing key is protected with user-scoped Windows DPAPI; only the public certificate is exported to Desktop/Downloads.
- The old HTTP tablet bookmark produced an empty response on the new TLS-only port. The user was guided to certificate installation through Android Settings and the HTTPS address.
