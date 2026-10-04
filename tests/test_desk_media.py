import asyncio
from datetime import datetime, timedelta, timezone
import io
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from PIL import Image
import pytest

from backend.media import MAX_ARTWORK, MediaMonitor, read_artwork, validate_artwork


def selected_player():
    monitor = MediaMonitor()
    session = Mock(source_app_user_model_id='C:\\Music\\Player.exe')
    controls = SimpleNamespace(is_play_pause_toggle_enabled=True, is_previous_enabled=True,
                               is_next_enabled=True, is_playback_position_enabled=True)
    session.get_playback_info.return_value = SimpleNamespace(playback_status=5, playback_rate=1, controls=controls)
    session.get_timeline_properties.return_value = SimpleNamespace(start_time=timedelta(), end_time=timedelta(seconds=120),
        position=timedelta(seconds=25), last_updated_time=datetime.now(timezone.utc))
    properties = SimpleNamespace(title='Track <script>', artist='Artist', album_title='Album', track_number=1, thumbnail=None)
    session.try_get_media_properties_async = AsyncMock(return_value=properties)
    session.try_change_playback_position_async = AsyncMock(return_value=True)
    session.try_toggle_play_pause_async = AsyncMock(return_value=True)
    session.add_media_properties_changed.return_value = 1
    monitor.manager = Mock()
    monitor.manager.get_current_session.return_value = session
    return monitor, session, properties


def test_metadata_and_seek_session_validation_and_units():
    async def scenario():
        monitor, session, props = selected_player()
        state = await monitor.refresh()
        assert state['title'] == 'Track <script>'
        assert state['player'] == 'Player.exe'
        assert state['timeline']['position'] == 25
        await monitor.command(state['sessionId'], state['trackRevision'], 'seek', 42)
        session.try_change_playback_position_async.assert_awaited_once_with(420_000_000)
        props.title = 'Next track'
        with pytest.raises(HTTPException) as error:
            await monitor.command(state['sessionId'], state['trackRevision'], 'seek', 10)
        assert error.value.status_code == 409
        assert session.try_change_playback_position_async.await_count == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('position', [-1, 121, float('nan'), float('inf')])
def test_invalid_seek_does_not_dispatch(position):
    async def scenario():
        monitor, session, _ = selected_player()
        state = await monitor.refresh()
        with pytest.raises(HTTPException):
            await monitor.command(state['sessionId'], state['trackRevision'], 'seek', position)
        session.try_change_playback_position_async.assert_not_called()
    asyncio.run(scenario())


def test_metadata_failure_and_late_track_result_clear_old_details():
    async def scenario():
        monitor, session, props = selected_player()
        await monitor.refresh()
        async def changed():
            monitor._changed()
            return props
        session.try_get_media_properties_async.side_effect = changed
        result = await monitor.refresh(force=True)
        assert not result.get('trackRevision')
        assert not result.get('title')
        session.try_get_media_properties_async.side_effect = RuntimeError('player gone')
        result = await monitor.refresh(force=True)
        assert not result.get('title')
        assert result['status'] == 'paused'
        monitor.manager.get_current_session.return_value = None
        assert monitor.sample()['status'] == 'none'
        assert monitor.artwork is None
    asyncio.run(scenario())


def test_native_refusal_and_disabled_control_are_not_retried():
    async def scenario():
        monitor, session, _ = selected_player()
        state = await monitor.refresh()
        session.try_toggle_play_pause_async.return_value = False
        with pytest.raises(HTTPException) as error:
            await monitor.command(state['sessionId'], state['trackRevision'], 'play-pause')
        assert error.value.status_code == 409
        session.try_toggle_play_pause_async.assert_awaited_once()
        session.get_playback_info.return_value.controls.is_playback_position_enabled = False
        with pytest.raises(HTTPException):
            await monitor.command(state['sessionId'], state['trackRevision'], 'seek', 30)
        session.try_change_playback_position_async.assert_not_called()
    asyncio.run(scenario())


def png():
    out = io.BytesIO()
    Image.new('RGB', (2, 2)).save(out, format='PNG')
    return out.getvalue()


def test_artwork_validation_rejects_non_raster_oversize_and_corruption():
    assert validate_artwork(png())[1] == 'image/png'
    assert validate_artwork(b'<svg onload="evil()"/>') is None
    assert validate_artwork(b'x' * (MAX_ARTWORK + 1)) is None
    assert validate_artwork(png()[:30]) is None


@pytest.mark.skipif(os.name != 'nt', reason='Native WinRT stream check')
def test_native_thumbnail_stream_read_is_bounded():
    from winrt.windows.storage.streams import InMemoryRandomAccessStream
    async def scenario():
        stream = InMemoryRandomAccessStream()
        await stream.write_async(png())
        reference = SimpleNamespace(open_read_async=AsyncMock(return_value=stream))
        result = await read_artwork(reference)
        assert result is not None and result[1] == 'image/png'
    asyncio.run(scenario())
