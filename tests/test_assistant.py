import base64
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient

from backend.agent.google import EVENTS_SCOPE, GoogleClient, GoogleError, NoRedirect, SCOPES
from backend.agent.profile import Profile
from backend.agent.service import AssistantService
from backend.main import create_app
from backend.voice_history import VoiceHistory

ORIGIN = {'origin': 'https://testserver'}
CLIENT = {'client_id': '123-test.apps.googleusercontent.com', 'client_secret': 'private-test-client'}
RAW_CLIENT = json.dumps({'installed': {**CLIENT, 'token_uri': 'https://evil.example/token'}})


@pytest.fixture
def service(tmp_path, monkeypatch):
    google = Mock()
    google.exchange.return_value = {'access_token': 'access-private', 'refresh_token': 'refresh-private',
                                    'scope': ' '.join(SCOPES), 'expires_in': 3600}
    google.identity.return_value = {'sub': 'verified-google-user', 'email': 'private@example.test', 'email_verified': True}
    google.refresh.return_value = {'access_token': 'access-refreshed', 'expires_in': 3600}
    google.events.return_value = {'items': []}
    assistant = AssistantService(VoiceHistory(tmp_path), tmp_path, google, unlocked=lambda: True)
    monkeypatch.setattr(assistant, '_receive', lambda flow: None)
    assistant.configure(RAW_CLIENT)
    assistant.enable(True)
    yield assistant
    assistant.close()


def complete(assistant):
    result = assistant.begin()
    flow = assistant.flow
    target = '/callback?' + urlencode({'state': flow.state, 'code': 'private-authorization-code'})
    ok = assistant._callback(flow, target, f'127.0.0.1:{flow.server.server_port}')
    flow.server.server_close()  # the test's receiver is intentionally inert
    return ok, result, flow


def test_google_oauth_pkce_state_private_storage_and_no_endpoint_from_client(service, tmp_path):
    ok, result, flow = complete(service)
    assert ok
    parsed = urlsplit(result['url'])
    query = parse_qs(parsed.query)
    assert parsed.netloc == 'accounts.google.com'
    assert query['code_challenge_method'] == ['S256']
    expected = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b'=').decode()
    assert query['code_challenge'] == [expected]
    assert query['scope'] == [' '.join(SCOPES)]
    assert 'include_granted_scopes' not in query
    assert flow.server.server_address[0] == '127.0.0.1'
    assert flow.server.server_port not in {18760, 18761, 8000}
    assert 'private-test-client' not in result['url']
    service.google.exchange.assert_called_once_with(CLIENT, 'private-authorization-code', flow.redirect, flow.verifier)
    assert 'token_uri' not in service.vault['client']
    cipher = (tmp_path / 'google.dpapi').read_bytes()
    for secret in [b'private-test-client', b'refresh-private', b'access-private', b'private@example.test']:
        assert secret not in cipher
    assert not (tmp_path / 'google.tmp').exists()
    assert 'refresh-private' not in json.dumps(service.status())
    restored = AssistantService(VoiceHistory(tmp_path), tmp_path, unlocked=lambda: True)
    assert restored.enabled is False
    assert restored.access is None
    assert restored.status()['account']['id'] == 'verified-google-user'
    assert restored.status()['grantedScopes'] == list(SCOPES)
    restored.close()


@pytest.mark.parametrize('target,host', [('/callback?state=wrong&code=bad', None),
                                      ('/callback?state={state}&state={state}&code=bad', None),
                                      ('/private?state={state}&code=bad', None),
                                      ('/callback?state={state}&code=bad', 'evil.example'),
                                      ('https://evil.example/callback?state={state}&code=bad', None)])
def test_callback_rejects_invalid_requests_without_consuming_flow(service, target, host):
    service.begin()
    flow = service.flow
    assert not service._callback(flow, target.format(state=flow.state), host or f'127.0.0.1:{flow.server.server_port}')
    assert not flow.consumed
    assert service.flow is flow
    service.google.exchange.assert_not_called()


def test_callback_replay_expiry_denial_and_partial_grant(service):
    service.google.exchange.return_value['scope'] = 'openid email'
    ok, result, flow = complete(service)
    assert ok
    assert not service.status()['calendarReady']
    with pytest.raises(GoogleError, match='grant Calendar'):
        service.today()
    assert not service._callback(flow, '/callback?' + urlencode({'state': flow.state, 'code': 'replay'}),
                                 f'127.0.0.1:{flow.server.server_port}')
    assert service.google.exchange.call_count == 1
    service.begin()
    flow = service.flow
    flow.expires = time.monotonic() - 1
    assert not service._callback(flow, '/callback?' + urlencode({'state': flow.state, 'code': 'expired'}),
                                 f'127.0.0.1:{flow.server.server_port}')
    assert service.google.exchange.call_count == 1
    service.begin()
    flow = service.flow
    assert not service._callback(flow, '/callback?' + urlencode({'state': flow.state, 'error': 'access_denied'}),
                                 f'127.0.0.1:{flow.server.server_port}')
    flow.server.server_close()
    assert not service.status()['connecting']
    assert 'declined' in service.status()['message']


