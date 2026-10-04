"""On-demand CPU voice worker. No web frontend, local LLM, or shell access."""
from collections import deque
import ctypes
from ctypes import wintypes
import io
import os
import re
import time
import wave
from .voice_actions import respond, rest_entry_requested, rest_wake_requested


def desktop_unlocked():
    """Fail closed when Windows is locked or the input desktop is inaccessible."""
    if os.name != 'nt':
        return False
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    handle = user32.OpenInputDesktop(0, False, 1)
    if not handle:
        return False
    try:
        name, length = ctypes.create_unicode_buffer(256), wintypes.DWORD()
        return bool(user32.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(length))
                    and name.value.lower() == 'default')
    finally:
        user32.CloseDesktop(handle)


def pcm_wav(pcm):
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    data.seek(0)
    data.name = 'command.wav'
    return data


def collect_utterance(stream, allowed, pre_roll=(), wait_seconds=3, on_speech=lambda: None):
    """Wait for speech, then capture at most ten seconds, ending on 0.8s silence."""
    import numpy as np
    recording = list(pre_roll)[-3:]
    before = deque(maxlen=3)
    voice_seen, silent_frames = False, 0
    waiting = 0
    while allowed():
        audio, overflow = stream.read(1280)
        if overflow:
            return None
        chunk = bytes(audio)
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        voiced = float(np.sqrt(np.mean(samples * samples))) >= 300
        if not voice_seen:
            waiting += 1
            before.append(chunk)
            if not voiced:
                if waiting >= max(1, round(wait_seconds * 12.5)):
                    return None
                continue
            voice_seen = True
            on_speech()
            recording.extend(before)
            before.clear()
        else:
            recording.append(chunk)
        silent_frames = 0 if voiced else silent_frames + 1
        if silent_frames >= 10 or len(recording) >= 125:
            return b''.join(recording[:125])
    return None


def request_rest_entry(pipe, stop, text, speak, allowed, control=lambda message: None):
    return request_rest_action(pipe, stop, text, speak, allowed, control, waking=False)


def request_rest_wake(pipe, stop, text, speak, allowed, control=lambda message: None):
    return request_rest_action(pipe, stop, text, speak, allowed, control, waking=True)


def request_rest_action(pipe, stop, text, speak, allowed, control, waking):
    """Capture is closed; fixed power request bypasses conversational model tools."""
    matches = rest_wake_requested if waking else rest_entry_requested
    if not matches(text) or not allowed():
        return False
    if not waking:
        speak("I'll enter Rest mode, sir.")
    if not allowed():
        return False
    pipe.send({'type': 'status', 'phase': 'thinking', 'message':
               'Waking desk monitors.' if waking else 'Checking desk monitors for Rest mode.'})
    pipe.send({'type': 'rest-wake' if waking else 'rest-entry', 'heard': text})
    deadline = time.monotonic()+30
    while not stop.is_set() and time.monotonic() < deadline:
        if not desktop_unlocked():
            pipe.send({'type': 'rest-cancel'})
            return False
        if pipe.poll(.1):
            message = pipe.recv()
            if message.get('type') == 'rest-result':
                if message.get('ok') is True:
                    if waking and allowed():
                        speak('Displays awake, sir.')
                    return True
                if allowed():
                    reply = ("I couldn't wake the displays, sir. " if waking else "I couldn't enter Rest mode, sir. ") + str(message.get('message', 'Try the dashboard.'))[:200]
                    pipe.send({'type': 'exchange', 'heard': text, 'reply': reply})
                    speak(reply)
                return False
            control(message)
    if not stop.is_set():
        pipe.send({'type': 'rest-cancel'})
        if allowed():
            reply = 'The display request timed out, sir. Please try the dashboard.'
            pipe.send({'type': 'exchange', 'heard': text, 'reply': reply})
            speak(reply)
    return False


