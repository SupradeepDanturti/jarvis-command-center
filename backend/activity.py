"""Read-only foreground game recognition; no window titles or command lines."""
import asyncio
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import time

import psutil

HELPERS = {'steam.exe', 'epicgameslauncher.exe', 'riotclientservices.exe', 'riotclientux.exe',
           'goggalaxy.exe', 'galaxyclient.exe', 'crashreportclient.exe', 'launcher.exe',
           'uninstall.exe', 'setup.exe', 'cmd.exe', 'powershell.exe'}


def match_game(executable, records):
    path = Path(executable).resolve()
    if path.suffix.lower() != '.exe' or path.name.lower() in HELPERS or any(
        term in path.name.lower() for term in ('crash', 'anticheat', 'launcher', 'updater')):
        return None
    matches = []
    for game in records:
        folder = game['folder'].resolve()
        target = game['target']
        if game['launcher'] == 'Custom':
            matched = path == Path(target).resolve()
        else:
            matched = path.is_relative_to(folder) and path != folder
        if matched:
            matches.append({'id': game['id'], 'name': game['name']})
    return matches[0] if len(matches) == 1 else None


class ActivityMonitor:
    def __init__(self, games):
        self.games = games
        self.latest = {'available': False, 'game': None, 'sampledAt': 0}

    def sample(self):
        result = {'available': False, 'game': None, 'sampledAt': time.time() * 1000}
        if os.name != 'nt':
            return result
        try:
            from .voice_worker import desktop_unlocked
            if not desktop_unlocked():
                return result
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            process_id = wintypes.DWORD()
            window = user32.GetForegroundWindow()
            if not window or not user32.GetWindowThreadProcessId(window, ctypes.byref(process_id)):
                return result
            executable = psutil.Process(process_id.value).exe()
            with self.games.lock:
                self.games.scan()
                result['game'] = match_game(executable, self.games.records.values())
            result['available'] = True
        except (OSError, ValueError, psutil.Error):
            pass
        return result

    async def run(self):
        while True:
            try:
                self.latest = await asyncio.to_thread(self.sample)
            except Exception:
                self.latest = {'available': False, 'game': None, 'sampledAt': time.time() * 1000}
            await asyncio.sleep(2)
