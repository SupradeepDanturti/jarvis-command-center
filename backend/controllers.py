"""Trusted, laptop-side registrations only. No client-supplied executable or shell."""
import ctypes
import json
import ipaddress
import os
from pathlib import Path
import shutil
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import psutil
from fastapi import HTTPException
from .app_discovery import discover_apps, executable_path, package_available
from .app_icons import installed_icon

ROOT = Path(__file__).resolve().parents[1]
URI_PREFIXES = ("steam://", "discord://", "spotify:", "microsoft-edge:", "ms-settings:")
MEDIA_KEYS = {"volume-up": 0xAF, "volume-down": 0xAE, "mute": 0xAD,
              "play-pause": 0xB3, "next": 0xB0, "previous": 0xB1}


def website_url(url):
    """Canonical browser navigation only; never an OS protocol, command or authenticated URL."""
    if not isinstance(url, str) or not 1 <= len(url) <= 2048 or '\\' in url or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError('Use a complete HTTP or HTTPS website URL.')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or not parsed.hostname:
            raise ValueError()
        if parsed.username is not None or parsed.password is not None or '%' in parsed.hostname:
            raise ValueError()
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        if ':' in parsed.hostname:
            hostname = str(ipaddress.IPv6Address(parsed.hostname))
            authority = '[' + hostname + ']'
        else:
            hostname = parsed.hostname.encode('idna').decode('ascii').lower()
            domain = hostname[:-1] if hostname.endswith('.') else hostname
            if len(domain) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')):
                raise ValueError()
            authority = hostname
        if port is not None:
            authority += ':' + str(port)
        return urlunsplit((parsed.scheme, authority, parsed.path or '/', parsed.query, parsed.fragment)), hostname
    except (ValueError, UnicodeError):
        raise ValueError('Use a complete HTTP or HTTPS website URL without embedded credentials.') from None


def open_website(url):
    target, hostname = website_url(url)
    if os.name != 'nt':
        raise HTTPException(501, 'Website opening requires Windows.')
    executable = AppRegistry.resolve_executable('brave.exe')
    try:
        if not Path(executable).is_file():
            raise FileNotFoundError()
        subprocess.Popen([executable, '--new-tab', target], cwd=str(Path(executable).parent), shell=False)
    except OSError:
        raise HTTPException(409, 'The website could not be opened. Check that Brave is installed.') from None
    return {'ok': True, 'message': f'{hostname} opened in Brave.'}


