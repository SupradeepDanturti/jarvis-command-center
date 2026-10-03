from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.devices import DeviceStore
from backend.main import create_app

ORIGIN = {'origin': 'https://testserver'}


def test_pending_blocked_until_local_owner_approval_then_revocation():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.post('/api/pair', json={'code': 'ABCD1234', 'name': 'Laptop'}, headers=ORIGIN).status_code == 200
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            response = tablet.post('/api/device/request', json={'name': 'Redmi'}, headers=ORIGIN)
            assert response.status_code == 200
            assert 'Secure' in response.headers['set-cookie']
            request = response.json()['device']
            assert tablet.get('/api/system').status_code == 401
            assert tablet.get('/api/devices').status_code == 401
            assert owner.post(f"/api/devices/{request['id']}/approve", headers=ORIGIN).status_code == 200
            assert tablet.post('/api/device/activate', headers=ORIGIN).status_code == 200
            assert tablet.get('/api/apps').status_code == 200
            assert tablet.get('/api/devices').status_code == 403
            assert tablet.post(f"/api/devices/{request['id']}/approve", headers=ORIGIN).status_code == 403
            with tablet.websocket_connect('wss://testserver/ws', headers=ORIGIN) as ws:
                assert ws.receive_json()['type'] == 'telemetry'
                assert owner.post(f"/api/devices/{request['id']}/revoke", headers=ORIGIN).status_code == 200
                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()
            assert tablet.get('/api/apps').status_code == 401
            assert tablet.post('/api/device/activate', headers=ORIGIN).status_code == 401


def test_code_alone_cannot_authorize_a_remote_device():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver', client=('192.168.2.21', 4000)) as tablet:
        response = tablet.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert response.status_code == 200 and response.json()['device']['status'] == 'pending'
        assert tablet.get('/api/apps').status_code == 401
        assert tablet.get('/api/devices').status_code == 401


def test_remote_http_and_forged_owner_headers_blocked():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, client=('192.168.2.22', 4000)) as remote:
        assert remote.post('/api/device/request', json={'name': 'Redmi'}, headers={'origin':'http://testserver'}).status_code == 426
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4001)) as local:
        local.post('/api/pair', json={'code':'ABCD1234'}, headers=ORIGIN)
        token = local.cookies.get('g16_device')
    with TestClient(app, base_url='https://testserver', client=('192.168.2.23', 4002)) as remote:
        remote.cookies.set('g16_device', token)
        assert remote.get('/api/devices', headers={'X-Forwarded-For':'127.0.0.1'}).status_code == 403


def test_credentials_survive_restart_but_not_revocation(tmp_path):
    db = tmp_path / 'devices.sqlite3'
    store = DeviceStore(db)
    token, device = store.create('Laptop', '127.0.0.1', owner=True)
    second = DeviceStore(db)
    assert second.valid(token)['id'] == device['id']
    assert token.encode() not in db.read_bytes()
    second.revoke(device['id'])
    assert store.valid(token) is None
    assert second.valid(token) is None


def test_expired_requests_and_rate_limited_enrollment():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver', client=('192.168.2.24', 4000)) as remote:
        for _ in range(5):
            remote.cookies.clear()
            assert remote.post('/api/device/request', json={'name':'New browser'}, headers=ORIGIN).status_code == 200
        remote.cookies.clear()
        assert remote.post('/api/device/request', json={'name':'New browser'}, headers=ORIGIN).status_code == 429
    device = app.state.devices.list()[0]
    with app.state.devices.db:
        app.state.devices.db.execute('UPDATE devices SET expires=0')
    with pytest.raises(Exception) as error:
        app.state.devices.approve(device['id'])
    assert error.value.status_code == 409
