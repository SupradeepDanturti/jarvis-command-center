"""Explicitly scheduled alarm speech only: no microphone, model tools, key or cloud."""
import importlib.util
import io
import math
import multiprocessing
import os
from pathlib import Path
import threading
import time
import wave
from array import array


def alarm_worker(pipe, stop, model_directory, speaker_id, label, expires):
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'

    def allowed():
        if stop.is_set() or time.time() >= expires:
            return False
        try:
            if pipe.poll():
                pipe.recv()
                stop.set()
                return False
        except (EOFError, OSError):
            stop.set()
            return False
        return True

    try:
        from piper import PiperVoice
        from .voice_audio import resolve_output, play_on_speaker
        speaker = resolve_output(speaker_id)
        voice = PiperVoice.load(Path(model_directory) / 'jarvis-medium.onnx')
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
            voice.synthesize_wav(f"Sir, it's time to {label}.", wav)
        chime = io.BytesIO()
        pcm = array('h', (int(6000 * math.sin(2 * math.pi * (660 if i < 5500 else 880) * i / 22050)
                              * min(1, i/500, (11025-i)/500)) for i in range(11025)))
        with wave.open(chime, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050); wav.writeframes(pcm.tobytes())
        while allowed():
            pipe.send({'phase': 'speaking', 'message': 'Alarm playing through the selected laptop speaker.'})
            play_on_speaker(chime, speaker, allowed)
            if allowed():
                play_on_speaker(audio, speaker, allowed)
            if not allowed():
                break
            pipe.send({'phase': 'waiting', 'message': 'Alarm repeats every 30 seconds until snoozed or dismissed.'})
            for _ in range(60):
                if stop.wait(.5) or not allowed():
                    break
    except Exception:
        try:
            pipe.send({'phase': 'error', 'message': 'Alarm audio unavailable. Check Jarvis voice files and the selected speaker.'})
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()


class AlarmAudio:
    def __init__(self, directory, output=lambda: None):
        self.directory = Path(directory) if directory else None
        self.output = output
        self.lock = threading.RLock()
        self.process = self.pipe = self.stop_event = None
        self.phase, self.message = 'off', ''

    def ready(self):
        return bool(self.directory and all((self.directory / 'models' / name).is_file()
                    for name in ('jarvis-medium.onnx', 'jarvis-medium.onnx.json'))
                    and all(importlib.util.find_spec(name) for name in ('piper', 'sounddevice')))

    def status(self):
        with self.lock:
            try:
                while self.pipe and self.pipe.poll():
                    event = self.pipe.recv()
                    if event.get('phase') in {'speaking', 'waiting', 'error'}:
                        self.phase, self.message = event['phase'], event['message']
            except (EOFError, OSError):
                pass
            if self.process and not self.process.is_alive() and self.phase != 'error':
                self.phase = 'off'
            return {'ready': self.ready(), 'phase': self.phase, 'message': self.message}

    def start(self, label, expires):
        with self.lock:
            self.stop()
            if not self.ready():
                self.phase, self.message = 'error', 'Jarvis alarm voice is not installed. The visual alarm remains active.'
                return
            context = multiprocessing.get_context('spawn')
            self.pipe, child = context.Pipe()
            self.stop_event = context.Event()
            self.process = context.Process(target=alarm_worker, args=(child, self.stop_event,
                str(self.directory / 'models'), self.output(), label, expires), daemon=True)
            self.phase, self.message = 'starting', 'Preparing alarm speech.'
            try:
                self.process.start()
                child.close()
            except (OSError, RuntimeError):
                child.close()
                self.stop()
                self.phase, self.message = 'error', 'Alarm audio could not start.'

    def stop(self):
        with self.lock:
            if self.stop_event:
                self.stop_event.set()
            if self.process and self.process.pid:
                self.process.join(timeout=.5)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=1)
            if self.pipe:
                self.pipe.close()
            self.process = self.pipe = self.stop_event = None
            self.phase, self.message = 'off', ''