class AppRegistry:
    MAX_APPS = 25

    def __init__(self, selection_path=None):
        self.lock = threading.RLock()
        self.selection_path = Path(selection_path) if selection_path else None
        self.detected = {}
        self.icons = {}
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
                    and (not app.get('process') or app['process'].casefold() not in processes)]

    def _save(self, apps):
        if self.selection_path:
            try:
                self.selection_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.selection_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(apps, ensure_ascii=False), encoding='utf-8')
                for attempt in range(5):
                    try:
                        temporary.replace(self.selection_path)
                        break
                    except OSError as error:
                        # Windows scanners can briefly hold a newly written file.
                        if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 4:
                            raise
                        time.sleep(.025 * 2**attempt)
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
            if not (package_available(app) if app.get('kind') == 'packaged' else executable_path(app['target'])):
                raise HTTPException(409, 'This app is no longer installed. Refresh detected apps.')
            if any(a['id'] == app_id or str(self.resolve_executable(a['target'])).casefold() == app['target'].casefold()
                   or (app.get('process') and a.get('process', '').casefold() == app['process'].casefold())
                   for a in self.apps):
                raise HTTPException(409, 'This app is already in your shortcuts.')
            self._save([*self.apps, dict(app)])
            return self.catalog()

    def remove(self, app_id):
        with self.lock:
            if app_id not in {app['id'] for app in self.apps}:
                raise HTTPException(404, 'This app shortcut was already removed.')
            self._save([app for app in self.apps if app['id'] != app_id])
            self.icons.pop(app_id, None)
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
        return [{key: value for key, value in app.items() if key not in {"target", "args", "aumid", "packageRoot", "logo"}} |
                {"running": app.get("process", "").lower() in processes,
                 'artwork': f'/api/apps/{app["id"]}/artwork' if app.get('detected') else None,
                 "available": self.available(app)} for app in apps]

    def voice_catalog(self):
        """Available saved shortcuts plus the same bounded inventory as the Settings picker."""
        with self.lock:
            detected = self.discover()
            selected = [{'id': app['id'], 'name': app['name']} for app in self.apps if self.available(app)]
            return selected + [app for app in detected if self.available(self.detected[app['id']])]

    def launch_voice(self, app_id):
        # Discovery never registers a shortcut or persists a new launch capability.
        # Do not wait behind a Windows discovery while the voice parent holds its cancellation gate.
        if not self.lock.acquire(timeout=.25):
            raise HTTPException(503, 'Apps are being refreshed. Try again shortly.')
        try:
            app = next((app for app in self.apps if app['id'] == app_id), None)
            if app is None:
                if not self.discovered_at or time.monotonic() - self.discovered_at > 120:
                    raise HTTPException(409, 'Refresh available apps before opening an app.')
                app = self.detected.get(app_id)
                if app is None or app.get('args') or not (
                    package_available(app) if app.get('kind') == 'packaged' else executable_path(app['target'])
                ):
                    raise HTTPException(409, 'This application is not available. Refresh available apps.')
            if not self.available(app):
                raise HTTPException(409, 'This application is not available.')
            return self._launch(app)
        finally:
            self.lock.release()

    def artwork(self, app_id):
        with self.lock:
            app = next((a for a in self.apps if a['id'] == app_id and a.get('detected')), None)
            if not app:
                raise HTTPException(404, 'No icon for this app shortcut.')
            if app_id in self.icons:
                data = self.icons[app_id]
            else:
                try:
                    data = installed_icon(app)
                except (OSError, ValueError):
                    data = None
                self.icons[app_id] = data
            if not data:
                raise HTTPException(404, 'This app did not provide a local icon.')
            return data

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
        if app.get('kind') == 'packaged':
            return package_available(app)
        target = app["target"]
        # A registered URI's handler is checked by Windows at launch time.
        return target.startswith(URI_PREFIXES) or Path(AppRegistry.resolve_executable(target)).is_file()

    def launch(self, app_id: str):
        app = next((app for app in self.apps if app["id"] == app_id), None)
        if not app:
            raise HTTPException(404, "This application is not registered.")
        return self._launch(app)

    def _launch(self, app):
        if os.name != "nt":
            raise HTTPException(501, "Application launching requires Windows.")
        try:
            target = app["target"]
            if app.get('kind') == 'packaged':
                if not package_available(app):
                    raise FileNotFoundError
                os.startfile('shell:AppsFolder\\' + app['aumid'])
            elif target.startswith(URI_PREFIXES):
                os.startfile(target)
            else:
                executable = self.resolve_executable(target)
                if not Path(executable).is_file():
                    raise FileNotFoundError
                subprocess.Popen([executable, *app.get("args", [])],
                                 cwd=str(Path(executable).parent), shell=False)
        except OSError:
            raise HTTPException(409, f"{app['name']} could not be opened. Check its installation and local configuration.")
        return {"ok": True, "message": f"{app['name']} opened."}


def media_action(action: str):
    if action not in MEDIA_KEYS:
        raise HTTPException(404, "Unknown media control.")
    if os.name != "nt":
        raise HTTPException(501, "Media controls require Windows.")
    user32 = ctypes.windll.user32
    user32.keybd_event(MEDIA_KEYS[action], 0, 0, 0)
    user32.keybd_event(MEDIA_KEYS[action], 0, 2, 0)
    return {"ok": True, "message": "Media control sent"}
