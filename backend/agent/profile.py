"""Owner-authored preferences in the bounded private conversation database."""
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    address: str = Field(default='sir', max_length=40, pattern=r'^[^\x00-\x1f\x7f]*$')
    timezone: str = Field(default='America/Toronto', min_length=1, max_length=80)
    tone: Literal['jarvis', 'plain'] = 'jarvis'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Choose a valid IANA timezone, such as America/Toronto.') from None
        return value


class ProfileStore:
    def __init__(self, history):
        self.history = history
        with history.lock, history.db:
            history.db.execute('CREATE TABLE IF NOT EXISTS assistant_profile '
                               '(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')

    def get(self):
        with self.history.lock:
            row = self.history.db.execute('SELECT data FROM assistant_profile WHERE id=1').fetchone()
            return Profile.model_validate_json(row['data']) if row else Profile()

    def save(self, profile):
        with self.history.lock, self.history.db:
            self.history.db.execute('INSERT OR REPLACE INTO assistant_profile(id,data) VALUES(1,?)',
                                    (json.dumps(profile.model_dump()),))
        return profile

    def clear(self):
        with self.history.lock, self.history.db:
            self.history.db.execute('DELETE FROM assistant_profile')
