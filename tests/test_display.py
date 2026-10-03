from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.display import DisplayReports
from backend.main import create_app

ORIGIN = {'origin': 'https://testserver'}
DETAILS = dict(width=1280, height=720, visibleWidth=1280, visibleHeight=720,
               scale=2, mode='Normal browser', orientation='Landscape')


def test_only_approved_browser_reports_own_display_and_only_local_owner_reads_it():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            assert tablet.post('/api/device/display', json=DETAILS, headers=ORIGIN).status_code == 401
            device = tablet.post('/api/device/request', json={'name': 'Redmi'}, headers=ORIGIN).json()['device']
            assert tablet.post('/api/device/display', json=DETAILS, headers=ORIGIN).status_code == 401
            owner.post(f"/api/devices/{device['id']}/approve", headers=ORIGIN)
            assert tablet.post('/api/device/display', json=DETAILS, headers={'origin': 'https://evil.example'}).status_code == 403
            assert tablet.post('/api/device/display', json={**DETAILS, 'device_id': 'other'}, headers=ORIGIN).status_code == 422
            assert tablet.post('/api/device/display', json={**DETAILS, 'width': -1}, headers=ORIGIN).status_code == 422
            assert tablet.post('/api/device/display', json={**DETAILS, 'scale': 0}, headers=ORIGIN).status_code == 422
            assert tablet.post('/api/device/display', json=DETAILS, headers=ORIGIN).status_code == 200
            assert tablet.get('/api/devices').status_code == 403
            report = next(d['display'] for d in owner.get('/api/devices').json() if d['id'] == device['id'])
            assert {key: report[key] for key in DETAILS} == DETAILS
            assert report['reported_at'] > 0
            owner.post(f"/api/devices/{device['id']}/revoke", headers=ORIGIN)
            assert app.state.display_reports.get(device['id']) is None
            assert tablet.post('/api/device/display', json=DETAILS, headers=ORIGIN).status_code == 401
            assert next(d['display'] for d in owner.get('/api/devices').json() if d['id'] == device['id']) is None


def test_display_reports_expire_and_memory_is_bounded():
    reports = DisplayReports(retention=300, capacity=2)
    with patch('backend.display.time.time', return_value=1000):
        reports.record('one', DETAILS)
    with patch('backend.display.time.time', return_value=1001):
        reports.record('two', DETAILS)
    with patch('backend.display.time.time', return_value=1002):
        reports.record('three', DETAILS)
        assert reports.get('one') is None
        assert reports.get('three')['width'] == 1280
    with patch('backend.display.time.time', return_value=1303):
        assert reports.get('two') is None
        assert reports.get('three') is None


def test_logout_removes_display_report():
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        device = owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN).json()['device']
        assert owner.post('/api/device/display', json=DETAILS, headers=ORIGIN).status_code == 200
        assert owner.post('/api/logout', headers=ORIGIN).status_code == 200
        assert app.state.display_reports.get(device['id']) is None
