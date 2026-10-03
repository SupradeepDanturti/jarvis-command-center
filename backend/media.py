"""Read the Windows-selected player's state without guessing from key presses."""
import asyncio
import os
import time


class MediaMonitor:
    def __init__(self):
        self.manager = None
        self.latest = self.snapshot('unknown')

    @staticmethod
    def snapshot(status):
        return {'status': status, 'available': status not in {'unknown', 'none'},
                'sampledAt': time.time() * 1000}

    def sample(self):
        try:
            session = self.manager.get_current_session()
            status = 'none' if session is None else {
                0: 'closed', 1: 'opened', 2: 'changing', 3: 'stopped',
                4: 'playing', 5: 'paused',
            }.get(int(session.get_playback_info().playback_status), 'unknown')
            self.latest = self.snapshot(status)
        except Exception:
            # Players can disappear while being queried. Never leave an old Pause icon.
            self.latest = self.snapshot('unknown')
            self.manager = None
        return self.latest

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
                self.sample()
            except Exception:
                self.manager = None
                self.latest = self.snapshot('unknown')
            await asyncio.sleep(.5 if self.manager is not None else 10)
