import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .controllers import AppRegistry, media_action
from .devices import COOKIE, DEVICE_TTL, PENDING_TTL, DeviceStore
from .display import DisplayReports
from .focus import FocusTimer
from .activity import ActivityMonitor
from .games import GameLibrary
from .media import MediaMonitor
from .security import Pairing, require_origin, same_origin
from .telemetry import Telemetry
from .voice import VoiceService, voice_router

ROOT = Path(__file__).resolve().parents[1]


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=8, max_length=8, pattern=r"^[A-Za-z0-9]{8}$")
    name: str = Field(default='My browser', min_length=1, max_length=60)


class DeviceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=60)


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")


class DisplayRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    width: int = Field(ge=1, le=16384, strict=True)
    height: int = Field(ge=1, le=16384, strict=True)
    visibleWidth: int = Field(ge=1, le=16384, strict=True)
    visibleHeight: int = Field(ge=1, le=16384, strict=True)
    scale: float = Field(gt=0, le=16)
    mode: Literal['Fullscreen', 'Normal browser']
    orientation: Literal['Landscape', 'Portrait']


class MediaSessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sessionId: str = Field(pattern=r'^[0-9a-f]{24}$')
    trackRevision: str = Field(pattern=r'^[0-9a-f]{24}$')
    action: Literal['play-pause', 'previous', 'next']


class SeekRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    sessionId: str = Field(pattern=r'^[0-9a-f]{24}$')
    trackRevision: str = Field(pattern=r'^[0-9a-f]{24}$')
    position: float = Field(ge=0, le=2592000)


class FocusCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['start', 'pause', 'resume', 'reset', 'skip']
    revision: int = Field(ge=0, le=2**53-1, strict=True)


class FocusSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=0, le=2**53-1)
    focus: int = Field(ge=1, le=180)
    short: int = Field(ge=1, le=180)
    long: int = Field(ge=1, le=180)
    announcements: bool


class ThermalSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool
    cpuTemperature: str | None = Field(default=None, pattern=r'^[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}$')
    cpuThrottle: str | None = Field(default=None, pattern=r'^[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}$')
    gpuThrottle: str | None = Field(default=None, pattern=r'^[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}$')
    fans: list[str] = Field(default_factory=list, max_length=16)
    drives: list[str] = Field(default_factory=list, max_length=16)


