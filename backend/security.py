"""Pair a local browser without putting credentials in URLs or browser storage."""
import secrets
import time
import threading
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class Pairing:
    def __init__(self, code: str):
        self.code = code
        self.attempts = defaultdict(deque)
        self.lock = threading.Lock()

    def limit(self, address):
        with self.lock:
            now = time.monotonic()
            if len(self.attempts) >= 1024:
                self.attempts = defaultdict(deque, {ip: attempts for ip, attempts in self.attempts.items()
                                                   if attempts and attempts[-1] > now - 60})
                if address not in self.attempts and len(self.attempts) >= 1024:
                    raise HTTPException(429, 'Too many requests. Wait a minute.')
            attempts = self.attempts[address]
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 5:
                raise HTTPException(429, 'Too many attempts. Wait a minute.')
            attempts.append(now)

    def verify(self, code: str, address: str):
        self.limit(address)
        if not secrets.compare_digest(code.upper(), self.code):
            raise HTTPException(401, "Pairing code is incorrect.")

def same_origin(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def require_origin(request: Request):
    if not same_origin(request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(403, "Use the dashboard on this server to send controls.")
