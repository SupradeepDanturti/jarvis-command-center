"""Bounded, inspectable personal facts; no raw provider mirrors or hidden memory file."""
import re
import time
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Fact(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=500, pattern=r'^[^\x00-\x1f\x7f]+$')

    @field_validator('text')
    @classmethod
    def no_known_secrets(cls, value):
        if re.search(r'(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY|(?:password|client_secret|refresh_token)\s*[:=])', value, re.I):
            raise ValueError('Keep credentials out of personal memory.')
        return value


class MemoryStore:
    def __init__(self, history):
        self.history = history
        with history.lock, history.db:
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_memory '
                               '(id TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL, '
                               'pending INTEGER NOT NULL, updated REAL NOT NULL)')
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_options '
                               '(id INTEGER PRIMARY KEY CHECK(id=1), cloud INTEGER NOT NULL)')

    def cloud(self):
        with self.history.lock:
            row = self.history.db.execute('SELECT cloud FROM assistant_options WHERE id=1').fetchone()
            return bool(row and row['cloud'])

    def set_cloud(self, enabled):
        with self.history.lock, self.history.db:
            self.history.db.execute('INSERT OR REPLACE INTO assistant_options VALUES(1,?)', (int(enabled),))

    def all(self):
        with self.history.lock:
            return [dict(row) for row in self.history.db.execute('SELECT * FROM assistant_memory ORDER BY updated DESC,id')]

    def save(self, value, identity=None, source='owner', pending=False):
        fact = Fact.model_validate({'text': value})
        with self.history.lock, self.history.db:
            if identity:
                if not self.history.db.execute('SELECT 1 FROM assistant_memory WHERE id=?', (identity,)).fetchone():
                    raise ValueError('This memory no longer exists.')
            else:
                duplicate = self.history.db.execute('SELECT id FROM assistant_memory WHERE text=? AND pending=?',
                                                    (fact.text, int(pending))).fetchone()
                if duplicate:
                    return duplicate['id']
                if self.history.db.execute('SELECT COUNT(*) FROM assistant_memory').fetchone()[0] >= 200:
                    raise ValueError('Memory is full. Forget a fact before adding another.')
            identity = identity or uuid.uuid4().hex
            self.history.db.execute('INSERT OR REPLACE INTO assistant_memory VALUES(?,?,?,?,?)',
                                    (identity, fact.text, source, int(pending), time.time()))
            return identity

    def delete(self, identity=None):
        with self.history.lock, self.history.db:
            if identity is None:
                self.history.db.execute('DELETE FROM assistant_memory')
            else:
                self.history.db.execute('DELETE FROM assistant_memory WHERE id=?', (identity,))

    def selected(self, query):
        words = set(re.findall(r'\w{3,}', query.lower()))
        rows = [row for row in self.all() if not row['pending']]
        # Bounded lexical retrieval, with recent facts to handle short follow-ups. No embeddings or cloud indexing.
        rows.sort(key=lambda row: (len(words & set(re.findall(r'\w{3,}', row['text'].lower()))), row['updated']), reverse=True)
        return rows[:20]


def explicit_fact(heard):
    if not isinstance(heard, str):
        return None
    command = re.sub(r'^(?:hey\s+)?jarvis[, :]+', '', heard.strip(), flags=re.I)
    match = re.fullmatch(r'(?:please )?remember (?:that )?(.{1,500})', command, flags=re.I)
    return match.group(1).strip() if match else None
