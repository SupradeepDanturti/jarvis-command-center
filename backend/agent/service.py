"""Owner-only assistant foundation: installed OAuth, private profile, today's agenda."""
import base64
from dataclasses import dataclass, field
from datetime import datetime, time as day_time, timedelta
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ..tls import dpapi
from .google import AUTH_URL, EVENTS_SCOPE, SCOPES, GoogleClient, GoogleError
from .profile import ProfileStore


def desktop_unlocked():
    from ..voice_worker import desktop_unlocked as unlocked
    return unlocked()


def text(value, limit):
    return ''.join(c for c in str(value or '') if ord(c) >= 32 and ord(c) != 127)[:limit]


class ClientData(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    client_id: str = Field(min_length=1, max_length=255)
    client_secret: str = Field(min_length=1, max_length=300)


class AccountData(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=254)


class VaultData(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    client: ClientData | None = None
    account: AccountData | None = None
    refresh: str | None = Field(default=None, min_length=1, max_length=8192)
    scopes: list[str] = Field(default_factory=list, max_length=20)


@dataclass
class Flow:
    server: HTTPServer
    state: str
    verifier: str
    generation: int
    client: dict
    expires: float
    authorized: object = field(default=lambda: True)
    stop: threading.Event = field(default_factory=threading.Event)
    consumed: bool = False

    @property
    def redirect(self):
        return f'http://127.0.0.1:{self.server.server_port}/callback'


class AssistantService:
    def __init__(self, history, directory=None, google=None, unlocked=desktop_unlocked):
        self.profile = ProfileStore(history)
        self.directory = Path(directory) if directory else None
        self.google = google or GoogleClient()
        self.unlocked = unlocked
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.enabled = False
        self.generation = 0
        self.flow = None
        self.vault = {}
        self.access = None
        self.access_until = 0
        self.notice = ''
        if self.path and self.path.exists():
            try:
                if self.path.stat().st_size > 32768:
                    raise ValueError()
                vault = json.loads(dpapi(self.path.read_bytes(), decrypt=True))
                self.vault = VaultData.model_validate(vault).model_dump(exclude_none=True)
            except (OSError, ValueError, TypeError):
                self.notice = 'Saved Google connection could not be read. Import the client again to reset it.'

    @property
    def path(self):
        return self.directory / 'google.dpapi' if self.directory else None

    def _save(self, vault):
        if self.path:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            try:
                temporary.write_bytes(dpapi(json.dumps(vault).encode()))
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
        self.vault = vault

    def status(self):
        with self.lock:
            return {'enabled': self.enabled, 'clientConfigured': bool(self.vault.get('client')),
                    'account': self.vault.get('account'), 'grantedScopes': self.vault.get('scopes', []),
                    'calendarReady': EVENTS_SCOPE in self.vault.get('scopes', []),
                    'connecting': self.flow is not None, 'message': self.notice,
                    'services': {'calendar': 'read-only', 'gmail': 'planned', 'sheets': 'planned',
                                 'health': 'awaiting-google-access'}}

    def _cancel(self):
        self.generation += 1
        self.access = None
        self.access_until = 0
        if self.flow:
            self.flow.stop.set()
            self.flow.server.server_close()
            self.flow = None

    def enable(self, enabled):
        with self.lock:
            self._cancel()
            self.enabled = enabled
            self.notice = ''
        return self.status()

    def close(self):
        self.enable(False)

    def configure(self, raw):
        try:
            source = json.loads(raw)['installed']
            client = {key: source[key] for key in ('client_id', 'client_secret')}
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}\.apps\.googleusercontent\.com', client['client_id']):
                raise ValueError()
            if not isinstance(client['client_secret'], str) or not 1 <= len(client['client_secret']) <= 300 or any(ord(c) < 33 or ord(c) == 127 for c in client['client_secret']):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise GoogleError('Choose the downloaded Google Desktop app client JSON.', 400) from None
        with self.lock:
            self._cancel()
            self._save({'client': client})
            self.notice = 'Google client saved. You can connect your account now.'
        return self.status()

    def disconnect(self, remove_client=False):
        with self.lock:
            self._cancel()
            vault = {} if remove_client else {'client': self.vault.get('client')}
            if remove_client and self.path:
                self.path.unlink(missing_ok=True)
                self.vault = {}
            else:
                self._save(vault)
            self.notice = 'Google disconnected from this PC. Google account permissions remain until you remove them at Google.'
        return self.status()

    def _check(self, generation):
        if not self.enabled or generation != self.generation or not self.unlocked():
            raise GoogleError('Personal assistant access stopped or the PC was locked.', 409)

    def begin(self, authorized=lambda: True):
        with self.lock:
            self._check(self.generation)
            if not self.vault.get('client'):
                raise GoogleError('Import your Google Desktop client first.', 409)
            self._cancel()
            service = self

            class Callback(BaseHTTPRequestHandler):
                # Codes and state arrive here; suppress the HTTP server's access/error logs.
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    self.connection.settimeout(2)
                    flow = self.server.flow
                    ok = service._callback(flow, self.path, self.headers.get('Host'))
                    body = (b'Google connection completed. Return to Jarvis.' if ok else
                            b'Connection was not completed. Return to Jarvis and try again.')
                    self.send_response(200 if ok else 400)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
                    self.end_headers()
                    self.wfile.write(body)

            class Receiver(HTTPServer):
                def get_request(self):
                    connection, address = super().get_request()
                    connection.settimeout(2)
                    return connection, address

                def handle_error(self, request, client_address):
                    pass

            server = Receiver(('127.0.0.1', 0), Callback)
            server.timeout = .25
            flow = Flow(server, secrets.token_urlsafe(32), secrets.token_urlsafe(64), self.generation,
                        dict(self.vault['client']), time.monotonic() + 300, authorized)
            server.flow = flow
            self.flow = flow
            self.notice = 'Finish Google sign-in in your browser. This request expires in five minutes.'
            challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b'=').decode()
            url = AUTH_URL + '?' + urlencode({'client_id': flow.client['client_id'], 'redirect_uri': flow.redirect,
                                             'response_type': 'code', 'scope': ' '.join(SCOPES), 'state': flow.state,
                                             'code_challenge': challenge, 'code_challenge_method': 'S256',
                                             'access_type': 'offline', 'prompt': 'consent select_account'})
            threading.Thread(target=self._receive, args=(flow,), daemon=True, name='Google consent receiver').start()
            return {'url': url, 'expiresIn': 300}

    def _receive(self, flow):
        try:
            while not flow.stop.is_set() and time.monotonic() < flow.expires and self.unlocked() and flow.authorized():
                flow.server.handle_request()
        except (OSError, ValueError):
            pass
        finally:
            flow.server.server_close()
            with self.lock:
                if self.flow is flow:
                    self.flow = None
                    self.notice = 'Google sign-in expired or access stopped. Connect again.'

    def _check_flow(self, flow):
        self._check(flow.generation)
        if not flow.authorized() or time.monotonic() >= flow.expires:
            raise GoogleError('Google sign-in expired or browser access was revoked. Connect again.', 409)

    def _callback(self, flow, target, host):
        try:
            if len(target) > 8192 or host != f'127.0.0.1:{flow.server.server_port}':
                return False
            parsed = urlsplit(target)
            query = parse_qs(parsed.query, max_num_fields=20)
            if parsed.scheme or parsed.netloc or parsed.path != '/callback' or len(query.get('state', [])) != 1 or not secrets.compare_digest(query['state'][0], flow.state):
                return False
            with self.lock:
                self._check_flow(flow)
                if self.flow is not flow or flow.consumed or time.monotonic() >= flow.expires:
                    return False
                flow.consumed = True
            if len(query.get('code', [])) != 1 or 'error' in query or len(query['code'][0]) > 4096:
                raise GoogleError('Google sign-in was declined. You can connect again.', 409)
            tokens = self.google.exchange(flow.client, query['code'][0], flow.redirect, flow.verifier)
            self._check_flow(flow)
            token = self._token(tokens)
            access_until = self._expiry(tokens)
            identity = self.google.identity(token)
            if not isinstance(identity.get('sub'), str) or not identity['sub'] or len(identity['sub']) > 255 or identity.get('email_verified') is not True or not identity.get('email'):
                raise GoogleError('Google did not verify this account. Connect again.', 409)
            scopes = tokens.get('scope', '').split()
            if len(scopes) > 20 or any(len(scope) > 200 for scope in scopes):
                raise GoogleError()
            refresh = tokens.get('refresh_token')
            if not isinstance(refresh, str) or not 1 <= len(refresh) <= 8192:
                raise GoogleError('Google did not grant offline access. Remove Jarvis access at Google, then connect again.', 409)
            with self.lock:
                self._check_flow(flow)
                self._save({'client': flow.client, 'refresh': refresh, 'scopes': scopes,
                            'account': {'id': identity['sub'], 'email': text(identity['email'], 254)}})
                self.generation += 1  # invalidate every earlier account operation
                self.access, self.access_until = token, access_until
                self.notice = ('Google connected. Your primary calendar is ready.' if EVENTS_SCOPE in scopes else
                               'Google connected, but Calendar permission was not granted. Connect again to grant it.')
            return True
        except (GoogleError, ValueError, TypeError, AttributeError, OSError) as error:
            with self.lock:
                if self.flow is flow and flow.generation == self.generation:
                    self.notice = str(error) if isinstance(error, GoogleError) else 'Google connection could not be saved. Try again.'
            return False
        finally:
            if flow.consumed:
                flow.stop.set()
                with self.lock:
                    if self.flow is flow:
                        self.flow = None

    @staticmethod
    def _expiry(tokens):
        try:
            seconds = int(tokens['expires_in'])
            if seconds <= 0:
                raise ValueError()
            return time.monotonic() + max(0, min(3600, seconds) - 60)
        except (KeyError, ValueError, TypeError, OverflowError):
            raise GoogleError() from None

    @staticmethod
    def _token(tokens):
        token = tokens.get('access_token')
        if not isinstance(token, str) or not 1 <= len(token) <= 8192 or any(ord(c) < 33 or ord(c) == 127 for c in token):
            raise GoogleError()
        return token

    def _access(self, generation):
        with self.lock:
            self._check(generation)
            if self.flow:
                raise GoogleError('Finish or cancel Google sign-in first.', 409)
            if EVENTS_SCOPE not in self.vault.get('scopes', []) or not self.vault.get('refresh'):
                raise GoogleError('Connect Google and grant Calendar permission first.', 409)
            if self.access and time.monotonic() < self.access_until:
                return self.access
            client, refresh = dict(self.vault['client']), self.vault['refresh']
        tokens = self.google.refresh(client, refresh)
        token = self._token(tokens)
        access_until = self._expiry(tokens)
        with self.lock:
            self._check(generation)
            if 'scope' in tokens and EVENTS_SCOPE not in tokens['scope'].split():
                raise GoogleError('Calendar permission is no longer granted. Connect again.', 409)
            if tokens.get('refresh_token'):
                self._save({**self.vault, 'refresh': tokens['refresh_token']})
            self.access, self.access_until = token, access_until
            return token

    def today(self, now=None):
        # One bounded read at a time; no model sees this payload, and it is never persisted.
        if not self.operation.acquire(blocking=False):
            raise GoogleError('Your agenda is already being checked. Please wait.', 409)
        try:
            with self.lock:
                generation = self.generation
                self._check(generation)
                profile = self.profile.get()
            zone = ZoneInfo(profile.timezone)
            now = (now or datetime.now(zone)).astimezone(zone)
            start = datetime.combine(now.date(), day_time(), zone)
            end = datetime.combine(now.date() + timedelta(days=1), day_time(), zone)
            token = self._access(generation)
            query = {'timeMin': start.isoformat(), 'timeMax': end.isoformat(), 'timeZone': profile.timezone,
                     'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': 100,
                     'fields': 'nextPageToken,items(summary,start,end,status)'}
            self._check(generation)
            result = self.google.events(token, query)
            events, omitted = [], False
            for item in result.get('items', [])[:100]:
                if item.get('status') == 'cancelled':
                    continue
                begin, finish = item.get('start', {}), item.get('end', {})
                all_day = 'date' in begin
                try:
                    if all_day:
                        stamp, until = begin['date'], finish['date']
                        if datetime.strptime(until, '%Y-%m-%d') <= datetime.strptime(stamp, '%Y-%m-%d'):
                            raise ValueError()
                    else:
                        first = datetime.fromisoformat(begin['dateTime'])
                        last = datetime.fromisoformat(finish['dateTime'])
                        if first.tzinfo is None or last.tzinfo is None or last <= first:
                            raise ValueError()
                        stamp, until = first.astimezone(zone).isoformat(), last.astimezone(zone).isoformat()
                    events.append({'title': text(item.get('summary') or 'Busy', 200), 'start': stamp,
                                   'end': until, 'allDay': all_day})
                except (ValueError, KeyError, TypeError):
                    omitted = True
            partial = bool(result.get('nextPageToken')) or omitted
            count = len(events)
            address = f", {profile.address}" if profile.address and profile.tone == 'jarvis' else ''
            message = (f"Today's primary calendar checked{address}. " +
                       (f'{count} event' + ('s' if count != 1 else '') + ' found.' if count else 'No events found.'))
            if partial:
                message += ' This is a partial agenda; check Google Calendar for the complete day.'
            with self.lock:
                self._check(generation)
                return {'day': now.date().isoformat(), 'timezone': profile.timezone, 'events': events,
                        'partial': partial, 'message': message, 'checkedAt': time.time(), 'calendar': 'primary'}
        finally:
            self.operation.release()
