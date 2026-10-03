"""Pair a local browser without putting credentials in URLs or browser storage."""
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class Pairing:
    def __init__(self, code: str):
        self.code = code
        self.sessions: dict[str, float] = {}
        self.attempts = defaultdict(deque)

    def valid(self, token: str | None) -> bool:
        now = time.time()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        return bool(token and token in self.sessions)

    def pair(self, code: str, address: str) -> str:
        now = time.monotonic()
        attempts = self.attempts[address]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(429, "Too many attempts. Wait a minute.")
        attempts.append(now)
        if not secrets.compare_digest(code.upper(), self.code):
            raise HTTPException(401, "Pairing code is incorrect.")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = time.time() + 43200
        return token


def same_origin(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def require_origin(request: Request):
    if not same_origin(request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(403, "Use the dashboard on this server to send controls.")
