"""Owner-only key storage and an on-demand, isolated laptop voice process."""
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .security import require_origin
from .tls import dpapi
from .voice_actions import execute_tool, voice_tools
from .voice_history import VoiceHistory

MODEL_FILES = ('jarvis-medium.onnx', 'jarvis-medium.onnx.json', 'hey_jarvis_v0.1.onnx',
               'melspectrogram.onnx', 'embedding_model.onnx')
DEPENDENCIES = ('piper', 'openwakeword', 'sounddevice', 'openai')


class VoiceService:
    def __init__(self, directory, registry, telemetry):
        self.directory = Path(directory) if directory else None
        self.registry, self.telemetry = registry, telemetry
        self.lock = threading.RLock()
        self.process = self.pipe = self.stop_event = None
        self.generation = 0
        self.phase = 'off'
        self.message = 'Microphone off.'
        self.last_heard = self.last_reply = ''
        self.last_started = 0
        self.input_id = None
        self.history = VoiceHistory(self.directory)
        self.followup_seconds = 15
        self.last_action = None
        if self.directory and (self.directory / 'input.json').exists():
            try:
                self.input_id = json.loads((self.directory / 'input.json').read_text(encoding='utf-8')).get('id')
            except (OSError, ValueError):
                pass
        if self.directory and (self.directory / 'settings.json').exists():
            try:
                seconds = json.loads((self.directory / 'settings.json').read_text(encoding='utf-8')).get('followupSeconds')
                if type(seconds) is int and seconds in {0, 15, 30}:
                    self.followup_seconds = seconds
            except (OSError, ValueError):
                pass

    @property
    def key_path(self):
        return self.directory / 'openai-key.dpapi'

    def status(self):
        with self.lock:
            installed = bool(self.directory and all((self.directory / 'models' / f).is_file() for f in MODEL_FILES))
            dependencies = all(importlib.util.find_spec(module) is not None for module in DEPENDENCIES)
            configured = bool(self.directory and self.key_path.is_file())
            alive = bool(self.process and self.process.is_alive())
            return {'phase': self.phase, 'message': self.message, 'enabled': alive and self.phase != 'preview',
                    'busy': alive, 'keyConfigured': configured, 'modelsInstalled': installed,
                    'dependenciesInstalled': dependencies, 'ready': installed and dependencies and configured,
                    'lastHeard': self.last_heard, 'lastReply': self.last_reply,
                    'wakePhrase': 'Hey Jarvis', 'inputId': self.input_id,
                    'followupSeconds': self.followup_seconds, 'history': self.history.recent(12)}

    def set_followup(self, seconds):
        if type(seconds) is not int or seconds not in {0, 15, 30}:
            raise HTTPException(400, 'Choose off, 15 seconds, or 30 seconds.')
        with self.lock:
            self.stop()
            self.followup_seconds = seconds
            if self.directory:
                (self.directory / 'settings.json').write_text(json.dumps({'followupSeconds': seconds}), encoding='utf-8')

    def clear_history(self):
        with self.lock:
            self.stop()
            self.history.clear()

    def audio_inputs(self):
        from .voice_audio import enumerate_in_child
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=enumerate_in_child, args=(child,), daemon=True)
        try:
            process.start()
            child.close()
            return parent.recv() if parent.poll(5) else []
        except Exception:
            return []
        finally:
            parent.close()
            child.close()
            if process.pid:
                process.join(timeout=0.2)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=0.5)

    def set_input(self, identity):
        if identity is not None and identity not in {item['id'] for item in self.audio_inputs()}:
            raise HTTPException(400, 'Choose a microphone from this laptop.')
        with self.lock:
            self.stop()
            self.input_id = identity
            if self.directory:
                self.directory.mkdir(parents=True, exist_ok=True)
                (self.directory / 'input.json').write_text(json.dumps({'id': identity}), encoding='utf-8')

    def save_key(self, key):
        if not self.directory or os.name != 'nt':
            raise HTTPException(503, 'Private Windows key storage is unavailable.')
        key = key.strip()
        if not key.startswith('sk-') or not 20 <= len(key) <= 512 or any(c.isspace() for c in key):
            raise HTTPException(400, 'Enter a valid OpenAI API key.')
        with self.lock:
            self.stop()
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.key_path.with_suffix('.tmp')
            temporary.write_bytes(dpapi(key.encode('utf-8')))
            temporary.replace(self.key_path)

    def delete_key(self):
        with self.lock:
            self.stop()
            if self.directory:
                self.key_path.unlink(missing_ok=True)

    def start(self, preview=False):
        with self.lock:
            state = self.status()
            if state['busy']:
                raise HTTPException(409, 'Jarvis is already running. Turn it off first.')
            if not state['modelsInstalled'] or not state['dependenciesInstalled']:
                raise HTTPException(409, 'Install the local voice components first. See the Jarvis setup guide.')
            if not preview and not state['keyConfigured']:
                raise HTTPException(409, 'Save an OpenAI key from the approved laptop browser first.')
            if time.monotonic() - self.last_started < 3:
                raise HTTPException(429, 'Wait a moment before starting Jarvis again.')
            try:
                key = None if preview else dpapi(self.key_path.read_bytes(), decrypt=True).decode('utf-8')
            except Exception:
                raise HTTPException(409, 'Windows could not unlock the saved key. Save it again on this laptop.') from None
            from .voice_worker import worker_main
            context = multiprocessing.get_context('spawn')
            parent, child = context.Pipe()
            stop = context.Event()
            process = context.Process(target=worker_main,
                args=(child, stop, str(self.directory / 'models'), key, voice_tools(self.registry), preview, self.input_id,
                      self.followup_seconds, self.history.context()),
                daemon=True, name='G16 Jarvis')
            self.generation += 1
            generation = self.generation
            self.phase = 'preview' if preview else 'starting'
            self.message = 'Preparing the local voice.' if preview else 'Starting Jarvis on your laptop.'
            self.last_heard = self.last_reply = ''
            self.last_action = None
            try:
                process.start()
            except Exception:
                parent.close()
                child.close()
                self.phase, self.message = 'error', 'The voice worker could not start.'
                raise HTTPException(503, self.message) from None
            child.close()
            self.process, self.pipe, self.stop_event = process, parent, stop
            self.last_started = time.monotonic()
            threading.Thread(target=self._monitor, args=(generation, process, parent), daemon=True).start()

    def _monitor(self, generation, process, pipe):
        from .voice_worker import desktop_unlocked
        try:
            while process.is_alive() or pipe.poll():
                if not pipe.poll(0.2):
                    continue
                event = pipe.recv()
                with self.lock:
                    if generation != self.generation:
                        return
                    if event.get('type') == 'action':
                        result = {'ok': False, 'message': 'Voice control is unavailable.'}
                        if self.phase == 'thinking' and not self.stop_event.is_set() and desktop_unlocked():
                            try:
                                result = execute_tool(event.get('name'), event.get('arguments'), self.registry, self.telemetry)
                            except (ValueError, TypeError, HTTPException):
                                result = {'ok': False, 'message': 'This action could not be carried out.'}
                        pipe.send({'type': 'result', 'result': result})
                        self.last_action = {'name': event.get('name'), 'arguments': event.get('arguments'),
                                            'ok': bool(result.get('ok')), 'message': result.get('message', '')[:200]}
                    elif event.get('type') == 'status':
                        self.phase = event['phase']
                        self.message = event['message'][:200]
                    elif event.get('type') == 'exchange':
                        self.last_heard = str(event.get('heard', ''))[:500]
                        self.last_reply = str(event.get('reply', ''))[:500]
                        self.history.add(event.get('heard', ''), self.last_reply, self.last_action, event.get('sources'))
                        self.last_action = None
                    elif event.get('type') == 'turn':
                        self.last_action = None
        except (EOFError, OSError, ValueError):
            pass
        finally:
            with self.lock:
                if generation == self.generation:
                    if self.phase not in {'off', 'error'}:
                        self.phase, self.message = 'error', 'Voice worker stopped. You can restart it.'
                    self.process = self.pipe = self.stop_event = None
            pipe.close()
            process.join(timeout=0.5)

    def stop(self):
        with self.lock:
            self.generation += 1  # Reject all late actions and replies from the old worker.
            process, stop, pipe = self.process, self.stop_event, self.pipe
            self.process = self.pipe = self.stop_event = None
            self.phase, self.message = 'off', 'Microphone off.'
            self.last_heard = self.last_reply = ''
            if stop:
                stop.set()
        if process:
            process.join(timeout=0.4)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if pipe:
                pipe.close()


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: SecretStr


class EnableRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool


class InputRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None


class FollowupRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seconds: int = Field(strict=True)


def voice_router(service, authenticate, owner):
    router = APIRouter(prefix='/api/voice')

    @router.get('/status', dependencies=[Depends(authenticate)])
    def status():
        return service.status()

    @router.get('/history', dependencies=[Depends(authenticate)])
    def history(before: int | None = Query(default=None, ge=1)):
        return service.history.recent(before=before)

    @router.delete('/history', dependencies=[Depends(owner), Depends(require_origin)])
    def clear_history():
        service.clear_history()
        return {'ok': True}

    @router.put('/followup', dependencies=[Depends(authenticate), Depends(require_origin)])
    def followup(body: FollowupRequest):
        service.set_followup(body.seconds)
        return service.status()

    @router.get('/inputs', dependencies=[Depends(authenticate)])
    def inputs():
        return service.audio_inputs()

    @router.put('/input', dependencies=[Depends(authenticate), Depends(require_origin)])
    def input_device(body: InputRequest):
        service.set_input(body.id)
        return service.status()

    @router.put('/key', dependencies=[Depends(owner), Depends(require_origin)])
    def save_key(body: KeyRequest):
        service.save_key(body.key.get_secret_value())
        return {'ok': True, 'keyConfigured': True}

    @router.delete('/key', dependencies=[Depends(owner), Depends(require_origin)])
    def delete_key():
        service.delete_key()
        return {'ok': True, 'keyConfigured': False}

    @router.post('/enabled', dependencies=[Depends(authenticate), Depends(require_origin)])
    def enabled(body: EnableRequest):
        if body.enabled:
            service.start()
        else:
            service.stop()
        return service.status()

    @router.post('/preview', dependencies=[Depends(authenticate), Depends(require_origin)])
    def preview():
        service.start(preview=True)
        return service.status()

    return router