def create_app(pairing_code=None, device_db=None, voice_dir=None, focus_path=None):
    state_dir = ROOT / '.state/private'
    code = pairing_code or secrets.token_hex(4).upper()
    pairing = Pairing(code)
    devices = DeviceStore(device_db or (':memory:' if pairing_code else state_dir / 'devices.sqlite3'))
    telemetry = Telemetry(None if pairing_code else state_dir / 'thermal.json')
    registry = AppRegistry()
    games = GameLibrary()
    display_reports = DisplayReports()
    media_monitor = MediaMonitor()
    voice = VoiceService(voice_dir or (state_dir / 'voice' if not pairing_code else None), registry, telemetry)
    focus = FocusTimer(focus_path or (None if pairing_code else state_dir / 'focus.json'), notify=voice.remind)
    activity = ActivityMonitor(games)

    @asynccontextmanager
    async def lifespan(app):
        if not pairing_code:
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "pairing-code.txt").write_text(code, encoding="utf-8")
        task = asyncio.create_task(telemetry.run())
        media_task = asyncio.create_task(media_monitor.run())
        focus_task = asyncio.create_task(focus.run())
        activity_task = asyncio.create_task(activity.run())
        print(f"\nG16 Command Center | Laptop setup code: {code}\nApproved browsers are remembered for 180 days, including across restarts.\n", flush=True)
        yield
        await asyncio.to_thread(voice.stop)
        task.cancel()
        media_task.cancel()
        focus_task.cancel()
        activity_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(asyncio.CancelledError):
            await media_task
        with suppress(asyncio.CancelledError):
            await focus_task
        with suppress(asyncio.CancelledError):
            await activity_task

    app = FastAPI(title="G16 Command Center", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.pairing = pairing
    app.state.telemetry = telemetry
    app.state.registry = registry
    app.state.games = games
    app.state.devices = devices
    app.state.display_reports = display_reports
    app.state.media = media_monitor
    app.state.voice = voice
    app.state.focus = focus
    app.state.activity = activity

    def local(request):
        return request.client is not None and request.client.host in {'127.0.0.1', '::1'}

    def cookie(response, request, token, seconds=DEVICE_TTL):
        response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=seconds)

    def transport(request):
        if not local(request) and request.url.scheme != 'https':
            raise HTTPException(426, 'Use the HTTPS dashboard to connect devices.')

    def authenticate(request: Request):
        transport(request)
        device = devices.valid(request.cookies.get(COOKIE))
        if not device:
            raise HTTPException(401, 'This browser needs approval from your laptop.')
        devices.touch(request.cookies.get(COOKIE))
        return device

    def owner(request: Request, device=Depends(authenticate)):
        if not local(request) or device['role'] != 'owner':
            raise HTTPException(403, 'Manage devices from the approved laptop browser at localhost.')
        return device

    app.include_router(voice_router(voice, authenticate, owner))

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": "0.2.0"}

    @app.get('/api/auth')
    def auth_status(request: Request):
        transport(request)
        device = devices.lookup(request.cookies.get(COOKIE))
        return {'local': local(request), 'device': device,
                'owner': bool(local(request) and device and device['status'] == 'approved' and device['role'] == 'owner')}

    @app.post("/api/pair", dependencies=[Depends(require_origin)])
    def pair(body: PairRequest, request: Request, response: Response):
        transport(request)
        address = request.client.host if request.client else 'unknown'
        pairing.verify(body.code, address)
        token, device = devices.create(body.name.strip() or 'My browser', address, owner=local(request))
        cookie(response, request, token, DEVICE_TTL if local(request) else PENDING_TTL)
        response.delete_cookie('g16_session')
        return {'ok': True, 'device': device}

    @app.post('/api/device/request', dependencies=[Depends(require_origin)])
    def request_device(body: DeviceRequest, request: Request, response: Response):
        transport(request)
        existing = devices.lookup(request.cookies.get(COOKIE))
        if existing and existing['status'] in {'pending', 'approved'}:
            return {'device': existing}
        address = request.client.host if request.client else 'unknown'
        pairing.limit(address)
        token, device = devices.create(body.name.strip() or 'My browser', address)
        cookie(response, request, token, PENDING_TTL)
        return {'device': device}

    @app.post('/api/device/activate', dependencies=[Depends(authenticate), Depends(require_origin)])
    def activate(request: Request, response: Response):
        import time
        token = request.cookies.get(COOKIE)
        device = devices.valid(token)
        cookie(response, request, token, max(1, int(device['expires'] - time.time())))
        return {'ok': True, 'device': device}

    @app.get('/api/devices', dependencies=[Depends(owner)])
    def device_list():
        return [{**device, 'display': display_reports.get(device['id']) if device['status'] == 'approved' else None}
                for device in devices.list()]

    @app.post('/api/device/display', dependencies=[Depends(require_origin)])
    def report_display(body: DisplayRequest, device=Depends(authenticate)):
        display_reports.record(device['id'], body.model_dump())
        return {'ok': True}

    @app.post('/api/devices/{device_id}/approve', dependencies=[Depends(owner), Depends(require_origin)])
    def approve(device_id: str):
        devices.approve(device_id)
        return {'ok': True}

    @app.post('/api/devices/{device_id}/revoke', dependencies=[Depends(owner), Depends(require_origin)])
    def revoke(device_id: str):
        devices.revoke(device_id)
        display_reports.remove(device_id)
        return {'ok': True}

    @app.post("/api/logout", dependencies=[Depends(authenticate), Depends(require_origin)])
    def logout(request: Request, response: Response):
        device = devices.lookup(request.cookies.get(COOKIE))
        devices.revoke(device['id'])
        display_reports.remove(device['id'])
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/system", dependencies=[Depends(authenticate)])
    def system():
        if telemetry.latest is None:
            raise HTTPException(503, "Waiting for a hardware sample.")
        return telemetry.latest

    @app.get("/api/history", dependencies=[Depends(authenticate)])
    def history(seconds: int = Query(default=60, ge=30, le=3600)):
        cutoff = datetime.now(timezone.utc).timestamp() - seconds
        samples = [sample for sample in telemetry.history
                   if datetime.fromisoformat(sample["timestamp"]).timestamp() >= cutoff]
        # Bound response size while keeping the newest point.
        step = max(1, (len(samples) + 239) // 240)
        points = samples[::step]
        if samples and (not points or points[-1] is not samples[-1]):
            points.append(samples[-1])
        return {"seconds": seconds, "samples": points}

    @app.get("/api/apps", dependencies=[Depends(authenticate)])
    def apps():
        return registry.catalog()

    @app.post("/api/apps/launch", dependencies=[Depends(authenticate), Depends(require_origin)])
    def launch(body: LaunchRequest):
        return registry.launch(body.id)

    @app.post('/api/media/session-action', dependencies=[Depends(authenticate), Depends(require_origin)])
    async def session_action(body: MediaSessionRequest):
        return await media_monitor.command(body.sessionId, body.trackRevision, body.action)

    @app.post('/api/media/seek', dependencies=[Depends(authenticate), Depends(require_origin)])
    async def seek(body: SeekRequest):
        return await media_monitor.command(body.sessionId, body.trackRevision, 'seek', body.position)

    @app.get('/api/media/artwork/{revision}', dependencies=[Depends(authenticate)])
    async def media_artwork(revision: str):
        media_monitor.sample()
        if revision != media_monitor.revision or not media_monitor.artwork:
            raise HTTPException(404, 'Artwork unavailable.')
        data, mime = media_monitor.artwork
        return Response(data, media_type=mime)

    @app.post("/api/media/{action}", dependencies=[Depends(authenticate), Depends(require_origin)])
    def media(action: str):
        return media_action(action)

    @app.get('/api/media/state', dependencies=[Depends(authenticate)])
    async def media_state():
        return media_monitor.sample()

    @app.get('/api/focus', dependencies=[Depends(authenticate)])
    def focus_state():
        return focus.snapshot()

    @app.post('/api/focus/command', dependencies=[Depends(authenticate), Depends(require_origin)])
    def focus_command(body: FocusCommand):
        result = focus.command(body.action, body.revision)
        if body.action in {'start', 'resume', 'reset', 'skip'}:
            voice.cancel_reminder()
        return result

    @app.put('/api/focus/settings', dependencies=[Depends(authenticate), Depends(require_origin)])
    def focus_settings(body: FocusSettings):
        result = focus.command('settings', body.revision, body.model_dump(exclude={'revision'}))
        voice.cancel_reminder()
        return result

    @app.get('/api/thermals', dependencies=[Depends(authenticate)])
    def thermal_state():
        return telemetry.thermals.snapshot()

    @app.get('/api/thermals/inventory', dependencies=[Depends(owner)])
    def thermal_inventory():
        telemetry.thermals.sample()
        return telemetry.thermals.discovery()

    @app.put('/api/thermals/settings', dependencies=[Depends(owner), Depends(require_origin)])
    def thermal_settings(body: ThermalSettings):
        try:
            result = telemetry.thermals.configure(body.model_dump())
        except ValueError:
            raise HTTPException(422, 'Choose valid sensor identities.') from None
        return result

    @app.get('/api/games', dependencies=[Depends(authenticate)])
    def game_catalog():
        return app.state.games.catalog()

    @app.post('/api/games/refresh', dependencies=[Depends(authenticate), Depends(require_origin)])
    def refresh_games():
        return app.state.games.catalog(force=True)

    @app.post('/api/games/launch', dependencies=[Depends(authenticate), Depends(require_origin)])
    def launch_game(body: LaunchRequest):
        return app.state.games.launch(body.id)

    @app.get('/api/games/{game_id}/artwork', dependencies=[Depends(authenticate)])
    def game_artwork(game_id: str):
        return FileResponse(app.state.games.artwork(game_id))

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        if not devices.valid(ws.cookies.get(COOKIE)) or not same_origin(ws.headers.get("origin"), ws.headers.get("host")) or (ws.client.host not in {'127.0.0.1', '::1'} and ws.url.scheme != 'wss'):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while devices.valid(ws.cookies.get(COOKIE)):
                await ws.send_json({"type": "telemetry", "data": telemetry.latest, "errors": telemetry.errors,
                                    "media": media_monitor.latest, "focus": focus.snapshot(), "activity": activity.latest,
                                    "serverTime": datetime.now(timezone.utc).timestamp() * 1000})
                await asyncio.sleep(1)
            await ws.close(code=1008)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    @app.get("/")
    def index():
        return FileResponse(ROOT / "frontend/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
    return app


app = create_app()
