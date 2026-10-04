"""On-demand CPU voice worker. No web frontend, local LLM, or shell access."""
from collections import deque
import ctypes
from ctypes import wintypes
import io
import os
import time
import wave

from .voice_actions import respond


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


def worker_main(pipe, stop, model_directory, key, tools, preview=False, input_id=None):
    # Imported only in this child; disabled Jarvis adds no inference RAM to the server.
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[variable] = '1'
    from pathlib import Path
    import winsound

    def status(phase, message):
        pipe.send({'type': 'status', 'phase': phase, 'message': message})

    def allowed():
        if stop.is_set() or not desktop_unlocked():
            return False
        # EOF becomes readable when the dashboard disappears, including a forced restart.
        if pipe.poll():
            try:
                pipe.recv()
            except (EOFError, OSError):
                stop.set()
                return False
        return True

    try:
        import numpy as np
        from piper import PiperVoice
        directory = Path(model_directory)
        voice = PiperVoice.load(directory / 'jarvis-medium.onnx')

        def speak(text):
            if not allowed():
                return
            status('preview' if preview else 'speaking', 'Speaking on your laptop.')
            audio = io.BytesIO()
            with wave.open(audio, 'wb') as wav:
                voice.synthesize_wav(text[:500], wav)
            if allowed():
                winsound.PlaySound(audio.getvalue(), winsound.SND_MEMORY)

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
            return {'ok': False, 'message': 'Voice control timed out.'}

        with client:
            while not stop.is_set():
                if not desktop_unlocked():
                    status('locked', 'Laptop locked. Microphone paused.')
                    while not stop.wait(0.5) and not allowed():
                        # allowed also detects a lost parent; lock itself does not stop the worker.
                        if pipe.poll():
                            pipe.recv()
                    if stop.is_set():
                        break
                wake.reset()
                frames = deque(maxlen=3)
                command = None
                status('listening', 'Listening for Hey Jarvis · ' + input_device['name'])
                with sd.RawInputStream(device=input_device['index'], samplerate=16000, blocksize=1280, channels=1, dtype='int16') as stream:
                    while allowed():
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
                        recording = list(frames)
                        voice_seen, silent_frames = False, 0
                        for index in range(125):  # At most ten seconds, held only in RAM.
                            if not allowed():
                                recording = []
                                break
                            audio, overflow = stream.read(1280)
                            if overflow:
                                recording = []
                                break
                            chunk = bytes(audio)
                            recording.append(chunk)
                            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                            voiced = float(np.sqrt(np.mean(samples * samples))) >= 300
                            voice_seen = voice_seen or voiced
                            silent_frames = 0 if voiced else silent_frames + 1
                            if voice_seen and silent_frames >= 10:
                                break
                            if not voice_seen and index >= 37:
                                recording = []
                                break
                        if recording and voice_seen:
                            command = b''.join(recording)
                        recording.clear()
                        frames.clear()
                        break
                # Input device is closed before network calls or speaker playback.
                if not command or not allowed():
                    continue
                status('transcribing', 'Understanding your command.')
                try:
                    with pcm_wav(command) as audio:
                        transcript = client.audio.transcriptions.create(model='gpt-transcribe', file=audio)
                    command = None
                    text = transcript.text.strip()[:1000]
                    if not text or not allowed():
                        continue
                    status('thinking', 'Working on your request.')
                    reply = respond(client, text, tools, dispatch, allowed)
                    if reply and allowed():
                        pipe.send({'type': 'exchange', 'heard': text, 'reply': reply})
                        speak(reply)
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
