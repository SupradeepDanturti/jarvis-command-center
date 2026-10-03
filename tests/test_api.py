from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import create_app

ORIGIN = {"origin": "http://testserver"}


@pytest.fixture
def client():
    app = create_app(pairing_code="ABCD1234")
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        yield client


def paired(client):
    response = client.post('/api/pair', json={"code": "ABCD1234"}, headers=ORIGIN)
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']


def test_private_endpoints_require_pairing(client):
    for url in ['/api/system', '/api/apps', '/api/history']:
        assert client.get(url).status_code == 401
    assert client.post('/api/apps/launch', json={"id": "files"}, headers=ORIGIN).status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws', headers=ORIGIN):
            pass


def test_pairing_throttles_guesses(client):
    for _ in range(5):
        assert client.post('/api/pair', json={"code": "00000000"}, headers=ORIGIN).status_code == 401
    assert client.post('/api/pair', json={"code": "ABCD1234"}, headers=ORIGIN).status_code == 429


def test_cross_origin_requests_rejected(client):
    assert client.post('/api/pair', json={"code": "ABCD1234"}).status_code == 403
    paired(client)
    for origin in ['http://evil.example', 'http://testserver.evil.example', 'null']:
        assert client.post('/api/media/mute', headers={"origin": origin}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws', headers={"origin": origin}):
                pass


def test_no_arbitrary_launch_or_extra_parameters(client):
    paired(client)
    assert client.post('/api/apps/launch', json={"id": "not-registered"}, headers=ORIGIN).status_code == 404
    assert client.post('/api/apps/launch', json={"id": "files", "command": "calc.exe"}, headers=ORIGIN).status_code == 422
    assert client.post('/api/apps/launch', json={"id": "../cmd.exe"}, headers=ORIGIN).status_code == 422
    assert client.post('/api/media/shutdown', headers=ORIGIN).status_code == 404
    with patch('backend.controllers.subprocess.Popen') as launch:
        assert client.post('/api/apps/launch', json={"id": "files"}, headers=ORIGIN).status_code == 200
        assert launch.call_args.kwargs['shell'] is False
        assert launch.call_args.args[0][0].lower().endswith('explorer.exe')


def test_live_websocket_and_logout_revocation(client):
    paired(client)
    client.app.state.telemetry.latest = client.app.state.telemetry.sample()
    with client.websocket_connect('/ws', headers=ORIGIN) as ws:
        data = ws.receive_json()
        assert data['type'] == 'telemetry'
        assert data['data']['source'] == 'live'
        assert data['data']['cpu']['temperature'] is None
        assert data['data']['memory']['total'] > 0
    assert client.post('/api/logout', headers=ORIGIN).status_code == 200
    assert client.get('/api/apps').status_code == 401


def test_history_bounded_and_catalog_hides_targets(client):
    paired(client)
    now = datetime.now(timezone.utc)
    client.app.state.telemetry.history.clear()
    for index in range(3600):
        client.app.state.telemetry.history.append({"timestamp": (now-timedelta(seconds=3599-index)).isoformat()})
    data = client.get('/api/history?seconds=3600').json()
    assert 1 < len(data['samples']) <= 241
    assert data['samples'][-1]['timestamp'] == now.isoformat()
    assert client.get('/api/history?seconds=3601').status_code == 422
    apps = client.get('/api/apps').json()
    assert apps and all('target' not in app for app in apps)


def test_static_shell_and_security_headers(client):
    page = client.get('/')
    assert page.status_code == 200
    assert 'frame-ancestors' in page.headers['content-security-policy']
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/style.css').status_code == 200


def test_expired_session(client):
    paired(client)
    token = client.cookies.get('g16_device')
    with client.app.state.devices.db:
        client.app.state.devices.db.execute('UPDATE devices SET expires=0')
    assert client.get('/api/apps').status_code == 401
