"""Remember explicitly approved browsers using hashed, revocable credentials."""
import hashlib
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import HTTPException

DEVICE_TTL = 180 * 86400
PENDING_TTL = 600
COOKIE = 'g16_device'


class DeviceStore:
    def __init__(self, database=':memory:'):
        if str(database) != ':memory:':
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, credential_hash TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, address TEXT NOT NULL, role TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL,
                expires REAL NOT NULL, last_seen REAL NOT NULL)''')

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def public(row):
        if row is None:
            return None
        device = {key: row[key] for key in row.keys() if key != 'credential_hash'}
        device['fingerprint'] = device['id'][:8].upper()
        if device['expires'] <= time.time() and device['status'] != 'revoked':
            device['status'] = 'expired'
        return device

    def create(self, name, address, owner=False):
        now = time.time()
        with self.lock, self.db:
            self.db.execute("DELETE FROM devices WHERE status='pending' AND expires < ?", (now,))
            count = self.db.execute("SELECT count(*) FROM devices WHERE status='pending'").fetchone()[0]
            if count >= 64 and not owner:
                raise HTTPException(429, 'Too many pending device requests.')
            token = secrets.token_urlsafe(32)
            device_id = secrets.token_hex(16)
            self.db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?,?,?)',
                            (device_id, self.digest(token), name, address,
                             'owner' if owner else 'device', 'approved' if owner else 'pending',
                             now, now + (DEVICE_TTL if owner else PENDING_TTL), now))
        return token, self.lookup(token)

    def lookup(self, token):
        if not token or len(token) > 128:
            return None
        with self.lock:
            row = self.db.execute('SELECT * FROM devices WHERE credential_hash=?',
                                  (self.digest(token),)).fetchone()
            return self.public(row)

    def valid(self, token):
        device = self.lookup(token)
        return device if device and device['status'] == 'approved' else None

    def list(self):
        with self.lock:
            return [self.public(row) for row in self.db.execute('SELECT * FROM devices ORDER BY created DESC')]

    def approve(self, device_id):
        with self.lock, self.db:
            cursor = self.db.execute("UPDATE devices SET status='approved',expires=? WHERE id=? AND status='pending' AND expires>?",
                                     (time.time() + DEVICE_TTL, device_id, time.time()))
            if not cursor.rowcount:
                raise HTTPException(409, 'This request expired or is no longer pending.')

    def revoke(self, device_id):
        with self.lock, self.db:
            cursor = self.db.execute("UPDATE devices SET status='revoked' WHERE id=?", (device_id,))
            if not cursor.rowcount:
                raise HTTPException(404, 'Device not found.')

    def touch(self, token):
        with self.lock, self.db:
            self.db.execute('UPDATE devices SET last_seen=? WHERE credential_hash=? AND last_seen<?',
                            (time.time(), self.digest(token), time.time() - 60))
