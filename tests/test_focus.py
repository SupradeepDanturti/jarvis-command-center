import json
from unittest.mock import Mock, patch

from fastapi import HTTPException
import pytest

from backend.focus import FocusTimer
from backend.main import create_app


class Clock:
    def __init__(self):
        self.wall, self.mono = 1000., 20.

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


def timer(clock, **kwargs):
    return FocusTimer(wall=lambda: clock.wall, monotonic=lambda: clock.mono, **kwargs)


def command(focus, action, settings=None):
    return focus.command(action, focus.snapshot()['revision'], settings)


def test_pause_resume_suspend_and_single_completion(tmp_path):
    clock, notified = Clock(), Mock()
    focus = timer(clock, path=tmp_path/'focus.json', notify=notified)
    command(focus, 'settings', {'focus': 1, 'short': 1, 'long': 2, 'announcements': True})
    command(focus, 'start')
    clock.advance(15)
    assert command(focus, 'pause')['remaining'] == 45
    clock.advance(600)
    assert focus.snapshot()['remaining'] == 45
    command(focus, 'resume')
    clock.advance(1000)  # Entire phase elapsed while laptop/browser was away.
    assert focus.snapshot()['status'] == 'complete'
    focus.snapshot()
    assert focus.completed == 1
    notified.assert_called_once_with(focus.phase_id, 'focus')
    restored = timer(clock, path=tmp_path/'focus.json', notify=notified)
    assert restored.snapshot()['status'] == 'complete'
    assert notified.call_count == 1
    assert command(restored, 'start')['phase'] == 'short'


def test_restart_recovers_remaining_and_overdue_does_not_speak(tmp_path):
    clock, notified = Clock(), Mock()
    path = tmp_path/'focus.json'
    focus = timer(clock, path=path, notify=notified)
    command(focus, 'settings', {'focus': 1, 'short': 1, 'long': 1, 'announcements': True})
    command(focus, 'start')
    clock.advance(20)
    recovered = timer(clock, path=path, notify=notified)
    assert recovered.snapshot()['remaining'] == 40
    clock.advance(41)
    overdue = timer(clock, path=path, notify=notified)
    assert overdue.snapshot()['status'] == 'complete'
    assert overdue.completed == 1
    notified.assert_not_called()


def test_four_completed_focus_phases_choose_long_break():
    clock, focus = Clock(), None
    focus = timer(clock)
    command(focus, 'settings', {'focus': 1, 'short': 1, 'long': 2, 'announcements': False})
    for count in range(1, 5):
        command(focus, 'start')
        clock.advance(61)
        assert focus.snapshot()['completed'] == count
        assert command(focus, 'start')['phase'] == ('long' if count == 4 else 'short')
        clock.advance(121)
        assert focus.snapshot()['status'] == 'complete'
    assert command(focus, 'reset')['completed'] == 0


def test_conflict_and_clock_jump_pause():
    clock = Clock()
    focus = timer(clock)
    command(focus, 'start')
    with pytest.raises(HTTPException) as error:
        focus.command('pause', 0)
    assert error.value.status_code == 409
    clock.wall += 3600
    assert focus.snapshot()['status'] == 'paused'
    assert focus.remaining == 1500
    assert 'Time changed' in focus.message


def test_invalid_saved_state_and_failed_persistence(tmp_path):
    path = tmp_path/'focus.json'
    path.write_text(json.dumps({'settings': {'focus': float('nan')}}))
    focus = FocusTimer(path)
    assert focus.snapshot()['status'] == 'ready'
    with patch('pathlib.Path.replace', side_effect=OSError):
        assert command(focus, 'start')['status'] == 'running'
    assert 'storage unavailable' in focus.message


def test_reminder_parent_idle_expiry_lock_generation_and_cancel():
    service = create_app(pairing_code='ABCD1234').state.voice
    service.process, service.pipe, service.stop_event = Mock(), Mock(), Mock()
    service.process.is_alive.return_value = True
    service.stop_event.is_set.return_value = False
    service.generation, service.phase = 3, 'thinking'
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        service.remind('phase-one', 'focus')
        service._check_reminders(3, service.pipe)
        service.pipe.send.assert_not_called()
        service.phase = 'listening'
        service._check_reminders(3, service.pipe)
        service.pipe.send.assert_called_once()
        assert service.pipe.send.call_args.args[0]['type'] == 'reminder'
        service._check_reminders(3, service.pipe)
        assert service.pipe.send.call_count == 1
        service.remind('phase-two', 'short')
        service.cancel_reminder()
        assert service.pending_reminder is None
        assert service.pipe.send.call_args.args[0]['type'] == 'reminder-cancel'
        service.remind('expired', 'focus')
        service.pending_reminder['expires'] = 0
        service._check_reminders(3, service.pipe)
        assert service.pending_reminder is None
        service.remind('old-generation', 'focus')
        service._check_reminders(2, service.pipe)
        assert service.pending_reminder is None
    with patch('backend.voice_worker.desktop_unlocked', return_value=False):
        service.remind('locked', 'focus')
        assert service.pending_reminder is None
