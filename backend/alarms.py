"""One laptop-owned, persisted alarm plus display-only Rest mode."""
import asyncio
import json
import math
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import HTTPException

ACTIVE = {'armed', 'ringing'}


class RestAlarms:
    def __init__(self, power, audio, path=None, wall=time.time, monotonic=time.monotonic, before_ring=lambda: None):
        self.power, self.audio = power, audio
        self.path = Path(path) if path else None
        self.wall, self.monotonic = wall, monotonic
        self.before_ring = before_ring
        self.lock = threading.RLock()
        self.alarm, self.revision, self.rest = None, 0, False
        self.instance = secrets.token_hex(12)
        self.message = ''
        self.nonces = {}
        self.closed = threading.Event()
        self.clock_fault = False
        self.anchor_wall, self.anchor_mono = wall(), monotonic()
        self._load()

    @staticmethod
    def validate(alarm):
        if not isinstance(alarm, dict) or set(alarm) != {'id', 'label', 'speech', 'dueAt', 'startedAt', 'status'}:
            raise ValueError()
        if not isinstance(alarm['id'], str) or not re.fullmatch('[0-9a-f]{24}', alarm['id']):
            raise ValueError()
        if (not isinstance(alarm['label'], str) or not 1 <= len(alarm['label']) <= 80
            or not alarm['label'].strip() or any(ord(c) < 32 or ord(c) == 127 for c in alarm['label'])):
            raise ValueError()
        if type(alarm['speech']) is not bool or alarm['status'] not in {'armed', 'ringing', 'dismissed', 'missed', 'paused'}:
            raise ValueError()
        for key in ('dueAt', 'startedAt'):
            value = alarm[key]
            if key == 'startedAt' and value is None:
                continue
            if type(value) not in {float, int} or not math.isfinite(value) or not 0 < value < 32503680000:
                raise ValueError()
        if alarm['status'] == 'ringing' and alarm['startedAt'] is None:
            raise ValueError()
        return dict(alarm)

    def _load(self):
        if not self.path or not self.path.is_file():
            return
        try:
            if self.path.stat().st_size > 4096:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            revision = data['revision']
            if type(revision) is not int or not 0 <= revision < 2**53-1:
                raise ValueError()
            alarm = self.validate(data['alarm']) if data['alarm'] is not None else None
            self.revision, self.alarm = revision, alarm
            saved_at = data['savedAt']
            if type(saved_at) not in {int, float} or not math.isfinite(saved_at):
                raise ValueError()
            if alarm and (alarm['status'] == 'ringing' or alarm['status'] == 'armed' and alarm['dueAt'] <= self.wall()):
                self._commit({**alarm, 'status': 'missed'})
                self.message = 'Alarm missed while the dashboard was stopped. Set a new time.'
            elif alarm and alarm['status'] == 'armed' and (alarm['dueAt'] - self.wall() > 31*86400 or self.wall() < saved_at - 5):
                self._commit({**alarm, 'status': 'paused'})
                self.message = 'Time changed. Review and set your alarm again.'
        except (ValueError, KeyError, TypeError, OSError, HTTPException):
            self.alarm, self.revision = None, 0
            self.message = 'Saved alarm unavailable. Set a new alarm.'

    def _commit(self, alarm):
        next_revision = self.revision + 1
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'revision': next_revision, 'alarm': alarm, 'savedAt': self.wall()}), encoding='utf-8')
                temporary.replace(self.path)
            except OSError:
                self.message = 'Alarm storage unavailable. No new alarm action was started.'
                raise HTTPException(503, self.message) from None
        self.alarm, self.revision = alarm, next_revision

    def _check_revision(self, revision):
        if revision != self.revision:
            raise HTTPException(409, 'The alarm changed on another screen. Check it and try again.')

    def _hold(self):
        self.power.hold(self.rest or bool(not self.clock_fault and self.alarm and self.alarm['status'] in ACTIVE))

    def _restore_hold(self):
        try:
            self._hold()
        except OSError:
            self.message = 'Windows awake request unavailable.'

    def snapshot(self):
        with self.lock:
            return {'instance': self.instance, 'revision': self.revision, 'serverTime': self.wall()*1000,
                    'rest': self.rest, 'displayAvailable': self.power.available,
                    'keepingAwake': self.power.held,
                    'alarm': {**self.alarm, 'status': 'paused'} if self.alarm and self.clock_fault else dict(self.alarm) if self.alarm else None,
                    'message': self.message, 'audio': self.audio.status()}

    def arm(self, revision, due_at, label, speech):
        with self.lock:
            self._check_revision(revision)
            if not math.isfinite(due_at) or not 5 <= due_at - self.wall() <= 31*86400:
                raise HTTPException(422, 'Choose an alarm time from five seconds to 31 days ahead.')
            alarm = self.validate({'id': secrets.token_hex(12), 'label': label.strip(), 'speech': speech,
                                  'dueAt': due_at, 'startedAt': None, 'status': 'armed'})
            if speech and not self.audio.ready():
                raise HTTPException(409, 'Install the Jarvis voice first, or turn off spoken announcement.')
            try:
                self.power.hold(True)
                self._commit(alarm)
            except OSError:
                raise HTTPException(503, 'Could not keep the laptop awake. The alarm was not armed.') from None
            except HTTPException:
                self._restore_hold()
                raise
            self.audio.stop()
            self.clock_fault = False
            self.message = ''
            self.anchor_wall, self.anchor_mono = self.wall(), self.monotonic()
            return self.snapshot()

    def command(self, revision, action):
        with self.lock:
            self._check_revision(revision)
            if action == 'snooze':
                if not self.alarm or self.alarm['status'] != 'ringing':
                    raise HTTPException(409, 'Only a ringing alarm can be snoozed.')
                alarm = {**self.alarm, 'status': 'armed', 'dueAt': self.wall()+300, 'startedAt': None}
            elif action == 'dismiss':
                if not self.alarm or self.alarm['status'] != 'ringing':
                    raise HTTPException(409, 'The alarm is no longer ringing.')
                alarm = {**self.alarm, 'status': 'dismissed'}
            elif action == 'cancel':
                alarm = None
            else:
                raise HTTPException(422, 'Unknown alarm action.')
            self.audio.stop()
            self._commit(alarm)
            self.clock_fault = False
            self.message = ''
            try:
                self._hold()
            except OSError:
                self.message = 'Windows awake request unavailable.'
            return self.snapshot()

    def prepare(self, device_id):
        # USB-C dock discovery can take several seconds. Do not hold shared alarm state
        # or stop WebSocket/health traffic during this read-only preparation.
        try:
            if not self.power.probe():
                raise OSError()
        except OSError:
            raise HTTPException(503, 'No controllable desk monitor found. Enable DDC/CI; your dock must support monitor power commands.') from None
        with self.lock:
            now = self.monotonic()
            self.nonces = {key: value for key, value in self.nonces.items() if value[1] > now}
            if len(self.nonces) >= 128 and device_id not in self.nonces:
                raise HTTPException(429, 'Try Rest mode again shortly.')
            nonce = secrets.token_hex(12)
            self.nonces[device_id] = (nonce, now+30)
            return {'nonce': nonce}

    def preview(self):
        with self.lock:
            if self.alarm and self.alarm['status'] == 'ringing':
                raise HTTPException(409, 'Dismiss or snooze the alarm first.')
            if not self.audio.ready():
                raise HTTPException(409, 'Jarvis alarm voice is not installed.')
            self.before_ring()
            self.audio.start('wake up', self.wall()+10)
            return self.snapshot()

    def enter(self, device_id, nonce, revision, allowed=lambda: True):
        with self.lock:
            if self.closed.is_set() or not allowed():
                raise HTTPException(409, 'Rest entry was cancelled.')
            prepared = self.nonces.pop(device_id, None)
            if not prepared or prepared[1] <= self.monotonic() or not secrets.compare_digest(prepared[0], nonce):
                raise HTTPException(409, 'Rest confirmation expired. Try again.')
            self._check_revision(revision)
            if self.alarm and self.alarm['status'] == 'ringing':
                raise HTTPException(409, 'Dismiss or snooze the alarm first.')
            try:
                self.power.hold(True)
                self._commit(self.alarm)
                if not allowed():
                    raise HTTPException(409, 'Rest entry was cancelled.')
                self.power.off(allowed=allowed)
                self.rest, self.message = True, 'Desk monitor power-off requested. Laptop stays awake.'
            except OSError:
                self._restore_hold()
                raise HTTPException(503, 'Monitor power-off unavailable. Enable DDC/CI in your monitor menu. No system sleep was requested.') from None
            except HTTPException:
                self._restore_hold()
                raise
            return self.snapshot()

    def wake(self, allowed=lambda: True):
        with self.lock:
            if self.closed.is_set() or not allowed():
                raise HTTPException(409, 'Display wake was cancelled.')
            try:
                self.power.wake(allowed=allowed)
            except OSError:
                raise HTTPException(503, 'Windows display wake request failed.') from None
            was_rest = self.rest
            self.rest, self.message = False, 'Laptop display wake requested.'
            if was_rest:
                try:
                    self._commit(self.alarm)
                except HTTPException:
                    # Exiting an ephemeral dim screen must remain possible with a full disk.
                    self.revision += 1
                    self.message = 'Laptop display wake requested. Alarm storage unavailable.'
            self._restore_hold()
            return self.snapshot()

    def tick(self):
        with self.lock:
            if self.closed.is_set():
                return
            now, mono = self.wall(), self.monotonic()
            jumped = abs((now-self.anchor_wall) - (mono-self.anchor_mono)) > 5
            self.anchor_wall, self.anchor_mono = now, mono
            alarm = self.alarm
            if jumped and alarm and alarm['status'] in ACTIVE:
                self.clock_fault = True
                self.audio.stop()
                self._restore_hold()
            if self.clock_fault and alarm:
                self._commit({**alarm, 'status': 'paused'})
                self.clock_fault = False
                self.message = 'Time changed. Review and set your alarm again.'
            elif alarm and alarm['status'] == 'armed' and now >= alarm['dueAt']:
                if now - alarm['dueAt'] > 60:
                    self._commit({**alarm, 'status': 'missed'})
                    self.message = 'Alarm missed while the laptop was unavailable. Set a new time.'
                else:
                    self._commit({**alarm, 'status': 'ringing', 'startedAt': now})
                    self.rest = False
                    if self.closed.is_set():
                        return
                    self.before_ring()
                    try:
                        self.power.wake()
                        self.message = 'Alarm active. Laptop display wake requested.'
                    except OSError:
                        self.message = 'Alarm active. Windows display wake request failed.'
                    if alarm['speech'] and not self.closed.is_set():
                        self.audio.start(alarm['label'], now+600)
            elif alarm and alarm['status'] == 'ringing' and now-alarm['startedAt'] >= 600:
                self._commit({**alarm, 'status': 'missed'})
                self.audio.stop()
                self.message = 'Alarm stopped after ten minutes.'
            try:
                self._hold()
            except OSError:
                self.message = 'Windows awake request unavailable. Keep the laptop awake for your alarm.'

    def close(self):
        self.closed.set()
        with self.lock:
            # A cancelled to_thread tick may still be finishing; serialize cleanup after it.
            self.audio.stop()
            self.power.close()

    async def run(self):
        try:
            while True:
                try:
                    await asyncio.to_thread(self.tick)
                except HTTPException:
                    pass  # Storage warning is public; do not dispatch unpersisted effects.
                await asyncio.sleep(.5)
        finally:
            self.closed.set()
            await asyncio.to_thread(self.close)
