"""Trusted, laptop-side registrations only. No client-supplied executable or shell."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import psutil
from fastapi import HTTPException
from .app_discovery import discover_apps, executable_path

ROOT = Path(__file__).resolve().parents[1]
URI_PREFIXES = ("steam://", "discord://", "spotify:", "microsoft-edge:", "ms-settings:")
MEDIA_KEYS = {"volume-up": 0xAF, "volume-down": 0xAE, "mute": 0xAD,
              "play-pause": 0xB3, "next": 0xB0, "previous": 0xB1}


class AppRegistry:
    MAX_APPS = 25

    def __init__(self, selection_path=None):
        self.lock = threading.RLock()
        self.selection_path = Path(selection_path) if selection_path else None
        self.detected = {}
        self.discovered_at = 0
        path = ROOT / "config/apps.local.json"
        if not path.exists():
            path = ROOT / "config/apps.json"
        if self.selection_path and self.selection_path.exists():
            path = self.selection_path
        self.apps = json.loads(path.read_text(encoding="utf-8"))
        ids = [app["id"] for app in self.apps]
        if len(ids) != len(set(ids)):
            raise ValueError("Application IDs must be unique")

    def discover(self):
        with self.lock:
            if not self.discovered_at or time.monotonic() - self.discovered_at > 30:
                try:
                    detected = discover_apps()
                except (OSError, ValueError, subprocess.SubprocessError):
                    raise HTTPException(503, 'Could not detect apps. Try again shortly.')
                self.detected = {app['id']: app for app in detected}
                self.discovered_at = time.monotonic()
            targets = {str(self.resolve_executable(app['target'])).casefold() for app in self.apps}
            processes = {app.get('process', '').casefold() for app in self.apps}
            return [{'id': app['id'], 'name': app['name']} for app in self.detected.values()
                    if app['id'] not in {a['id'] for a in self.apps} and app['target'].casefold() not in targets
                    and app['process'].casefold() not in processes]

    def _save(self, apps):
        if self.selection_path:
            try:
                self.selection_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.selection_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(apps, ensure_ascii=False), encoding='utf-8')
                temporary.replace(self.selection_path)
            except OSError:
                raise HTTPException(503, 'Could not save app shortcuts. Your shortcuts are unchanged.')
        self.apps = apps

    def add(self, app_id):
        with self.lock:
            if len(self.apps) >= self.MAX_APPS:
                raise HTTPException(409, 'You can keep up to 25 apps. Remove one before adding another.')
            if time.monotonic() - self.discovered_at > 120 or app_id not in self.detected:
                raise HTTPException(409, 'Refresh detected apps and choose an app from the list.')
            app = self.detected[app_id]
            if executable_path(app['target']) is None:
                raise HTTPException(409, 'This app is no longer installed. Refresh detected apps.')
            if any(a['id'] == app_id or str(self.resolve_executable(a['target'])).casefold() == app['target'].casefold()
                   or a.get('process', '').casefold() == app['process'].casefold()
                   for a in self.apps):
                raise HTTPException(409, 'This app is already in your shortcuts.')
            self._save([*self.apps, dict(app)])
            return self.catalog()

    def remove(self, app_id):
        with self.lock:
            if app_id not in {app['id'] for app in self.apps}:
                raise HTTPException(404, 'This app shortcut was already removed.')
            self._save([app for app in self.apps if app['id'] != app_id])
            return self.catalog()

    def catalog(self):
        processes = set()
        for process in psutil.process_iter(["name"]):
            try:
                processes.add((process.info["name"] or "").lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        with self.lock:
            apps = list(self.apps)
        return [{key: value for key, value in app.items() if key not in {"target", "args"}} |
                {"running": app.get("process", "").lower() in processes,
                 "available": self.available(app)} for app in apps]

    @staticmethod
    def resolve_executable(target):
        resolved = shutil.which(target)
        if resolved:
            return resolved
        if target.lower() == 'brave.exe':
            # Trusted alias; never resolve a client-supplied path or URL.
            for folder in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
                base = os.environ.get(folder)
                if base:
                    candidate = Path(base) / 'BraveSoftware/Brave-Browser/Application/brave.exe'
                    if candidate.is_file():
                        return str(candidate)
        return target

    @staticmethod
    def available(app):
        target = app["target"]
        # A registered URI's handler is checked by Windows at launch time.
        return target.startswith(URI_PREFIXES) or Path(AppRegistry.resolve_executable(target)).is_file()

    def launch(self, app_id: str):
        app = next((app for app in self.apps if app["id"] == app_id), None)
        if not app:
            raise HTTPException(404, "This application is not registered.")
        if os.name != "nt":
            raise HTTPException(501, "Application launching requires Windows.")
        try:
            target = app["target"]
            if target.startswith(URI_PREFIXES):
                os.startfile(target)
            else:
                executable = self.resolve_executable(target)
                if not Path(executable).is_file():
                    raise FileNotFoundError
                subprocess.Popen([executable, *app.get("args", [])],
                                 cwd=str(Path(executable).parent), shell=False)
        except OSError:
            raise HTTPException(409, f"{app['name']} could not be opened. Check its installation and local configuration.")
        return {"ok": True, "message": f"Opening {app['name']}"}


def media_action(action: str):
    if action not in MEDIA_KEYS:
        raise HTTPException(404, "Unknown media control.")
    if os.name != "nt":
        raise HTTPException(501, "Media controls require Windows.")
    user32 = ctypes.windll.user32
    user32.keybd_event(MEDIA_KEYS[action], 0, 0, 0)
    user32.keybd_event(MEDIA_KEYS[action], 0, 2, 0)
    return {"ok": True, "message": "Media control sent"}
