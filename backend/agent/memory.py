"""Reviewed facts in a readable Markdown file, with legacy SQLite migration."""
import re
import time
import uuid
import json
import os
from pathlib import Path
import secrets

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
    def __init__(self, history, directory=None):
        self.history = history
        directory = directory or getattr(history, 'directory', None)
        self.directory = Path(directory) / 'memory' if directory else None
        with history.lock, history.db:
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_memory '
                               '(id TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL, '
                               'pending INTEGER NOT NULL, updated REAL NOT NULL)')
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_options '
                               '(id INTEGER PRIMARY KEY CHECK(id=1), cloud INTEGER NOT NULL)')
            if self.directory:
                prior = [dict(row) for row in history.db.execute('SELECT * FROM assistant_memory')]
                if prior:
                    current = self._entries()
                    identities = {row['id'] for row in current}
                    self._persist([*current, *(row for row in prior if row['id'] not in identities)])
                    # Persist and verify the Markdown copy before retiring legacy fact storage.
                    if {row['id'] for row in prior} <= {row['id'] for row in self._entries()}:
                        history.db.execute('DELETE FROM assistant_memory')

    def _path(self):
        if self.directory.is_symlink() or self.directory.is_junction():
            raise ValueError('Memory folder must be local.')
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / 'reviewed-facts.md'
        if path.is_symlink() or path.is_junction():
            raise ValueError('Memory file must be local.')
        return path

    def _entries(self):
        path = self._path()
        if not path.exists():
            return []
        if path.stat().st_size > 512000:
            raise ValueError('Reviewed memory file is too large.')
        lines = path.read_text(encoding='utf-8').splitlines()
        result = []
        for index, line in enumerate(lines):
            if not line.startswith('<!-- jarvis-fact: ') or not line.endswith(' -->'):
                continue
            if index+1 >= len(lines) or not lines[index+1].startswith('- '):
                raise ValueError('Reviewed memory metadata is incomplete.')
            metadata = json.loads(line[len('<!-- jarvis-fact: '):-4])
            if set(metadata) != {'id', 'source', 'pending', 'updated'} or not isinstance(metadata['id'], str):
                raise ValueError('Reviewed memory metadata is invalid.')
            result.append({**metadata, 'text': Fact.model_validate({'text': lines[index+1][2:]}).text})
        if len(result) > 200:
            raise ValueError('Reviewed memory exceeds two hundred facts.')
        return result

    def _persist(self, rows):
        if len(rows) > 200:
            raise ValueError('Memory is full. Forget a fact before adding another.')
        path = self._path()
        content = '# Reviewed facts\n\nManaged in Jarvis Memory. Agent-written topic files live beside this file.\n\n'
        for row in rows:
            content += '<!-- jarvis-fact: ' + json.dumps({key: row[key] for key in ('id', 'source', 'pending', 'updated')}, ensure_ascii=True) + ' -->\n- ' + row['text'] + '\n\n'
        temporary = path.parent / ('.reviewed-' + secrets.token_hex(12) + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8', newline='\n') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def cloud(self):
        with self.history.lock:
            row = self.history.db.execute('SELECT cloud FROM assistant_options WHERE id=1').fetchone()
            return bool(row and row['cloud'])

    def set_cloud(self, enabled):
        with self.history.lock, self.history.db:
            self.history.db.execute('INSERT OR REPLACE INTO assistant_options VALUES(1,?)', (int(enabled),))

    def all(self):
        with self.history.lock:
            if self.directory:
                return sorted(self._entries(), key=lambda row: (row['updated'], row['id']), reverse=True)
            return [dict(row) for row in self.history.db.execute('SELECT * FROM assistant_memory ORDER BY updated DESC,id')]

    def save(self, value, identity=None, source='owner', pending=False):
        fact = Fact.model_validate({'text': value})
        with self.history.lock, self.history.db:
            if self.directory:
                rows = self._entries()
                if identity and not any(row['id'] == identity for row in rows):
                    raise ValueError('This memory no longer exists.')
                if not identity:
                    duplicate = next((row for row in rows if row['text'] == fact.text and row['pending'] == int(pending)), None)
                    if duplicate:
                        return duplicate['id']
                identity = identity or uuid.uuid4().hex
                self._persist([*(row for row in rows if row['id'] != identity),
                               {'id': identity, 'text': fact.text, 'source': source, 'pending': int(pending), 'updated': time.time()}])
                return identity
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
            if self.directory:
                self._persist([row for row in self._entries() if identity is not None and row['id'] != identity])
                return
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