def worker_main(pipe, stop, model_directory, key, tools, preview=False, input_id=None,
                followup_seconds=15, history=None, output_id=None, alerts_enabled=True):
    # Imported only in this child; disabled Jarvis adds no inference RAM to the server.
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[variable] = '1'
    from pathlib import Path
    pending_alerts = deque(maxlen=1)
    pending_reminder = None
    reminder_id = None
    reminder_expiry = 0

    def status(phase, message):
        pipe.send({'type': 'status', 'phase': phase, 'message': message})

    def control(message):
        nonlocal alerts_enabled, pending_reminder, reminder_id, reminder_expiry
        if message.get('type') == 'alerts':
            alerts_enabled = message.get('enabled') is True
            if not alerts_enabled:
                pending_alerts.clear()
        if message.get('type') == 'alert' and alerts_enabled:
            pending_alerts.append(str(message.get('text', ''))[:500])
        if message.get('type') == 'reminder-cancel':
            pending_reminder = reminder_id = None
        if message.get('type') == 'reminder' and message.get('expires', 0) > time.time():
            pending_reminder = message
            reminder_id, reminder_expiry = message.get('id'), message['expires']

    def allowed():
        if stop.is_set() or not desktop_unlocked():
            return False
        # EOF becomes readable when the dashboard disappears, including a forced restart.
        if pipe.poll():
            try:
                control(pipe.recv())
            except (EOFError, OSError):
                stop.set()
                return False
        return True

    try:
        import numpy as np
        from piper import PiperVoice
        from .voice_audio import resolve_output, play_on_speaker
        try:
            output_device = resolve_output(output_id)
        except ValueError:
            status('error', 'Jarvis speaker unavailable. Choose a connected speaker in Jarvis settings.')
            return
        directory = Path(model_directory)
        voice = PiperVoice.load(directory / 'jarvis-medium.onnx')

        def speak(text, alert=False, reminder=False):
            identity = reminder_id
            can_speak = lambda: allowed() and (not alert or alerts_enabled) and (
                not reminder or (identity is not None and identity == reminder_id and time.time() < reminder_expiry))
            if not can_speak():
                return
            status('preview' if preview else 'alert' if alert or reminder else 'speaking',
                   'Speaking through ' + output_device['name'] + '.')
            audio = io.BytesIO()
            with wave.open(audio, 'wb') as wav:
                voice.synthesize_wav(text[:500], wav)
            if can_speak():
                play_on_speaker(audio, output_device, can_speak)

        if preview:
            speak('Good evening, sir. All systems are ready. Just say Hey Jarvis, and tell me what you need.')
            status('off', 'Voice preview finished. Microphone off.')
            return

        import sounddevice as sd
        from .voice_audio import resolve_input
        input_device = resolve_input(input_id)
        from openai import OpenAI
        from openwakeword.model import Model
        wake = Model(wakeword_models=[str(directory / 'hey_jarvis_v0.1.onnx')], inference_framework='onnx',
                     melspec_model_path=str(directory / 'melspectrogram.onnx'),
                     embedding_model_path=str(directory / 'embedding_model.onnx'))
        client = OpenAI(api_key=key, base_url='https://api.openai.com/v1', timeout=15, max_retries=0)
        key = None
        context = list(history or [])[-12:]
        followup = False

        def dispatch(name, arguments):
            if not allowed():
                return {'ok': False, 'message': 'Voice control was stopped.'}
            pipe.send({'type': 'action', 'name': name, 'arguments': arguments})
            deadline = time.monotonic() + 5
            while not stop.is_set() and time.monotonic() < deadline:
                if pipe.poll(0.08):
                    message = pipe.recv()
                    if message.get('type') == 'result':
                        return message['result']
                    control(message)
            return {'ok': False, 'message': 'Voice control timed out.'}

        with client:
            while not stop.is_set():
                if not desktop_unlocked():
                    pending_alerts.clear()
                    pending_reminder = reminder_id = None
                    followup = False
                    status('locked', 'Laptop locked. Microphone paused.')
                    while not stop.wait(0.5) and not allowed():
                        # allowed also detects a lost parent; lock itself does not stop the worker.
                        if pipe.poll():
                            control(pipe.recv())
                    if stop.is_set():
                        break
                    pending_alerts.clear()
                    pending_reminder = reminder_id = None
                if not allowed():
                    continue
                if pending_alerts:
                    text = pending_alerts.pop()
                    pipe.send({'type': 'turn'})
                    pipe.send({'type': 'exchange', 'heard': 'Hardware alert', 'reply': text, 'kind': 'alert'})
                    speak(text, alert=True)
                    stop.wait(0.5)
                    followup = False
                    continue
                if pending_reminder:
                    reminder = pending_reminder
                    pending_reminder = None
                    if time.time() < reminder['expires']:
                        speak(reminder['text'], reminder=True)
                    reminder_id = None
                    followup = False
                    continue
                wake.reset()
                frames = deque(maxlen=3)
                command = None
                status('followup' if followup else 'listening',
                       f'Your turn · listening for a reply for {followup_seconds} seconds.' if followup else
                       'Listening for Hey Jarvis · ' + input_device['name'])
                with sd.RawInputStream(device=input_device['index'], samplerate=16000, blocksize=1280, channels=1, dtype='int16') as stream:
                    if followup:
                        command = collect_utterance(stream, allowed, wait_seconds=followup_seconds,
                                                    on_speech=lambda: status('recording', 'Listening to your reply.'))
                    while not followup and allowed() and not pending_alerts and not pending_reminder:
                        audio, overflow = stream.read(1280)
                        if overflow:
                            wake.reset()
                            frames.clear()
                            continue
                        chunk = bytes(audio)
                        frames.append(chunk)
                        score = wake.predict(np.frombuffer(chunk, dtype=np.int16))
                        if max(score.values(), default=0) < 0.6:
                            continue
                        status('recording', 'Listening to your command.')
                        command = collect_utterance(stream, allowed, pre_roll=frames)
                        frames.clear()
                        break
                # Input device is closed before network calls or speaker playback.
                if not command or not allowed():
                    followup = False
                    continue
                followup = False
                pipe.send({'type': 'turn'})
                status('transcribing', 'Understanding your command.')
                try:
                    with pcm_wav(command) as audio:
                        transcript = client.audio.transcriptions.create(model='gpt-transcribe', file=audio,
                            prompt='Laptop assistant command or conversational reply. App names: Steam, Discord, Spotify, Brave, YouTube, OBS. Rest commands: enter rest mode; wake up.')
                    command = None
                    text = transcript.text.strip()[:1000]
                    if not text or not allowed():
                        continue
                    if rest_entry_requested(text):
                        request_rest_entry(pipe, stop, text, speak, allowed, control)
                        stop.wait(.5)
                        continue
                    if rest_wake_requested(text):
                        request_rest_wake(pipe, stop, text, speak, allowed, control)
                        stop.wait(.5)
                        continue
                    status('thinking', 'Working on your request.')
                    normalized = text.lower().strip().rstrip('.!?,')
                    normalized = re.sub(r'^(?:hey\s+)?jarvis[,\s:]*|[,\s]+jarvis$', '', normalized).strip()
                    end_conversation = normalized in {'thanks', 'thank you', "that's all", 'that is all', 'never mind', 'goodbye'}
                    sources = []
                    reply = 'Very good, sir.' if end_conversation else respond(client, text, tools, dispatch, allowed,
                                                                             context, cite=sources.extend)
                    if reply and allowed():
                        pipe.send({'type': 'exchange', 'heard': text, 'reply': reply, 'sources': sources})
                        context = [*context, {'role': 'user', 'content': text}, {'role': 'assistant', 'content': reply}][-12:]
                        speak(reply)
                        followup = bool(followup_seconds) and not end_conversation
                except Exception as error:
                    # API exceptions can contain request information. Never emit their contents.
                    code = getattr(error, 'status_code', None)
                    message = ('Check your OpenAI key in Jarvis settings.' if code == 401 else
                               'OpenAI usage limit reached. Check your API billing.' if code == 429 else
                               'Could not reach OpenAI. Check your connection and try again.')
                    status('error', message)
                    if stop.wait(3):
                        break
                finally:
                    command = None
                stop.wait(0.5)  # Avoid hearing the end of our own reply.
    except (EOFError, BrokenPipeError, OSError):
        try:
            status('error', 'Microphone or audio output unavailable. Check Windows sound and microphone permissions.')
        except (EOFError, OSError):
            pass
    except Exception:
        try:
            status('error', 'The local voice could not start. Check the Jarvis setup guide.')
        except (EOFError, OSError):
            pass
    finally:
        pipe.close()