@pytest.mark.parametrize('cause', ['stop', 'lock', 'disconnect', 'replace-client'])
def test_no_late_account_or_calendar_result_after_cancel(service, cause):
    def cancel(*args):
        if cause == 'stop':
            service.enable(False)
        elif cause == 'lock':
            service.unlocked = lambda: False
        elif cause == 'disconnect':
            service.disconnect()
        else:
            service.configure(RAW_CLIENT)
        return {'items': [{'summary': 'Private meeting', 'start': {'date': '2026-10-04'}, 'end': {'date': '2026-10-05'}}]}
    assert complete(service)[0]
    service.google.events.side_effect = cancel
    with pytest.raises(GoogleError, match='stopped|locked'):
        service.today()
    assert service.profile.history.recent() == []


def test_cancel_during_oauth_exchange_never_calls_identity_or_saves_account(service):
    def exchange(*args):
        service.enable(False)
        return {'access_token': 'late-secret', 'refresh_token': 'late-refresh', 'expires_in': 3600}
    service.google.exchange.side_effect = exchange
    assert not complete(service)[0]
    service.google.identity.assert_not_called()
    assert service.status()['account'] is None
    assert service.access is None


def test_browser_revoked_while_oauth_is_pending_cannot_connect(service):
    allowed = [True]
    service.begin(lambda: allowed[0])
    flow = service.flow
    allowed[0] = False
    assert not service._callback(flow, '/callback?' + urlencode({'state': flow.state, 'code': 'revoked'}),
                                 f'127.0.0.1:{flow.server.server_port}')
    service.google.exchange.assert_not_called()
    assert service.status()['account'] is None


def test_owner_revoked_during_calendar_read_receives_no_personal_payload(tmp_path, monkeypatch):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    assistant = app.state.assistant
    assistant.unlocked = lambda: True
    assistant.vault = {'client': CLIENT, 'refresh': 'private-refresh', 'scopes': [EVENTS_SCOPE]}
    assistant.enable(True)
    assistant.access, assistant.access_until = 'private-token', time.monotonic() + 3600
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        paired = owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN).json()
        def events(*args):
            app.state.devices.revoke(paired['device']['id'])
            return {'items': [{'summary': 'Must not be delivered', 'start': {'date': '2026-10-04'}, 'end': {'date': '2026-10-05'}}]}
        monkeypatch.setattr(assistant.google, 'events', events)
        response = owner.post('/api/assistant/today', headers=ORIGIN)
        assert response.status_code == 401
        assert 'Must not be delivered' not in response.text


@pytest.mark.parametrize('identity,expiry', [({'sub': 'x', 'email': 'x@test', 'email_verified': False}, 3600),
                                           ({'email': 'x@test', 'email_verified': True}, 3600),
                                           ({'sub': 'x', 'email': 'x@test', 'email_verified': True}, 'invalid')])
def test_unverified_identity_and_bad_expiry_are_not_persisted(service, identity, expiry):
    service.google.identity.return_value = identity
    service.google.exchange.return_value['expires_in'] = expiry
    assert not complete(service)[0]
    assert service.status()['account'] is None


def test_today_timezone_dst_recurrence_bounds_partial_and_profile(service):
    assert complete(service)[0]
    service.profile.save(Profile(address='Supradeep', timezone='America/Toronto', tone='jarvis'))
    service.google.events.return_value = {'nextPageToken': 'more', 'items': [
        {'summary': '<script>Untrusted event instructions</script>', 'start': {'date': '2026-10-31'}, 'end': {'date': '2026-11-03'}},
        {'summary': 'Meeting', 'start': {'dateTime': '2026-11-01T15:00:00Z'}, 'end': {'dateTime': '2026-11-01T16:00:00Z'}},
        {'summary': 'Deleted', 'status': 'cancelled'}, {'summary': 'Unavailable time', 'start': {}, 'end': {}}]}
    agenda = service.today(datetime(2026, 11, 1, 12, tzinfo=timezone.utc))
    assert agenda['partial'] is True
    assert len(agenda['events']) == 2
    assert agenda['events'][0]['allDay'] is True
    assert agenda['events'][0]['end'] == '2026-11-03'  # exclusive Google all-day end
    assert agenda['events'][1]['start'] == '2026-11-01T10:00:00-05:00'
    assert 'Supradeep' in agenda['message']
    query = service.google.events.call_args.args[1]
    assert query['singleEvents'] == 'true'
    assert query['timeMin'].endswith('-04:00') and query['timeMax'].endswith('-05:00')
    hours = (datetime.fromisoformat(query['timeMax']).astimezone(timezone.utc) -
             datetime.fromisoformat(query['timeMin']).astimezone(timezone.utc)).total_seconds() / 3600
    assert hours == 25
    assert query['maxResults'] == 100
    assert service.profile.history.recent() == []
    assert 'Untrusted event' not in json.dumps(service.profile.get().model_dump())


