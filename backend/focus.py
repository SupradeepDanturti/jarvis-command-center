"""One persistent laptop timer. Browser ticks never own its countdown."""
import asyncio
import json
import math
from pathlib import Path
import secrets
import threading
import time

from fastapi import HTTPException


class FocusTimer:
    def __init__(self, path=None, wall=time.time, monotonic=time.monotonic, notify=lambda *_: None):
        self.path = Path(path) if path else None
        self.wall, self.monotonic, self.notify = wall, monotonic, notify
        self.lock = threading.RLock()
        self.settings = {'focus': 25, 'short': 5, 'long': 15, 'announcements': False}
        self.phase, self.status, self.completed = 'focus', 'ready', 0
        self.remaining, self.deadline, self.revision = 1500., None, 0
        self.phase_id = secrets.token_hex(12)
        self.message = ''
        self.anchor_wall, self.anchor_mono = self.wall(), self.monotonic()
        self._load()

    def _load(self):
        if not self.path or not self.path.is_file():
            return
        try:
            if self.path.stat().st_size > 4096:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            settings = data['settings']
            if any(type(settings[k]) is not int or not 1 <= settings[k] <= 180 for k in ('focus', 'short', 'long')):
                raise ValueError()
            if type(settings['announcements']) is not bool:
                raise ValueError()
            if data['phase'] not in {'focus', 'short', 'long'} or data['status'] not in {'ready', 'running', 'paused', 'complete'}:
                raise ValueError()
            if type(data['completed']) is not int or not 0 <= data['completed'] <= 1_000_000:
                raise ValueError()
            remaining = data['remaining']
            if type(remaining) not in {float, int} or not math.isfinite(remaining) or not 0 <= remaining <= 10800:
                raise ValueError()
            self.settings, self.phase, self.status = settings, data['phase'], data['status']
            self.completed, self.remaining = data['completed'], float(remaining)
            self.revision = data['revision'] if type(data['revision']) is int and 0 <= data['revision'] < 2**53 else 0
            self.phase_id = str(data['phaseId'])[:24]
            if self.status == 'running':
                deadline, saved_at = data['deadline'], data['savedAt']
                if (type(deadline) not in {int, float} or type(saved_at) not in {int, float}
                    or not math.isfinite(deadline) or not math.isfinite(saved_at)
                    or deadline - saved_at < 0 or deadline - saved_at > 10801 or self.wall() < saved_at - 5):
                    self.status, self.message = 'paused', 'Time changed. Review and resume your timer.'
                else:
                    self.remaining = max(0, min(10800, deadline - self.wall()))
                    self.deadline = deadline
                    if self.remaining == 0:
                        self._complete(announce=False)
        except (OSError, ValueError, KeyError, TypeError):
            self.settings = {'focus': 25, 'short': 5, 'long': 15, 'announcements': False}
            self.phase, self.status, self.remaining = 'focus', 'ready', 1500.
            self.completed, self.revision = 0, 0
            self.phase_id = secrets.token_hex(12)
            self.deadline = None
            self.message = 'Saved timer unavailable. Start a new session.'

    def _save(self):
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({**self._snapshot(), 'savedAt': self.wall()}), encoding='utf-8')
                temporary.replace(self.path)
            except OSError:
                self.message = 'Timer storage unavailable. This session may not survive a restart.'
                return False
        return True

    def _snapshot(self):
        return {'settings': dict(self.settings), 'phase': self.phase, 'status': self.status,
                'remaining': self.remaining, 'deadline': self.deadline, 'serverTime': self.wall(),
                'revision': self.revision, 'phaseId': self.phase_id, 'completed': self.completed,
                'message': self.message}

    def _complete(self, announce=True):
        self.status, self.remaining, self.deadline = 'complete', 0., None
        if self.phase == 'focus':
            self.completed += 1
        self.revision += 1
        self.message = 'Session complete. Start your next phase when ready.'
        saved = self._save()
        if saved and announce and self.settings['announcements']:
            self.notify(self.phase_id, self.phase)

    def _tick(self):
        if self.status != 'running':
            return
        now, mono = self.wall(), self.monotonic()
        elapsed_wall, elapsed_mono = now - self.anchor_wall, mono - self.anchor_mono
        if abs(elapsed_wall - elapsed_mono) > 5:
            self.remaining = max(0, self.remaining - max(0, elapsed_mono))
            self.status, self.deadline = 'paused', None
            self.message = 'Time changed. Review and resume your timer.'
            self.revision += 1
            self._save()
            return
        self.remaining = max(0, self.remaining - max(0, elapsed_mono))
        self.anchor_wall, self.anchor_mono = now, mono
        if self.remaining == 0:
            self._complete()

    def snapshot(self):
        with self.lock:
            self._tick()
            return self._snapshot()

    def command(self, action, revision, settings=None):
        with self.lock:
            self._tick()
            if revision != self.revision:
                raise HTTPException(409, 'The timer changed on another screen. Try again.')
            if action == 'settings':
                if self.status == 'running':
                    raise HTTPException(409, 'Pause the timer before changing durations.')
                self.settings = dict(settings)
                if self.status == 'ready':
                    self.remaining = self.settings[self.phase] * 60.
            elif action in {'start', 'resume'}:
                if self.status == 'running':
                    raise HTTPException(409, 'The timer is already running.')
                if self.status == 'complete':
                    self.phase = ('long' if self.completed % 4 == 0 else 'short') if self.phase == 'focus' else 'focus'
                    self.remaining = self.settings[self.phase] * 60.
                    self.phase_id = secrets.token_hex(12)
                self.status, self.message = 'running', ''
                self.anchor_wall, self.anchor_mono = self.wall(), self.monotonic()
                self.deadline = self.wall() + self.remaining
            elif action == 'pause':
                if self.status != 'running':
                    raise HTTPException(409, 'The timer is not running.')
                self.status, self.deadline = 'paused', None
            elif action in {'reset', 'skip'}:
                if action == 'skip':
                    self.phase = ('long' if self.completed and self.completed % 4 == 0 else 'short') if self.phase == 'focus' else 'focus'
                else:
                    self.phase, self.completed = 'focus', 0
                self.remaining, self.deadline = self.settings[self.phase] * 60., None
                self.status, self.message = 'ready', ''
                self.phase_id = secrets.token_hex(12)
            else:
                raise HTTPException(422, 'Unknown timer action.')
            self.revision += 1
            self._save()
            return self._snapshot()

    async def run(self):
        while True:
            self.snapshot()
            await asyncio.sleep(.25)
