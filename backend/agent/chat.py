"""Approved typed conversations using the voice agent and its bounded history."""
import importlib.util
import multiprocessing
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..devices import COOKIE
from ..security import require_origin
from ..tls import dpapi
from .chat_worker import chat_worker
from .google import GoogleError
from .personal_tools import PERSONAL_NAMES, execute_personal, personal_tool_failure
from .memory_files import MEMORY_FILE_NAMES, execute_memory_file
from .voice_actions import execute_tool, voice_tools, safe_sources, rest_entry_requested, rest_wake_requested


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=1000)

    @field_validator('text')
    @classmethod
    def clean(cls, value):
        if not value.strip() or any((ord(c) < 32 and c not in '\n\r\t') or ord(c) == 127 for c in value):
            raise ValueError('Invalid message.')
        return value.strip()


class StopMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[0-9a-f]{24}$')


class ChatService:
    def __init__(self, voice, assistant):
        self.voice, self.assistant = voice, assistant
        self.lock = threading.RLock()
        self.turn = None

    def available(self):
        return (self.assistant.enabled and self.assistant.unlocked()
                and bool(self.voice.directory and self.voice.key_path.is_file())
                and all(importlib.util.find_spec(name) is not None for name in ('openai', 'agents')))

    def allowed(self, turn):
        return (not turn['stop'].is_set() and time.monotonic() < turn['deadline']
                and self.assistant.enabled and self.assistant.unlocked()
                and self.assistant.generation == turn['assistantGeneration']
                and self.voice.generation == turn['voiceGeneration']
                and self.voice.phase in {'off', 'listening', 'followup', 'error'}
                and turn['authorized']())

    def status(self):
        with self.lock:
            turn = self.turn
            unlocked = self.assistant.unlocked()
            busy = bool(turn and turn['phase'] == 'thinking')
            if busy and not self.allowed(turn):
                turn['stop'].set()
            return {'ready': self.available(), 'enabled': self.assistant.enabled, 'locked': not unlocked,
                    'busy': busy, 'turn': ({key: turn.get(key) for key in
                    ('id', 'phase', 'message', 'navigation')} if turn and unlocked else None),
                    'serverTime': time.time() * 1000}

    def start(self, text, authorized):
        # Match the voice controller's lock so controls/history clearing cannot race a new turn.
        with self.voice.lock, self.lock:
            if self.turn and self.turn['phase'] == 'thinking':
                raise HTTPException(409, 'Jarvis is working. Wait or stop the current request.')
            if self.voice.phase not in {'off', 'listening', 'followup', 'error'}:
                raise HTTPException(409, 'Jarvis is speaking or listening to a request. Try again in a moment.')
            if not self.available():
                raise HTTPException(409, 'Enable the personal assistant and configure the OpenAI key and Jarvis dependencies on the PC.')
            context = self.assistant.voice_context(text)
            if not authorized():
                raise HTTPException(401, 'This browser needs approval from your laptop.')
            try:
                key = dpapi(self.voice.key_path.read_bytes(), decrypt=True).decode('utf-8')
            except (OSError, ValueError, UnicodeError):
                raise HTTPException(409, 'Save the OpenAI key again on the PC.') from None
            spawn = multiprocessing.get_context('spawn')
            parent, child = spawn.Pipe()
            stop = spawn.Event()
            turn = {'id': secrets.token_hex(12), 'phase': 'thinking', 'message': 'Working on your request.',
                    'text': text, 'context': context, 'authorized': authorized, 'stop': stop,
                    'assistantGeneration': context['generation'], 'voiceGeneration': self.voice.generation,
                    'deadline': time.monotonic() + 120, 'navigation': None, 'actions': []}
            process = spawn.Process(target=chat_worker, args=(child, stop, key, text,
                                    voice_tools(self.voice.registry), context), daemon=True, name='Jarvis chat')
            self.turn = turn
            try:
                process.start()
            except (OSError, RuntimeError):
                parent.close()
                child.close()
                turn['phase'], turn['message'] = 'error', 'Jarvis could not start. Please try again.'
                turn['authorized'] = lambda: False
                turn['text'], turn['context'] = '', None
                raise HTTPException(503, turn['message']) from None
            child.close()
            threading.Thread(target=self._monitor, args=(turn, process, parent), daemon=True).start()
            return {'id': turn['id']}

    def stop(self, identity=None):
        with self.lock:
            if self.turn and (identity is None or identity == self.turn['id']):
                self.turn['stop'].set()
                self.turn['navigation'] = None

    def _navigate(self, turn, screen, **options):
        if not self.allowed(turn) or self.voice.rest and self.voice.rest.rest:
            return {'ok': False, 'message': 'Navigation is unavailable.'}
        turn['navigation'] = {'id': secrets.token_hex(12), 'screen': screen, **options,
                              'expiresAt': time.time() * 1000 + 10000}
        return {'ok': True, 'message': 'Screen requested.'}

    def dispatch(self, turn, name, arguments):
        if not self.allowed(turn):
            return {'ok': False, 'message': 'Request cancelled.'}
        try:
            if name in MEMORY_FILE_NAMES:
                with self.voice.lock:
                    result = execute_memory_file(self.assistant, name, arguments, turn['text'],
                                                 turn['assistantGeneration'], lambda: self.allowed(turn))
            elif name in PERSONAL_NAMES:
                result = execute_personal(self.assistant, name, arguments, turn['text'],
                                          turn['assistantGeneration'], lambda: self.allowed(turn))
            elif name == 'list_apps':
                result = execute_tool(name, arguments, self.voice.registry, self.voice.telemetry)
            elif name in {'rest-entry', 'rest-wake'} and arguments == {} and self.voice.rest:
                # Rest's native adapter calls voice.stop for alarms. Never invert those locks.
                if name == 'rest-entry' and rest_entry_requested(turn['text']):
                    revision = self.voice.rest.snapshot()['revision']
                    prepared = self.voice.rest.prepare('chat-' + turn['id'])
                    result = self.voice.rest.enter('chat-' + turn['id'], prepared['nonce'],
                                                  revision, lambda: self.allowed(turn))
                elif name == 'rest-wake' and rest_wake_requested(turn['text']):
                    result = self.voice.rest.wake(lambda: self.allowed(turn))
                else:
                    raise ValueError('Explicit rest request required.')
                result = {'ok': True, 'message': result['message']}
            else:
                with self.voice.lock:
                    if not self.allowed(turn):
                        return {'ok': False, 'message': 'Request cancelled.'}
                    result = execute_tool(name, arguments, self.voice.registry, self.voice.telemetry,
                                          navigate=lambda screen, **options: self._navigate(turn, screen, **options),
                                          artifacts=self.voice.artifacts)
        except (GoogleError, HTTPException, OSError, ValueError, TypeError) as error:
            result = (personal_tool_failure(name, error) if name in PERSONAL_NAMES else
                      {'ok': False, 'message': 'This action is unavailable. Check settings on the PC.'})
        if not self.allowed(turn):
            return {'ok': False, 'message': 'Request cancelled.'}
        turn['actions'].append({'name': str(name)[:60], 'ok': bool(result.get('ok')),
                                'message': str(result.get('message', ''))[:200]})
        if result.get('artifact'):
            turn['actions'][-1]['artifact'] = result['artifact']
        return result

    def _monitor(self, turn, process, pipe):
        try:
            while self.allowed(turn) and (process.is_alive() or pipe.poll()):
                if not pipe.poll(.1):
                    continue
                event = pipe.recv()
                if event.get('type') == 'action':
                    pipe.send(self.dispatch(turn, event.get('name'), event.get('arguments')))
                elif event.get('type') == 'reply':
                    with self.voice.lock, self.assistant.lock:
                        if not self.allowed(turn):
                            break
                        actions = turn['actions']
                        action = {'name': 'assistant_tools', 'ok': all(a['ok'] for a in actions),
                                  'message': ' · '.join(a['message'] for a in actions)[:200]} if actions else None
                        if action:
                            action['artifacts'] = [a['artifact'] for a in actions if a.get('artifact')]
                        context = turn['context'].get('personal') or {}
                        kind = ('personal' if 'profile' in context else 'memory' if 'localMemory' in context or
                                any(a['name'] in MEMORY_FILE_NAMES for a in actions) else 'conversation')
                        self.voice.history.add(turn['text'], event['reply'], action, safe_sources(event.get('sources')), kind=kind)
                        turn['phase'], turn['message'] = 'done', 'Ready for your next message.'
                    return
                elif event.get('type') == 'error':
                    turn['phase'], turn['message'] = 'error', str(event.get('message', 'Request failed.'))[:200]
                    return
        except (EOFError, OSError, ValueError, TypeError):
            pass
        finally:
            turn['stop'].set()
            process.join(timeout=.5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            pipe.close()
            with self.lock:
                if turn['phase'] == 'thinking':
                    turn['phase'], turn['message'] = 'cancelled', 'Request stopped. Completed actions are not undone.'
                    turn['navigation'] = None
                turn['text'], turn['context'], turn['authorized'] = '', None, lambda: False


def chat_router(service, authenticate, owner, devices):
    router = APIRouter(prefix='/api/chat', dependencies=[Depends(authenticate)])

    def secure(request):
        if request.url.scheme != 'https':
            raise HTTPException(426, 'Use the HTTPS dashboard for assistant chat.')

    @router.get('/status')
    def status(request: Request):
        secure(request)
        return service.status()

    @router.get('/history')
    def history(request: Request, before: int | None = Query(default=None, ge=1), limit: int = Query(default=50, ge=1, le=50)):
        secure(request)
        if not service.assistant.unlocked():
            raise HTTPException(409, 'Unlock the PC to view the conversation.')
        return service.voice.history.recent(limit, before)

    @router.post('/messages')
    def send(body: ChatMessage, request: Request):
        secure(request)
        require_origin(request)
        token = request.cookies.get(COOKIE)
        return service.start(body.text, lambda: bool(devices.valid(token)))

    @router.post('/stop')
    def stop(body: StopMessage, request: Request):
        secure(request)
        require_origin(request)
        service.stop(body.id)
        return {'ok': True}

    @router.delete('/history', dependencies=[Depends(owner)])
    def clear(request: Request):
        secure(request)
        require_origin(request)
        service.stop()
        service.voice.clear_history()
        return {'ok': True}

    return router
