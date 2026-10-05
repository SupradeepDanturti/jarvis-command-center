"""Account-bound spreadsheet grants, discovery handles and reviewed RAW proposals."""
import json
import re
import secrets
import time

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def rectangle(value):
    match = re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_ ]{0,99}|'(?:[^'\x00-\x1f\x7f]|''){1,100}')!([A-Z]{1,3})([1-9][0-9]{0,6}):([A-Z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise ValueError('Use a bounded range such as Sheet1!A1:D20.')
    def column(name):
        number = 0
        for char in name:
            number = number * 26 + ord(char) - 64
        return number
    a, b, c, d = match.groups()
    width, height = column(c) - column(a) + 1, int(d) - int(b) + 1
    if width < 1 or height < 1 or width > 20 or height > 100 or width * height > 1000:
        raise ValueError('Choose at most 100 rows, 20 columns and 1,000 cells.')
    return height, width


class SheetRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60, pattern=r'^[^\x00-\x1f\x7f]+$')
    spreadsheetId: str = Field(min_length=10, max_length=150, pattern=r'^[A-Za-z0-9_-]+$')
    access: Literal['range', 'spreadsheet'] = 'range'
    range: str | None = Field(default=None, min_length=1, max_length=220)

    @field_validator('range')
    @classmethod
    def valid_range(cls, value):
        if value is not None:
            rectangle(value)
        return value

    @model_validator(mode='after')
    def valid_access(self):
        if (self.access == 'range') != (self.range is not None):
            raise ValueError('Choose an entire spreadsheet or one specific range.')
        return self


def target(sheet, area=None):
    """Resolve a request within its stored grant; never broaden a legacy range."""
    grant = SheetRegistration.model_validate({key: sheet[key] for key in ('name', 'spreadsheetId', 'range', 'access') if key in sheet})
    if grant.access == 'range':
        if area is not None and area != grant.range:
            raise ValueError('This registration only allows its saved range.')
        area = grant.range
    elif not isinstance(area, str):
        raise ValueError('Choose a bounded range within this spreadsheet first.')
    rectangle(area)
    return {**sheet, 'range': area}


def values(value, area):
    height, width = rectangle(area)
    if not isinstance(value, list) or not 1 <= len(value) <= height:
        raise ValueError('Provide rows within the registered range.')
    for row in value:
        if not isinstance(row, list) or len(row) > width:
            raise ValueError('Provide cells within the registered range.')
        for cell in row:
            if cell is not None and type(cell) not in {str, int, float, bool} or isinstance(cell, str) and (len(cell) > 500 or any(ord(c) < 32 and c not in '\n\t' for c in cell)):
                raise ValueError('Cells must contain bounded text, numbers or booleans.')
    if len(json.dumps(value, allow_nan=False)) > 20000:
        raise ValueError('The update is too large.')
    return value


class SheetStore:
    def __init__(self, history):
        self.history = history
        self.proposals = {}
        self.discovered = {}
        with history.lock, history.db:
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_sheets '
                               '(id TEXT PRIMARY KEY, account TEXT NOT NULL, data TEXT NOT NULL)')
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_sheet_access '
                               '(account TEXT PRIMARY KEY, enabled INTEGER NOT NULL)')

    def discovery_enabled(self, account):
        with self.history.lock:
            row = self.history.db.execute('SELECT enabled FROM assistant_sheet_access WHERE account=?', (account,)).fetchone()
            return bool(row and row['enabled'])

    def set_discovery(self, account, enabled):
        with self.history.lock, self.history.db:
            self.history.db.execute('INSERT INTO assistant_sheet_access VALUES(?,?) ON CONFLICT(account) DO UPDATE SET enabled=excluded.enabled', (account, int(enabled)))
        self.discovered.clear()

    def found(self, account, sheet, generation):
        self.discovered = {key: value for key, value in self.discovered.items() if value['expiresAt'] > time.time()}
        if len(self.discovered) >= 100:
            self.discovered.pop(next(iter(self.discovered)))
        identity = secrets.token_hex(16)
        self.discovered[identity] = {'account': account, 'generation': generation, 'expiresAt': time.time() + 300,
                                     'sheet': {'id': identity, **sheet}}
        return self.discovered[identity]['sheet']

    def resolve(self, account, identity, generation):
        registered = self.get(account, identity)
        if registered:
            return registered
        found = self.discovered.get(identity)
        if self.discovery_enabled(account) and found and found['account'] == account and found['generation'] == generation and found['expiresAt'] > time.time():
            return found['sheet']
        return None

    def all(self, account):
        with self.history.lock:
            return [{'id': row['id'], **json.loads(row['data'])} for row in self.history.db.execute(
                'SELECT id,data FROM assistant_sheets WHERE account=? ORDER BY id', (account,))]

    def register(self, account, body):
        with self.history.lock, self.history.db:
            if len(self.all(account)) >= 20:
                raise ValueError('At most twenty spreadsheets or ranges can be registered.')
            identity = secrets.token_hex(12)
            self.history.db.execute('INSERT INTO assistant_sheets VALUES(?,?,?)',
                                    (identity, account, json.dumps(body.model_dump())))
            return identity

    def get(self, account, identity):
        return next((row for row in self.all(account) if row['id'] == identity), None)

    def delete(self, account, identity):
        with self.history.lock, self.history.db:
            self.history.db.execute('DELETE FROM assistant_sheets WHERE account=? AND id=?', (account, identity))
        self.proposals.clear()

    def propose(self, sheet, value, generation):
        self.expire()
        if len(self.proposals) >= 10:
            raise ValueError('Review pending sheet changes before proposing more.')
        identity = secrets.token_hex(16)
        self.proposals[identity] = {'id': identity, 'sheet': sheet, 'values': values(value, sheet['range']),
                                    'generation': generation, 'expiresAt': time.time() + 300}
        return identity

    def expire(self):
        self.proposals = {key: value for key, value in self.proposals.items() if value['expiresAt'] > time.time()}
