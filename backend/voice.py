"""Owner-only key storage and an on-demand, isolated laptop voice process."""
import importlib.util
import json
import multiprocessing
import os
import secrets
import sqlite3
from pathlib import Path
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .security import require_origin
from .tls import dpapi
from .voice_actions import execute_tool, voice_tools, rest_entry_requested, rest_wake_requested, VOICE_SCREENS
from .voice_history import VoiceHistory
from .voice_alerts import HardwareAlerts
from .voice_wake import WAKE_MODEL, WAKE_PHRASE
from .ambient import load_ambient_scenes

MODEL_FILES = ('jarvis-medium.onnx', 'jarvis-medium.onnx.json', WAKE_MODEL,
               'melspectrogram.onnx', 'embedding_model.onnx')
DEPENDENCIES = ('piper', 'openwakeword', 'sounddevice', 'openai', 'agents')


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
        self.last_actions = []
        self.output_id = None
        self.alerts_enabled = True
        self.pending_reminder = None
        self.rest = None
        self.pending_rest = None
        self.navigation = None
        self.alert_policy = HardwareAlerts(self.directory / 'alerts.json' if self.directory else None)
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
                alerts = json.loads((self.directory / 'settings.json').read_text(encoding='utf-8')).get('alertsEnabled')
                if type(alerts) is bool:
                    self.alerts_enabled = alerts
            except (OSError, ValueError):
                pass

        if self.directory and (self.directory / 'output.json').exists():
            try:
                self.output_id = json.loads((self.directory / 'output.json').read_text(encoding='utf-8')).get('id')
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
                    'wakePhrase': WAKE_PHRASE, 'inputId': self.input_id,
                    'followupSeconds': self.followup_seconds, 'history': self.history.recent(12),
                    'outputId': self.output_id, 'alertsEnabled': self.alerts_enabled,
                    'navigation': self._navigation_snapshot(), 'serverTime': time.time() * 1000}

    def _navigation_snapshot(self):
        from .voice_worker import desktop_unlocked
        if self.navigation and (self.navigation['expiresAt'] <= time.time() * 1000
            or not self.process or not self.process.is_alive() or self.stop_event is None
            or self.stop_event.is_set() or self.phase in {'off', 'preview', 'locked', 'error'}
            or not desktop_unlocked()):
            self.navigation = None
        return dict(self.navigation) if self.navigation else None

    def _show_screen(self, screen, scene=None):
        # Called under the parent lock after checking the live worker generation.
        # Read the flag without acquiring Rest's lock: alarm delivery calls voice.stop under that lock.
        if self.rest is not None and self.rest.rest:
            return {'ok': False, 'message': 'Wake the displays before changing screens, sir.'}
        label = VOICE_SCREENS[screen]
        if scene is not None:
            available = load_ambient_scenes()
            if screen != 'ambient' or scene not in available:
                raise ValueError('This Ambient scene is unavailable.')
            label += ' · ' + available[scene]['name']
        self.navigation = {'id': secrets.token_hex(12), 'screen': screen, 'expiresAt': time.time() * 1000 + 10000}
        if scene is not None:
            self.navigation['scene'] = scene
        return {'ok': True, 'message': f'Requested {label} on active dashboard screens.',
                'delivery': 'Visible connected browsers only; disabled widgets open their settings.'}

    def set_followup(self, seconds):
        if type(seconds) is not int or seconds not in {0, 15, 30}:
            raise HTTPException(400, 'Choose off, 15 seconds, or 30 seconds.')
        with self.lock:
            self.stop()
            self.followup_seconds = seconds
            self._save_settings()

    def _save_settings(self):
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / 'settings.json').write_text(json.dumps({
                'followupSeconds': self.followup_seconds, 'alertsEnabled': self.alerts_enabled}), encoding='utf-8')

    def set_alerts(self, enabled):
        with self.lock:
            self.alerts_enabled = enabled
            self._save_settings()
            if self.pipe and self.process and self.process.is_alive():
                try:
                    self.pipe.send({'type': 'alerts', 'enabled': enabled})
                except (EOFError, OSError):
                    pass

    def set_output(self, identity):
        if identity is not None and identity not in {item['id'] for item in self.audio_inputs(output=True)}:
            raise HTTPException(400, 'Choose a speaker from this laptop.')
        with self.lock:
            self.stop()
            self.output_id = identity
            if self.directory:
                self.directory.mkdir(parents=True, exist_ok=True)
                (self.directory / 'output.json').write_text(json.dumps({'id': identity}), encoding='utf-8')

    def clear_history(self):
        with self.lock:
            self.stop()
            self.history.clear()

    def audio_inputs(self, output=False):
        from .voice_audio import enumerate_in_child
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=enumerate_in_child, args=(child, output), daemon=True)
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
                      self.followup_seconds, self.history.context(), self.output_id, self.alerts_enabled),
                daemon=True, name='G16 Jarvis')
            self.alert_policy = HardwareAlerts(self.directory / 'alerts.json' if self.directory else None)
            self.generation += 1
            generation = self.generation
            self.phase = 'preview' if preview else 'starting'
            self.message = 'Preparing the local voice.' if preview else 'Starting Jarvis on your laptop.'
            self.last_heard = self.last_reply = ''
            self.last_action = None
            self.last_actions = []
            self.navigation = None
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

    def _check_alerts(self, generation, pipe):
        from .voice_worker import desktop_unlocked
        with self.lock:
            if generation != self.generation or not self.alerts_enabled or self.phase != 'listening':
                return
            if self.stop_event.is_set() or not desktop_unlocked():
                return
            text = self.alert_policy.evaluate(self.telemetry.latest)
            if text:
                pipe.send({'type': 'alert', 'text': text})
                self.phase, self.message = 'alert', 'Hardware threshold reached.'

    def remind(self, identity, phase):
        from .voice_worker import desktop_unlocked
        with self.lock:
            if (phase not in {'focus', 'short', 'long'} or not self.process or not self.process.is_alive()
                or self.phase in {'off', 'preview', 'locked', 'error'} or not desktop_unlocked()):
                return
            phrase = ('Your focus session is complete. Time for a break.' if phase == 'focus' else
                      'Your break is complete. Ready for another focus session?')
            self.pending_reminder = {'type': 'reminder', 'id': identity, 'text': phrase,
                                     'expires': time.time() + 60, 'generation': self.generation}

    def cancel_reminder(self):
        with self.lock:
            self.pending_reminder = None
            if self.pipe and self.process and self.process.is_alive():
                try:
                    self.pipe.send({'type': 'reminder-cancel'})
                except (EOFError, OSError):
                    pass

    def _check_reminders(self, generation, pipe):
        from .voice_worker import desktop_unlocked
        with self.lock:
            reminder = self.pending_reminder
            if reminder is None:
                return
            if (reminder['generation'] != generation or generation != self.generation
                or reminder['expires'] <= time.time() or self.stop_event.is_set() or not desktop_unlocked()):
                self.pending_reminder = None
                return
            if self.phase == 'listening':
                pipe.send({k: v for k, v in reminder.items() if k != 'generation'})
                self.pending_reminder = None
                self.phase, self.message = 'alert', 'Focus reminder.'

    def _rest_allowed(self, request, process):
        from .voice_worker import desktop_unlocked
        with self.lock:
            live = (request == self.pending_rest and request[0] == self.generation
                    and time.monotonic() < request[2] and process is self.process and process.is_alive()
                    and self.stop_event is not None and not self.stop_event.is_set() and desktop_unlocked())
            if not live and self.pending_rest == request:
                self.pending_rest = None
            return bool(live)

    def _enter_rest(self, request, process, pipe, heard, waking=False):
        allowed = lambda: self._rest_allowed(request, process)
        try:
            if not allowed():
                return
            if waking:
                self.rest.wake(allowed=allowed)
            else:
                device_id = 'voice:' + request[1]
                prepared = self.rest.prepare(device_id)
                if not allowed():
                    return
                self.rest.enter(device_id, prepared['nonce'], self.rest.snapshot()['revision'], allowed=allowed)
            with self.lock:
                if request != self.pending_rest or request[0] != self.generation:
                    return
                try:
                    reply = 'Displays awake, sir.' if waking else 'Rest mode entered, sir.'
                    self.last_heard, self.last_reply = heard[:500], reply
                    self.history.add(heard, reply,
                        {'name': 'wake_displays' if waking else 'enter_rest_mode', 'arguments': {}, 'ok': True,
                         'message': 'Desk monitors powered on.' if waking else 'Desk monitors powered off.'})
                except (sqlite3.Error, OSError, ValueError):
                    pass
                pipe.send({'type': 'rest-result', 'ok': True})
        except (HTTPException, OSError) as error:
            if allowed():
                try:
                    pipe.send({'type': 'rest-result', 'ok': False,
                               'message': str(error.detail)[:200] if isinstance(error, HTTPException) else
                                          'Check DDC/CI and the monitor connection, or try the dashboard.'})
                except (EOFError, OSError):
                    pass
        finally:
            with self.lock:
                if self.pending_rest == request:
                    self.pending_rest = None

    def _request_rest(self, generation, process, pipe, event):
        from .voice_worker import desktop_unlocked
        waking = event.get('type') == 'rest-wake'
        matches = rest_wake_requested if waking else rest_entry_requested
        with self.lock:
            if (set(event) != {'type', 'heard'} or event.get('type') not in {'rest-entry', 'rest-wake'} or not matches(event.get('heard'))
                or self.rest is None or self.pending_rest is not None or generation != self.generation
                or self.phase != 'thinking' or self.stop_event is None or self.stop_event.is_set()
                or process is not self.process or not process.is_alive() or not desktop_unlocked()):
                pipe.send({'type': 'rest-result', 'ok': False, 'message': 'Rest voice entry is unavailable.'})
                return
            request = (generation, secrets.token_hex(12), time.monotonic()+25)
            self.pending_rest = request
            self.last_heard = event['heard'][:500]
        threading.Thread(target=self._enter_rest, args=(request, process, pipe, event['heard'], waking),
                         daemon=True, name='voice-rest').start()

    def _monitor(self, generation, process, pipe):
        from .voice_worker import desktop_unlocked
        try:
            while process.is_alive() or pipe.poll():
                with self.lock:
                    pending_rest = self.pending_rest
                if pending_rest is not None:
                    self._rest_allowed(pending_rest, process)
                self._check_alerts(generation, pipe)
                self._check_reminders(generation, pipe)
                if not pipe.poll(0.2):
                    continue
                event = pipe.recv()
                app_inventory = None
                if event.get('type') == 'action' and event.get('name') == 'list_apps':
                    # Windows enumeration is read-only and may take seconds. Keep stop/lock/status responsive.
                    with self.lock:
                        if generation != self.generation:
                            return
                        discover = (self.phase == 'thinking' and self.pending_rest is None
                                    and not self.stop_event.is_set() and desktop_unlocked())
                    if discover:
                        try:
                            app_inventory = execute_tool('list_apps', event.get('arguments'), self.registry, self.telemetry)
                        except (ValueError, TypeError, HTTPException):
                            app_inventory = {'ok': False, 'message': 'Available apps could not be read. Try again shortly.'}
                with self.lock:
                    if generation != self.generation:
                        return
                    if event.get('type') in {'rest-entry', 'rest-wake'}:
                        self._request_rest(generation, process, pipe, event)
                    elif event.get('type') == 'rest-cancel':
                        self.pending_rest = None
                    elif event.get('type') == 'action':
                        result = {'ok': False, 'message': 'Voice control is unavailable.'}
                        if self.phase == 'thinking' and self.pending_rest is None and not self.stop_event.is_set() and desktop_unlocked():
                            try:
                                if event.get('name') == 'list_apps':
                                    result = app_inventory or result
                                else:
                                    result = execute_tool(event.get('name'), event.get('arguments'), self.registry,
                                                          self.telemetry, navigate=self._show_screen)
                            except (ValueError, TypeError, HTTPException):
                                result = {'ok': False, 'message': 'This action could not be carried out.'}
                        pipe.send({'type': 'result', 'id': event.get('id'), 'result': result})
                        self.last_action = {'name': event.get('name'), 'arguments': event.get('arguments'),
                                            'ok': bool(result.get('ok')), 'message': result.get('message', '')[:200]}
                        self.last_actions.append(self.last_action)
                        if len(self.last_actions) > 1:
                            self.last_action = {'name': 'parallel_tools', 'arguments': {},
                                'ok': all(action['ok'] for action in self.last_actions),
                                'message': ' · '.join(action['message'] for action in self.last_actions)[:200],
                                'actions': list(self.last_actions)}
                    elif event.get('type') == 'status':
                        self.phase = event['phase']
                        self.message = event['message'][:200]
                        if self.phase in {'off', 'preview', 'locked', 'error'}:
                            self.navigation = None
                    elif event.get('type') == 'exchange':
                        self.last_heard = str(event.get('heard', ''))[:500]
                        self.last_reply = str(event.get('reply', ''))[:500]
                        self.history.add(event.get('heard', ''), self.last_reply, self.last_action, event.get('sources'),
                                         kind='alert' if event.get('kind') == 'alert' else 'conversation')
                        self.last_action = None
                        self.last_actions = []
                    elif event.get('type') == 'turn':
                        self.last_action = None
                        self.last_actions = []
        except (EOFError, OSError, ValueError):
            pass
        finally:
            with self.lock:
                if generation == self.generation:
                    if self.phase not in {'off', 'error'}:
                        self.phase, self.message = 'error', 'Voice worker stopped. You can restart it.'
                    self.process = self.pipe = self.stop_event = None
                    self.navigation = None
            pipe.close()
            process.join(timeout=0.5)

    def stop(self):
        with self.lock:
            self.generation += 1  # Reject all late actions and replies from the old worker.
            self.pending_reminder = None
            self.pending_rest = None
            self.navigation = None
            process, stop, pipe = self.process, self.stop_event, self.pipe
            self.process = self.pipe = self.stop_event = None
            self.phase, self.message = 'off', 'Microphone off.'
            self.last_heard = self.last_reply = ''
            self.last_action = None
            self.last_actions = []
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

    @router.get('/outputs', dependencies=[Depends(authenticate)])
    def outputs():
        return service.audio_inputs(output=True)

    @router.put('/output', dependencies=[Depends(authenticate), Depends(require_origin)])
    def output_device(body: InputRequest):
        service.set_output(body.id)
        return service.status()

    @router.put('/alerts', dependencies=[Depends(authenticate), Depends(require_origin)])
    def alerts(body: EnableRequest):
        service.set_alerts(body.enabled)
        return service.status()

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
