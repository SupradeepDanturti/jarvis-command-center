"""Bounded conversation text in the existing private laptop state directory."""
import json
from pathlib import Path
import sqlite3
import threading
import time

from .agent.voice_actions import safe_sources


class VoiceHistory:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else None
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(Path(directory) / 'history.sqlite3') if directory else ':memory:',
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('CREATE TABLE IF NOT EXISTS exchanges (id INTEGER PRIMARY KEY, created REAL NOT NULL, '
                        'heard TEXT NOT NULL, reply TEXT NOT NULL, action TEXT, sources TEXT)')
        if 'sources' not in {row[1] for row in self.db.execute('PRAGMA table_info(exchanges)')}:
            self.db.execute('ALTER TABLE exchanges ADD COLUMN sources TEXT')
        if 'kind' not in {row[1] for row in self.db.execute('PRAGMA table_info(exchanges)')}:
            self.db.execute("ALTER TABLE exchanges ADD COLUMN kind TEXT NOT NULL DEFAULT 'conversation'")
        self.db.commit()

    def add(self, heard, reply, action=None, sources=None, kind='conversation'):
        detail = json.dumps(action) if action else None
        if detail and len(detail) > 2000:
            detail = json.dumps({'name': action.get('name', '')[:60], 'ok': False, 'message': 'Action detail unavailable.'})
        with self.lock, self.db:
            self.db.execute('INSERT INTO exchanges(created,heard,reply,action,sources,kind) VALUES(?,?,?,?,?,?)',
                            (time.time(), str(heard)[:1000], str(reply)[:500],
                             detail, json.dumps(safe_sources(sources)), kind if kind in {'alert', 'personal', 'memory'} else 'conversation'))
            self.db.execute('DELETE FROM exchanges WHERE id NOT IN (SELECT id FROM exchanges ORDER BY id DESC LIMIT 500)')

    def recent(self, limit=50, before=None, personal=True):
        with self.lock:
            rows = self.db.execute("SELECT * FROM exchanges WHERE (? IS NULL OR id < ?) AND (? OR kind NOT IN ('personal','memory')) ORDER BY id DESC LIMIT ?",
                                   (before, before, personal, max(1, min(50, limit)))).fetchall()
            return [{**dict(row), 'action': json.loads(row['action']) if row['action'] else None,
                     'sources': safe_sources(json.loads(row['sources'])) if row['sources'] else []} for row in reversed(rows)]

    def context(self, personal=False, memory=False):
        with self.lock:
            rows = self.db.execute("SELECT heard,reply FROM exchanges WHERE kind='conversation' OR (? AND kind='personal') OR (? AND kind='memory') ORDER BY id DESC LIMIT 6", (personal, memory)).fetchall()
            return [message for row in reversed(rows) for message in
                    ({'role': 'user', 'content': row['heard']}, {'role': 'assistant', 'content': row['reply']})]

    def clear(self):
        with self.lock, self.db:
            self.db.execute('DELETE FROM exchanges')
