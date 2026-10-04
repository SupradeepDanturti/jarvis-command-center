# Laptop Jarvis voice

## Scope

An optional laptop voice worker inside G16 Command Center, controlled from the existing HTTPS webpage. No Android app, separate assistant frontend, ElevenLabs, or local language model. The worker uses the laptop microphone and speakers; the Redmi remains a remote switch and status surface.

## Implemented flow

1. An approved loopback owner saves an OpenAI API key on More → Jarvis. Windows user-scoped DPAPI encrypts it in ignored `.state/private/voice/openai-key.dpapi`. No API response returns the key.
2. The user selects a laptop microphone from Jarvis or System & controls. Selection persists by a device-name/host identity rather than an unstable audio index. Stereo Mix and loopback inputs are excluded. Only 16 kHz mono-capable MME capture devices are offered. A refresh arrow enumerates inputs in a fresh short-lived process so newly connected devices are visible without restarting PortAudio inside an active worker.
3. An approved browser turns Jarvis on. The server starts an isolated, on-demand CPU worker. Disabled Jarvis holds no microphone or inference models. Closing the webpage leaves the worker running; server startup always begins off.
4. openWakeWord detects “Hey Jarvis” locally. A command of up to ten seconds is collected in memory, ending after silence. The microphone closes before network requests and playback.
5. OpenAI `gpt-transcribe` transcribes the clip. `gpt-6-luna` uses Responses function calling with reasoning effort `none` to select one registered app action, media key, or read-only hardware-status function.
6. The parent revalidates the action against its registry and current worker generation, and requires an unlocked Windows desktop. No paths, URLs, argument arrays, scripts or arbitrary commands are accepted from the model. Follow-up failures never retry completed physical actions.
7. Piper generates a synthetic Jarvis-style reply locally with `jgkawell/jarvis` medium. Playback uses the laptop's Windows output. Listening resumes afterward and pauses while Windows is locked.

## Interface

More → Jarvis provides microphone selection, on/off, fixed voice preview, status and the latest in-memory request/reply. API key entry and deletion appear only on the approved localhost owner browser. System & controls also provides the microphone dropdown and an Open Jarvis shortcut.

Supported examples: open YouTube in Brave; open Discord/Steam; volume up/down, mute, previous/next, play-pause; CPU/RAM/GPU status. Play-pause is a toggle; volume sends one native Windows step per voice request. One action per utterance. General conversation can receive a short reply, without additional tools.

## Private state and boundaries

- Runtime models and key live below the existing ACL-protected private directory. The installer fetches only five ONNX/config artifacts over HTTPS, checks pinned SHA-256 digests and writes a local manifest. No model-training checkpoints or pickle weights are loaded.
- API audio and text requests go only through the server-side OpenAI SDK. No API key is in JavaScript, localStorage, URLs, logs or Git. No automatic cloud retries. API billing is required separately from ChatGPT subscriptions.
- Audio is not written to disk. Latest transcript/reply are bounded, in-memory status shown to approved browsers and cleared on disable. Synthetic previews generated during development are ignored test artifacts.
- Native recording is opt-in through the on switch. An approved tablet may start/stop the laptop microphone, like other authorized laptop controls. The wake word does not identify the speaker; nearby speech or media can trigger it.
- Stopping invalidates the worker generation, signals cancellation, then terminates it if necessary. A lost parent pipe ends the child. Late cloud results cannot dispatch actions after disable; locking also prevents dispatch.
- Key storage does not validate API access or billing. Cloud error messages are generic and never expose exception request contents.

## Dependencies and reuse

Install optional dependencies with `requirements-voice.txt`, then run `scripts/install-voice.py`. The existing non-voice dashboard remains usable without these dependencies.

Use Piper through its published Python API and openWakeWord through its inference API. The G16 adapter, supervisor, action boundary and webpage are original project code. We do not copy the Dix01/JARVIS assistant or its frontend.

- [Piper](https://github.com/OHF-Voice/piper1-gpl): GPL-3.0 engine dependency.
- [Jarvis model](https://huggingface.co/jgkawell/jarvis): published MIT model; a synthetic approximation, not a verified exact movie voice.
- [openWakeWord](https://github.com/dscripka/openWakeWord): Apache-2.0 code; bundled pretrained wake models CC BY-NC-SA 4.0. Current installation is for personal use.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) and [file transcription](https://developers.openai.com/api/docs/guides/speech-to-text).

## Validation and remaining acceptance

Automated tests cover key ownership/origin, DPAPI ciphertext, revoked-device denial, strict action arguments, cancellation, microphone selection and no action retries. Native checks load the actual ONNX voice and wake model and synthesize speech without cloud access. Browser checks verify setup/navigation and dropdowns using a QA credential without changing the user's voice configuration.

The user saved a key through the UI. A real API check transcribed locally synthesized command audio with `gpt-transcribe`; `gpt-6-luna` selected the real read-only hardware-status tool and produced a reply, which Piper synthesized locally. This verified account/model access without recording the room or launching an app. End-to-end room wake accuracy, spoken physical commands and tablet controls still need live user testing. No always-on startup, custom speaker verification, game launch, browser microphone, smart-home control or arbitrary automation is included in this first version.