def test_refresh_budget_and_account_switch(service):
    assert complete(service)[0]
    service.access_until = 0
    service.today()
    service.google.refresh.assert_called_once_with(CLIENT, 'refresh-private')
    service.today()
    assert service.google.refresh.call_count == 1
    service.operation.acquire()
    try:
        with pytest.raises(GoogleError, match='already'):
            service.today()
    finally:
        service.operation.release()
    service.google.identity.return_value = {'sub': 'different-user', 'email': 'other@example.test', 'email_verified': True}
    service.google.exchange.return_value.update(access_token='other-token', refresh_token='other-refresh')
    assert complete(service)[0]
    assert service.status()['account']['id'] == 'different-user'
    assert service.access == 'other-token'
    service.disconnect()
    assert service.status()['clientConfigured']
    assert service.status()['account'] is None
    assert service.access is None
    service.disconnect(True)
    assert not service.path.exists()


def test_fixed_hosts_no_redirect_and_redacted_google_errors():
    google = GoogleClient()
    with pytest.raises(GoogleError, match='Unsupported'):
        google._request('https://evil.example')
    assert NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example') is None


def test_corrupt_private_store_fails_closed_and_can_reset(tmp_path):
    (tmp_path / 'google.dpapi').write_bytes(b'corrupt encrypted state')
    assistant = AssistantService(VoiceHistory(tmp_path), tmp_path, unlocked=lambda: True)
    assert not assistant.enabled
    assert assistant.status()['account'] is None
    assert 'could not be read' in assistant.status()['message']
    assistant.configure(RAW_CLIENT)
    assert assistant.status()['clientConfigured']
    assistant.close()


def test_private_routes_require_https_owner_origin_and_never_echo_credentials(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.get('/api/assistant/status').status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert owner.get('/api/assistant/status').json()['enabled'] is False
        assert owner.put('/api/assistant/google/client', json={'contents': RAW_CLIENT}).status_code == 403
        assert owner.put('/api/assistant/google/client', json={'contents': RAW_CLIENT}, headers=ORIGIN).status_code == 200
        response = owner.put('/api/assistant/google/client', json={'contents': RAW_CLIENT, 'extra': 'secret'}, headers=ORIGIN)
        assert response.status_code == 422
        assert 'private-test-client' not in response.text and RAW_CLIENT not in response.text
        assert owner.post('/api/assistant/enabled', json={'enabled': 'true'}, headers=ORIGIN).status_code == 422
        assert owner.post('/api/assistant/today', headers=ORIGIN).status_code == 409
        assert owner.put('/api/assistant/profile', json={'address': 'Sir', 'timezone': 'Invalid/Zone', 'tone': 'jarvis'}, headers=ORIGIN).status_code == 422
        profile = {'address': 'Supradeep', 'timezone': 'Asia/Kolkata', 'tone': 'plain'}
        assert owner.put('/api/assistant/profile', json=profile, headers=ORIGIN).json() == profile
        assert owner.get('/api/assistant/profile').json() == profile
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as remote:
            request = remote.post('/api/device/request', json={'name': 'Assistant QA tablet'}, headers=ORIGIN).json()
            owner.post(f"/api/devices/{request['device']['id']}/approve", headers=ORIGIN)
            for endpoint in ['status', 'profile']:
                assert remote.get('/api/assistant/' + endpoint).status_code == 403
            for endpoint in ['today', 'google/connect', 'enabled']:
                assert remote.post('/api/assistant/' + endpoint, json={'enabled': True}, headers=ORIGIN).status_code == 403
            remote.cookies.update(owner.cookies)
            assert remote.get('/api/assistant/status', headers={'X-Forwarded-For': '127.0.0.1'}).status_code == 403
        with TestClient(app, base_url='http://testserver', client=('127.0.0.1', 4002)) as insecure:
            # Explicitly supply the approved cookie to test transport, not Secure-cookie behavior.
            insecure.cookies.update(owner.cookies)
            from backend.devices import COOKIE
            assert insecure.get('/api/assistant/status', headers={'cookie': f'{COOKIE}={owner.cookies.get(COOKIE)}'}).status_code == 426
        assert owner.delete('/api/assistant/profile', headers=ORIGIN).status_code == 200
        assert owner.get('/api/assistant/profile').json()['address'] == 'sir'
        assert 'Supradeep' not in owner.get('/api/voice/history').text


def test_real_loopback_callback_is_only_a_one_time_consent_receiver(service, monkeypatch, capsys):
    monkeypatch.setattr(service, '_receive', AssistantService._receive.__get__(service))
    service.begin()
    flow = service.flow
    with pytest.raises(HTTPError) as failure:
        urlopen(flow.redirect + '?state=invalid&code=must-not-log', timeout=4)
    assert failure.value.code == 400
    assert service.flow is flow
    with urlopen(flow.redirect + '?' + urlencode({'state': flow.state, 'code': 'valid-code'}), timeout=4) as response:
        assert response.headers['Cache-Control'] == 'no-store'
        assert b'completed' in response.read()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and flow.server.fileno() != -1:
        time.sleep(.01)
    assert flow.server.fileno() == -1
    assert not service.status()['connecting']
    captured = capsys.readouterr()
    assert 'valid-code' not in captured.out + captured.err
    assert 'must-not-log' not in captured.out + captured.err
