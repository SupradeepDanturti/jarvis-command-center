# Laptop Jarvis voice

## Scope

An optional laptop voice worker inside G16 Command Center, controlled from the existing HTTPS webpage. No Android app, separate assistant frontend, ElevenLabs, or local language model. The worker uses the laptop microphone and speakers; the Redmi remains a remote switch and status surface.

## Implemented flow

1. An approved loopback owner saves an OpenAI API key on More → Jarvis. Windows user-scoped DPAPI encrypts it in ignored `.state/private/voice/openai-key.dpapi`. No API response returns the key.
2. The user selects a laptop microphone from Jarvis or System & controls. Selection persists by a device-name/host identity rather than an unstable audio index. Stereo Mix and loopback inputs are excluded. Only 16 kHz mono-capable MME capture devices are offered. A refresh arrow enumerates inputs in a fresh short-lived process so newly connected devices are visible without restarting PortAudio inside an active worker.
3. An approved browser turns Jarvis on. The server starts an isolated, on-demand CPU worker. Disabled Jarvis holds no microphone or inference models. Closing the webpage leaves the worker running; server startup always begins off.
4. openWakeWord detects “Hey Jarvis” locally. A command of up to ten seconds is collected in memory, ending after silence. The microphone closes before network requests and playback.
5. OpenAI `gpt-transcribe` transcribes the clip or a follow-up answer. `gpt-6-luna` uses Responses function calling with reasoning effort `none` to select one registered app action, media key, or read-only hardware-status function.
6. The parent revalidates the action against its registry and current worker generation, and requires an unlocked Windows desktop. No paths, URLs, argument arrays, scripts or arbitrary commands are accepted from the model. Follow-up failures never retry completed physical actions.
7. Piper generates a synthetic Jarvis-style reply locally with `jgkawell/jarvis` medium. Playback opens an explicit speaker endpoint independently of the Windows default/headphones, with cancellation/lock checks between PCM chunks. Auto selects Realtek speakers; missing speakers fail visibly without falling back to headphones. After each reply, a configurable 15-second (default) or 30-second window accepts a conversational answer without another wake phrase. Off requires the wake phrase each turn. Silence or “thank you” returns to wake-word listening; Windows lock pauses recording.

## Interface

More → Jarvis provides microphone selection, on/off, fixed voice preview, status and saved conversation history with action results and clickable web sources. History is scrollable with earlier-page loading. Follow-up listening can be Off, 15 seconds or 30 seconds; changing this setting stops the current worker. Only the loopback owner can clear saved history, which also stops Jarvis. API key entry and deletion appear only on the approved localhost owner browser. System & controls also provides microphone and speaker dropdowns and an Open Jarvis shortcut.

Supported examples: open YouTube in Brave; open Discord/Steam; volume up/down, mute, previous/next, play-pause; CPU/RAM/GPU status. Play-pause is a toggle; volume sends one native Windows step per voice request. One action per utterance. General conversation uses the latest six saved exchanges as context. The system instructions request a calm, composed Jarvis-style manner with polished British phrasing, understated dry wit and sparing use of “sir”. Native Responses `web_search` (low search context) is available for explicit searches and current or uncertain facts. Up to five source links appear beside the saved answer; URLs are omitted from spoken output. Web content cannot authorize laptop actions.

## Iron Man interface and hardware warnings

- The voice screen uses a sourced transparent PNG Iron Man helmet stored locally with red/gold armor, cyan ring/scan animations, conversation history and the existing controls. Native phase changes drive animations. The graphics are status indicators, not measured audio levels.
- Home keeps the black-hole movie, telemetry, apps and media controls. A pointer-transparent HUD occupies its artwork stage; idle listening shows a compact armed indicator, while recording/transcribing/thinking/speaking/follow-up/alerts expand it. Labels/replies come from authenticated voice status; readings come from live telemetry. No simulated diagnostics or invented progress appears. Off, stale/disconnected, hidden or unpaired pages hide the HUD.
- Approved status polling runs on Home, Jarvis and System while visible. Expired snapshots hide activity. Revocation/unpairing clears cached voice state. Reduced motion disables new animations; narrow/short landscape uses a compact overlay.
- An approved user can select a real speaker by enumerated device identity or Auto. Only speaker endpoints are listed; headphones/default sound mappers are excluded. Input and output identities persist independently. Preview uses this same output; other applications retain their Windows output.
- Local warning thresholds are CPU ≥90%, RAM ≥90% or GPU ≥70°C for three distinct fresh samples. Warnings combine eligible metrics, wait for unlocked idle wake listening, and are generated by Piper without cloud requests. All metrics share a 3600-second cooldown, persisted in private `alerts.json` across restarts; sustained high values may warn again after that hour. Alerts on/off is usable during a running session and cancels pending/current warning playback without stopping conversation listening.
- Warnings are marked as system alerts in the bounded private history and excluded from the six-conversation context sent to OpenAI. Missing/stale/invalid readings never generate an alert. Turning Jarvis off or locking Windows prevents warning playback; startup listening remains off.

## Private state and boundaries

