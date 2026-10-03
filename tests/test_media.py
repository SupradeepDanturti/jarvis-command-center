from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.media import MediaMonitor


@pytest.mark.parametrize('native,expected', [(0, 'closed'), (1, 'opened'), (2, 'changing'),
                                            (3, 'stopped'), (4, 'playing'), (5, 'paused'), (99, 'unknown')])
def test_native_playback_status(native, expected):
    monitor = MediaMonitor()
    session = Mock()
    session.get_playback_info.return_value = SimpleNamespace(playback_status=native)
    monitor.manager = Mock()
    monitor.manager.get_current_session.return_value = session
    assert monitor.sample()['status'] == expected
    assert monitor.latest['available'] == (expected != 'unknown')


def test_player_disappears_clears_previous_playing_state():
    monitor = MediaMonitor()
    monitor.latest = monitor.snapshot('playing')
    monitor.manager = Mock()
    monitor.manager.get_current_session.return_value = None
    assert monitor.sample()['status'] == 'none'
    monitor.manager.get_current_session.side_effect = RuntimeError('player exited')
    assert monitor.sample()['status'] == 'unknown'
    assert monitor.manager is None
    assert monitor.latest['available'] is False
