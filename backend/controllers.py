"""Trusted, laptop-side registrations only. No client-supplied executable or shell."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess

import psutil
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
URI_PREFIXES = ("steam://", "discord://", "spotify:", "microsoft-edge:", "ms-settings:")
MEDIA_KEYS = {"volume-up": 0xAF, "volume-down": 0xAE, "mute": 0xAD,
              "play-pause": 0xB3, "next": 0xB0, "previous": 0xB1}


class AppRegistry:
    def __init__(self):
        path = ROOT / "config/apps.local.json"
        if not path.exists():
            path = ROOT / "config/apps.json"
        self.apps = json.loads(path.read_text(encoding="utf-8"))
        ids = [app["id"] for app in self.apps]
        if len(ids) != len(set(ids)):
            raise ValueError("Application IDs must be unique")

    def catalog(self):
        processes = set()
        for process in psutil.process_iter(["name"]):
            try:
                processes.add((process.info["name"] or "").lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return [{key: value for key, value in app.items() if key not in {"target", "args"}} |
                {"running": app.get("process", "").lower() in processes,
                 "available": self.available(app)} for app in self.apps]

    @staticmethod
    def available(app):
        target = app["target"]
        # A registered URI's handler is checked by Windows at launch time.
        return target.startswith(URI_PREFIXES) or Path(target).is_file() or shutil.which(target) is not None

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
                executable = shutil.which(target) or target
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