- Runtime models and key live below the existing ACL-protected private directory. The installer fetches only five ONNX/config artifacts over HTTPS, checks pinned SHA-256 digests and writes a local manifest. No model-training checkpoints or pickle weights are loaded.
- API audio and text requests go only through the server-side OpenAI SDK. No API key is in JavaScript, localStorage, URLs, logs or Git. No automatic cloud retries. Responses requests use `store=False`; native web search is performed by OpenAI, not an arbitrary laptop HTTP-fetch tool. API billing is required separately from ChatGPT subscriptions.
- Audio is not written to disk. Conversation text, timestamps, action results and safe source links persist in `.state/private/voice/history.sqlite3`, retaining the latest 500 exchanges across restarts. Approved browsers can read history; only the direct-loopback owner can clear it. Each cloud turn includes at most the latest six exchanges. Disabling clears the transient status but preserves saved history. Synthetic previews generated during development are ignored test artifacts.
- Native recording is opt-in through the on switch. An approved tablet may start/stop the laptop microphone, like other authorized laptop controls. The wake word does not identify the speaker; nearby speech or media can trigger it.
- Stopping invalidates the worker generation, signals cancellation, then terminates it if necessary. A lost parent pipe ends the child. Late cloud results cannot dispatch actions after disable; locking also prevents dispatch.
- Key storage does not validate API access or billing. Cloud error messages are generic and never expose exception request contents.

## Dependencies and reuse

Install optional dependencies with `requirements-voice.txt`, then run `scripts/install-voice.py`. The existing non-voice dashboard remains usable without these dependencies.

Use Piper through its published Python API and openWakeWord through its inference API. The G16 adapter, supervisor, action boundary and webpage are original project code. We do not copy the Dix01/JARVIS assistant or its frontend.

- [Piper](https://github.com/OHF-Voice/piper1-gpl): GPL-3.0 engine dependency.
- [Jarvis model](https://huggingface.co/jgkawell/jarvis): published MIT model; a synthetic approximation, not a verified exact movie voice.
- [openWakeWord](https://github.com/dscripka/openWakeWord): Apache-2.0 code; bundled pretrained wake models CC BY-NC-SA 4.0. Current installation is for personal use.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) and [file transcription](https://developers.openai.com/api/docs/guides/speech-to-text) and [native web search](https://developers.openai.com/api/docs/guides/tools-web-search).

## Validation and remaining acceptance

Automated tests cover key ownership/origin, DPAPI ciphertext, revoked-device denial, strict action arguments, cancellation, microphone selection, persistent bounded history, history authorization, follow-up capture/timeout, native citations and no action retries. A complete mocked worker turn verifies “Which app?” → “Steam” without a second wake detection. Native checks load the actual ONNX voice and wake model and synthesize speech without cloud access. Browser checks verify setup/navigation and dropdowns using a QA credential without changing the user's voice configuration.

The user saved a key through the UI. A real API check transcribed locally synthesized command audio with `gpt-transcribe`; `gpt-6-luna` selected the real read-only hardware-status tool and produced a reply, which Piper synthesized locally. This verified account/model access without recording the room or launching an app. The user confirmed spoken YouTube and Steam launches work. A real native web-search request returned a NASA update with a nasa.gov citation. Conversational room timing, Windows-lock behavior and the Redmi Jarvis screen still need live acceptance. No always-on startup, custom speaker verification, game launch, browser microphone, smart-home control or arbitrary automation is included in this first version.

## Focus completion announcements

The laptop-owned focus timer has an independent announcements preference, off by default. A completed phase can queue one fixed local phrase for an already-enabled Jarvis worker. Delivery waits for Listening, expires after 60 seconds and requires the same worker generation and unlocked desktop. Reset, skip, starting the next phase, preference changes, disabling Jarvis or locking cancel pending/late speech. The worker rechecks cancellation after synthesis and while playing audio. Missed/overdue recovery does not replay announcements.

These reminders use the selected local speaker and Piper voice without wake capture, STT, OpenAI requests, follow-up capture, transcripts or conversation-history entries. They do not change the hardware-alert switch/thresholds, turn listening on, or add voice action capabilities.

## Explicitly scheduled alarm speech

[Rest & alarms](REST_ALARM_SPEC.md) has separate per-alarm speech consent. Its isolated local Piper/speaker process opens no microphone, OpenAI client, credentials, wake detector or tools and creates no history. A chime precedes “Sir, it's time to {label}.” It can play with Windows locked and conversational Jarvis off, without unlocking or enabling listening. Entering Rest, preview and ringing stop conversational Jarvis; re-enable listening explicitly afterward. Speech repeats every 30 seconds for at most ten minutes; snooze/dismiss/cancel/replacement/shutdown stop it with cancellation checks after synthesis and between chunks. A fixed ten-second preview never changes the alarm or monitors. Missing installed voice dependencies permit visual-only alarms, and no API key is required. Existing conversational and Focus lock checks still apply to those workers.

## Literal voice Rest entry

“Hey Jarvis, enter rest mode” enters Rest only, preserving any alarm. Capture closes before acknowledgment and monitor preparation. The fixed transcript, optional Jarvis prefix/suffix, wake-phrase punctuation and optional please are matched outside the conversational model; no Rest tool is supplied to the cloud. The parent independently validates that phrase and binds preparation/confirmation to the live unlocked worker generation with a 25-second deadline. Native queue and per-monitor cancellation guards reject late actions after disable, lock, worker replacement or expiry. Success stores the authorized command/action in the bounded private history and stops Jarvis; failed requests record the fixed controller reason there. Wake/exit is by alarm or button; no voice wake or arbitrary monitor control is added. Normal STT still requires the saved key and internet.
