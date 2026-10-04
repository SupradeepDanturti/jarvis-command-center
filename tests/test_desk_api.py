from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.main import create_app

ORIGIN = {'origin': 'https://testserver'}


def test_private_reads_mutations_origin_and_strict_arguments():
    app = create_app(pairing_code='ABCD1234')
    client = TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000))
    for url in ['/api/focus','/api/thermals','/api/thermals/inventory','/api/media/artwork/'+'a'*24]:
        assert client.get(url).status_code == 401
    assert client.post('/api/focus/command',json={'action':'start','revision':0},headers=ORIGIN).status_code == 401
    client.post('/api/pair',json={'code':'ABCD1234'},headers=ORIGIN)
    for url, method, body in [('/api/focus/command','post',{'action':'start','revision':0}),
        ('/api/focus/settings','put',{'revision':0,'focus':25,'short':5,'long':15,'announcements':False}),
        ('/api/media/seek','post',{'sessionId':'a'*24,'trackRevision':'b'*24,'position':5}),
        ('/api/media/session-action','post',{'sessionId':'a'*24,'trackRevision':'b'*24,'action':'next'}),
        ('/api/thermals/settings','put',{'enabled':True})]:
        assert getattr(client,method)(url,json=body,headers={'origin':'https://evil.example'}).status_code == 403
        assert getattr(client,method)(url,json={**body,'command':'cmd.exe'},headers=ORIGIN).status_code == 422
    assert client.post('/api/focus/command',json={'action':'start','revision':True},headers=ORIGIN).status_code == 422
    assert client.put('/api/focus/settings',json={'revision':0,'focus':181,'short':5,'long':15,'announcements':False},headers=ORIGIN).status_code == 422
    assert client.put('/api/thermals/settings',json={'enabled':True,'fans':['../secret']},headers=ORIGIN).status_code == 422
    app.state.media.command = AsyncMock(return_value={'ok': True})
    assert client.post('/api/media/seek',json={'sessionId':'a'*24,'trackRevision':'b'*24,'position':15},headers=ORIGIN).status_code == 200
    app.state.media.command.assert_awaited_once_with('a'*24,'b'*24,'seek',15)
    assert client.post('/api/focus/command',json={'action':'start','revision':0},headers=ORIGIN).status_code == 200
    assert client.post('/api/focus/command',json={'action':'start','revision':0},headers=ORIGIN).status_code == 409
    client.post('/api/logout',headers=ORIGIN)
    assert client.get('/api/focus').status_code == 401


def test_remote_approved_browser_cannot_configure_sensors_or_read_inventory():
    app = create_app(pairing_code='ABCD1234')
    token, device = app.state.devices.create('QA tablet','192.168.1.20')
    app.state.devices.approve(device['id'])
    client = TestClient(app, base_url='https://testserver', client=('192.168.1.20',4000))
    client.cookies.set('g16_device',token)
    assert client.get('/api/focus').status_code == 200
    assert client.get('/api/thermals').status_code == 200
    assert client.get('/api/thermals/inventory').status_code == 403
    assert client.put('/api/thermals/settings',json={'enabled':True},headers=ORIGIN).status_code == 403
