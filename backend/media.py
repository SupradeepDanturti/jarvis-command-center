"""Windows-selected media, with bounded local artwork and session-aware controls."""
import asyncio
import io
import math
import os
import secrets
import time

from fastapi import HTTPException

MAX_ARTWORK = 2 * 1024 * 1024


def seconds(value):
    number = value.total_seconds() if hasattr(value, 'total_seconds') else float(value)
    if not math.isfinite(number):
        raise ValueError('Invalid timeline')
    return number


def validate_artwork(data):
    if not data or len(data) > MAX_ARTWORK:
        return None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in {'PNG', 'JPEG', 'WEBP'} or max(picture.size) > 4096:
                return None
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[picture.format]
            picture.verify()
        return data, mime
    except Exception:
        return None


async def read_artwork(reference):
    if reference is None:
        return None
    stream = reader = None
    try:
        from winrt.windows.storage.streams import DataReader
        stream = await asyncio.wait_for(reference.open_read_async(), 2)
        size = stream.size
        if not 0 < size <= MAX_ARTWORK:
            return None
        reader = DataReader(stream.get_input_stream_at(0))
        if await asyncio.wait_for(reader.load_async(size), 2) != size:
            return None
        data = bytearray(size)
        reader.read_bytes(data)
        return await asyncio.to_thread(validate_artwork, bytes(data))
    except Exception:
        return None
    finally:
        if reader is not None:
            reader.close()
        if stream is not None:
            stream.close()


class MediaMonitor:
    def __init__(self):
        self.manager = self.session = None
        self.latest = self.snapshot('unknown')
        self.session_id = self.revision = None
        self.metadata = {}
        self.identity = None
        self.artwork = None
        self.token = None
        self.event_serial = 0
        self.read_serial = -1
        self.last_metadata = 0
        self.lock = asyncio.Lock()

    @staticmethod
    def snapshot(status):
        return {'status': status, 'available': status not in {'unknown', 'none'},
                'sampledAt': time.time() * 1000}

    def _changed(self, *_):
        self.event_serial += 1

    def _clear(self):
        if self.session is not None and self.token is not None:
            try:
                self.session.remove_media_properties_changed(self.token)
            except Exception:
                pass
        self.session = self.token = None
        self.session_id = self.revision = self.identity = None
        self.metadata = {}
        self.artwork = None
        self.last_metadata = 0
        self.read_serial = -1

    def sample(self):
        try:
            session = self.manager.get_current_session()
            if session is None:
                self._clear()
                self.latest = self.snapshot('none')
                return self.latest
            if session != self.session:
                self._clear()
                self.session = session
                self.session_id = secrets.token_hex(12)
                try:
                    self.token = session.add_media_properties_changed(self._changed)
                except Exception:
                    pass
            info = session.get_playback_info()
            if self.read_serial != self.event_serial:
                self.metadata, self.artwork, self.revision = {}, None, None
            status = {0: 'closed', 1: 'opened', 2: 'changing', 3: 'stopped', 4: 'playing',
                      5: 'paused'}.get(int(info.playback_status), 'unknown')
            controls = getattr(info, 'controls', None)
            enabled = {key: bool(getattr(controls, attr, False)) for key, attr in {
                'play-pause': 'is_play_pause_toggle_enabled', 'previous': 'is_previous_enabled',
                'next': 'is_next_enabled', 'seek': 'is_playback_position_enabled'}.items()}
            timeline = None
            try:
                native = session.get_timeline_properties()
                start, end, position = map(seconds, (native.start_time, native.end_time, native.position))
                rate = float(info.playback_rate if info.playback_rate is not None else 1)
                updated = native.last_updated_time.timestamp()
                if 0 <= start < end <= 86400 * 30 and math.isfinite(rate) and 0 <= rate <= 16:
                    advance = max(0, min(time.time() - updated, 86400 * 30)) * rate if status == 'playing' else 0
                    timeline = {'start': start, 'end': end, 'position': max(start, min(end, position + advance)),
                                'rate': rate, 'updatedAt': updated * 1000}
            except Exception:
                pass
            if timeline is None:
                enabled['seek'] = False
            if status in {'closed', 'unknown'}:
                self._clear()
                self.latest = self.snapshot(status)
            else:
                self.latest = {**self.snapshot(status), 'sessionId': self.session_id,
                               'trackRevision': self.revision, **self.metadata,
                               'timeline': timeline, 'controls': enabled,
                               'artwork': f'/api/media/artwork/{self.revision}' if self.artwork else None}
        except Exception:
            self._clear()
            self.latest = self.snapshot('unknown')
            self.manager = None
        return self.latest

    async def refresh(self, force=False):
        async with self.lock:
            return await self._refresh(force)

    async def _refresh(self, force=False):
        self.sample()
        session, sid, serial = self.session, self.session_id, self.event_serial
        if session is None:
            return self.latest
        if not force and serial == self.read_serial and time.monotonic() - self.last_metadata < 2:
            return self.latest
        self.last_metadata = time.monotonic()
        try:
            properties = await asyncio.wait_for(session.try_get_media_properties_async(), 2)
            metadata = {key: str(getattr(properties, attr, '') or '')[:500] for key, attr in {
                'title': 'title', 'artist': 'artist', 'album': 'album_title'}.items()}
            app_id = str(session.source_app_user_model_id)
            metadata['player'] = app_id.replace('\\', '/').rsplit('/', 1)[-1][:100]
            identity = (*metadata.values(), int(properties.track_number))
            changed = identity != self.identity or serial != self.read_serial
            artwork = await read_artwork(properties.thumbnail) if changed else self.artwork
            if session != self.manager.get_current_session() or sid != self.session_id or serial != self.event_serial:
                self.sample()
                return self.latest
            if changed:
                self.revision = secrets.token_hex(12)
                self.identity, self.artwork = identity, artwork
            self.metadata, self.read_serial = metadata, serial
        except Exception:
            self.metadata, self.artwork, self.identity, self.revision = {}, None, None, None
        return self.sample()

    async def command(self, session_id, revision, action, position=None):
        async with self.lock:
            await self._refresh(force=True)
            if not revision or session_id != self.session_id or revision != self.revision or self.session is None:
                raise HTTPException(409, 'The player or track changed. Try again.')
            if not self.latest.get('controls', {}).get(action):
                raise HTTPException(409, 'This player does not support that control.')
            if action == 'seek':
                timeline = self.latest.get('timeline')
                if position is None or not math.isfinite(position) or not timeline['start'] <= position <= timeline['end']:
                    raise HTTPException(422, 'Choose a position within this track.')
                operation = self.session.try_change_playback_position_async(round(position * 10_000_000))
            else:
                operation = getattr(self.session, {'play-pause': 'try_toggle_play_pause_async',
                    'previous': 'try_skip_previous_async', 'next': 'try_skip_next_async'}[action])()
            try:
                ok = await asyncio.wait_for(operation, 2)
            except Exception:
                raise HTTPException(409, 'The player did not respond. Try again.') from None
            if not ok:
                raise HTTPException(409, 'The player refused that control.')
            self.sample()
            return {'ok': True}

    async def run(self):
        if os.name != 'nt':
            return
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        except ImportError:
            return
        while True:
            try:
                if self.manager is None:
                    self.manager = await asyncio.wait_for(
                        GlobalSystemMediaTransportControlsSessionManager.request_async(), timeout=3)
                await self.refresh()
            except Exception:
                self._clear()
                self.manager = None
                self.latest = self.snapshot('unknown')
            await asyncio.sleep(.5 if self.manager is not None else 10)
