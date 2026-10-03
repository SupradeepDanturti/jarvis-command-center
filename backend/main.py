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
from .security import Pairing, require_origin, same_origin
from .telemetry import Telemetry

ROOT = Path(__file__).resolve().parents[1]


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=8, max_length=8, pattern=r"^[A-Za-z0-9]{8}$")


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")


def create_app(pairing_code=None):
    state_dir = ROOT / ".state"
    code = pairing_code or secrets.token_hex(4).upper()
    pairing = Pairing(code)
    telemetry = Telemetry()
    registry = AppRegistry()

    @asynccontextmanager
    async def lifespan(app):
        if not pairing_code:
            state_dir.mkdir(exist_ok=True)
            (state_dir / "pairing-code.txt").write_text(code, encoding="utf-8")
        task = asyncio.create_task(telemetry.run())
        print(f"\nG16 Command Center | Pairing code: {code}\nSessions expire after 12 hours. Code changes on restart.\n", flush=True)
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="G16 Command Center", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.pairing = pairing
    app.state.telemetry = telemetry
    app.state.registry = registry

    def authenticate(request: Request):
        if not pairing.valid(request.cookies.get("g16_session")):
            raise HTTPException(401, "Pair this device to your laptop.")

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
        return {"ok": True, "version": "0.1.0"}

    @app.post("/api/pair", dependencies=[Depends(require_origin)])
    def pair(body: PairRequest, request: Request, response: Response):
        token = pairing.pair(body.code, request.client.host if request.client else "unknown")
        response.set_cookie("g16_session", token, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", max_age=43200)
        return {"ok": True}

    @app.post("/api/logout", dependencies=[Depends(authenticate), Depends(require_origin)])
    def logout(request: Request, response: Response):
        pairing.sessions.pop(request.cookies.get("g16_session"), None)
        response.delete_cookie("g16_session")
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
        if not pairing.valid(ws.cookies.get("g16_session")) or not same_origin(ws.headers.get("origin"), ws.headers.get("host")):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while pairing.valid(ws.cookies.get("g16_session")):
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
