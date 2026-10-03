import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .controllers import AppRegistry, media_action
from .devices import COOKIE, DEVICE_TTL, PENDING_TTL, DeviceStore
from .security import Pairing, require_origin, same_origin
from .telemetry import Telemetry

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


def create_app(pairing_code=None, device_db=None):
    state_dir = ROOT / '.state/private'
    code = pairing_code or secrets.token_hex(4).upper()
    pairing = Pairing(code)
    devices = DeviceStore(device_db or (':memory:' if pairing_code else state_dir / 'devices.sqlite3'))
    telemetry = Telemetry()
    registry = AppRegistry()

    @asynccontextmanager
    async def lifespan(app):
        if not pairing_code:
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "pairing-code.txt").write_text(code, encoding="utf-8")
        task = asyncio.create_task(telemetry.run())
        print(f"\nG16 Command Center | Laptop setup code: {code}\nApproved browsers are remembered for 180 days, including across restarts.\n", flush=True)
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="G16 Command Center", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.pairing = pairing
    app.state.telemetry = telemetry
    app.state.registry = registry
    app.state.devices = devices

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
        return devices.list()

    @app.post('/api/devices/{device_id}/approve', dependencies=[Depends(owner), Depends(require_origin)])
    def approve(device_id: str):
        devices.approve(device_id)
        return {'ok': True}

    @app.post('/api/devices/{device_id}/revoke', dependencies=[Depends(owner), Depends(require_origin)])
    def revoke(device_id: str):
        devices.revoke(device_id)
        return {'ok': True}

    @app.post("/api/logout", dependencies=[Depends(authenticate), Depends(require_origin)])
    def logout(request: Request, response: Response):
        device = devices.lookup(request.cookies.get(COOKIE))
        devices.revoke(device['id'])
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

    @app.post("/api/media/{action}", dependencies=[Depends(authenticate), Depends(require_origin)])
    def media(action: str):
        return media_action(action)

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        if not devices.valid(ws.cookies.get(COOKIE)) or not same_origin(ws.headers.get("origin"), ws.headers.get("host")) or (ws.client.host not in {'127.0.0.1', '::1'} and ws.url.scheme != 'wss'):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while devices.valid(ws.cookies.get(COOKIE)):
                await ws.send_json({"type": "telemetry", "data": telemetry.latest, "errors": telemetry.errors})
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
