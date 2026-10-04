"""Owner-only, ID-based app registration without dispatching physical apps."""
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import app_discovery
from backend.controllers import AppRegistry
from backend.main import create_app

ORIGIN = {'origin': 'http://testserver'}


@pytest.fixture
def detected(tmp_path):
    executable = tmp_path / 'editor.exe'
    executable.write_bytes(b'fixture')
    return {'id': 'detected-' + 'a'*24, 'name': 'Editor <test>', 'target': str(executable),
            'args': [], 'process': 'editor.exe', 'category': 'Installed apps',
            'color': '#a9bacf', 'icon': 'apps', 'detected': True}


def test_owner_auth_origin_and_no_browser_paths(tmp_path, detected):
    app = create_app(pairing_code='ABCD1234', apps_path=tmp_path / 'apps.json')
    with TestClient(app, client=('127.0.0.1', 50000)) as owner:
        assert owner.get('/api/apps/detected').status_code == 401
        assert owner.post('/api/apps/shortcuts', json={'id': detected['id']}, headers=ORIGIN).status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        with patch('backend.controllers.discover_apps', return_value=[detected]):
            inventory = owner.get('/api/apps/detected')
            assert inventory.json() == [{'id': detected['id'], 'name': detected['name']}]
            assert owner.post('/api/apps/shortcuts', json={'id': detected['id']}).status_code == 403
            for extra in ({'target': detected['target']}, {'args': ['--anything']}, {'command': 'cmd.exe'}):
                assert owner.post('/api/apps/shortcuts', json={'id': detected['id'], **extra}, headers=ORIGIN).status_code == 422
            assert owner.post('/api/apps/shortcuts', json={'id': 'unknown'}, headers=ORIGIN).status_code == 409
            result = owner.post('/api/apps/shortcuts', json={'id': detected['id']}, headers=ORIGIN)
            assert result.status_code == 200
            assert result.json()[-1]['name'] == detected['name']
            assert all('target' not in a and 'args' not in a for a in result.json())
            assert owner.post('/api/apps/shortcuts', json={'id': detected['id']}, headers=ORIGIN).status_code == 409
        # Even an owner cookie cannot manage registration from a LAN peer or forwarded loopback.
        with TestClient(app, base_url='https://testserver', client=('192.168.1.50', 50001)) as tablet:
            tablet.cookies.update(owner.cookies)
            assert tablet.get('/api/apps').status_code == 200
            assert tablet.get('/api/apps/detected', headers={'x-forwarded-for': '127.0.0.1'}).status_code == 403
            assert tablet.post('/api/apps/shortcuts', json={'id': detected['id']}, headers={'origin': 'https://testserver'}).status_code == 403
            assert tablet.delete('/api/apps/shortcuts/'+detected['id'], headers={'origin': 'https://testserver'}).status_code == 403
        assert owner.delete('/api/apps/shortcuts/'+detected['id']).status_code == 403
        assert owner.delete('/api/apps/shortcuts/'+detected['id'], headers=ORIGIN).status_code == 200
        assert owner.post('/api/apps/launch', json={'id': detected['id']}, headers=ORIGIN).status_code == 404


def test_limit_persistence_and_save_failure(tmp_path, detected):
    path = tmp_path / 'saved.json'
    registry = AppRegistry(path)
    originals = list(registry.apps)
    registry.detected = {detected['id']: detected}
    registry.discovered_at = time.monotonic()
    registry.add(detected['id'])
    assert AppRegistry(path).apps == [*originals, detected]
    with patch('backend.controllers.subprocess.Popen') as launch:
        registry.launch(detected['id'])
        assert launch.call_args.args[0] == [detected['target']]
        assert launch.call_args.kwargs['shell'] is False
    registry.remove('steam')
    assert 'steam' not in {a['id'] for a in AppRegistry(path).apps}
    registry.apps = [{**detected, 'id': 'app-'+str(i)} for i in range(25)]
    with pytest.raises(HTTPException, match='25 apps'):
        registry.add(detected['id'])
    with patch('pathlib.Path.replace', side_effect=OSError):
        with pytest.raises(HTTPException, match='unchanged'):
            registry.remove('app-0')
    assert len(registry.apps) == 25


def test_expired_or_missing_discovery_and_executable(tmp_path, detected):
    registry = AppRegistry()
    registry.detected = {detected['id']: detected}
    registry.discovered_at = time.monotonic() - 121
    with pytest.raises(HTTPException, match='Refresh'):
        registry.add(detected['id'])
    registry.discovered_at = time.monotonic()
    (tmp_path / 'editor.exe').unlink()
    with pytest.raises(HTTPException, match='no longer installed'):
        registry.add(detected['id'])
    with patch('backend.controllers.discover_apps', side_effect=subprocess.TimeoutExpired('fixed', 12)):
        registry.discovered_at = 0
        with pytest.raises(HTTPException, match='Could not detect'):
            registry.discover()


def test_concurrent_additions_cannot_exceed_limit(tmp_path, detected):
    second = {**detected, 'id': 'detected-'+'b'*24, 'process': 'other.exe', 'target': str(tmp_path/'other.exe')}
    (tmp_path/'other.exe').write_bytes(b'fixture')
    registry = AppRegistry(tmp_path/'selected.json')
    registry.apps = [{**detected, 'id': 'app-'+str(i), 'process': f'old-{i}.exe',
                      'target': str(tmp_path/f'old-{i}.exe')} for i in range(24)]
    registry.detected = {detected['id']: detected, second['id']: second}
    registry.discovered_at = time.monotonic()

    def add(app_id):
        try:
            registry.add(app_id)
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(add, registry.detected)) == [200, 409]
    assert len(registry.apps) == len(AppRegistry(tmp_path/'selected.json').apps) == 25


def test_discovery_filters_deduplicates_and_uses_fixed_shortcuts(tmp_path):
    valid = tmp_path / 'nice.exe'
    valid.write_bytes(b'fixture')
    records = [{'name': 'Friendly editor', 'target': str(valid)},
               {'name': 'duplicate', 'target': str(valid)},
               {'name': 'remote', 'target': 'https://example.com/program.exe'},
               {'name': 'script', 'target': str(tmp_path/'file.ps1')}]
    for name in ['cmd.exe', 'python.exe', 'pyw.exe', 'powershell_ise.exe', 'winget.exe', 'regedit.exe', 'unins000.exe']:
        path = tmp_path / name
        path.write_bytes(b'fixture')
        records.append({'name': name, 'target': str(path)})
    with patch.object(app_discovery, 'shortcut_records', return_value=records), patch.object(app_discovery, 'app_path_records', return_value=[]), patch.object(app_discovery, 'packaged_records', return_value=[]):
        first = app_discovery.discover_apps()
        second = app_discovery.discover_apps()
    assert first == second
    assert len(first) == 1 and first[0]['name'] == 'Friendly editor'
    assert first[0]['args'] == []
    assert len(first[0]['id']) < 80
    with patch.object(app_discovery.subprocess, 'run') as run:
        run.return_value.stdout = b'[]'
        assert app_discovery.shortcut_records() == []
        assert run.call_args.args[0][-1] == app_discovery.SHORTCUT_SCRIPT
        assert run.call_args.kwargs['timeout'] == 12


@pytest.fixture
def packaged(tmp_path):
    root = tmp_path/'package'
    root.mkdir()
    (root/'AppxManifest.xml').write_text('<Package/>')
    from backend.app_icons import png_chunk
    import struct
    import zlib
    png = b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + png_chunk(b'IDAT', zlib.compress(b'\x00\xff\x80\x40\xff')) + png_chunk(b'IEND', b'')
    logo = root/'logo.png'
    logo.write_bytes(png)
    return {'id': 'detected-'+'c'*24, 'name': 'Claude', 'aumid': 'Claude_pzs8sxrjxfjjc!Claude',
            'target': 'shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude', 'args': [], 'process': 'Claude.exe',
            'packageRoot': str(root), 'logo': str(logo), 'kind': 'packaged', 'category': 'Installed apps',
            'icon': 'apps', 'color': '#a9bacf', 'detected': True}


def test_packaged_detection_registration_and_fixed_launch(tmp_path, packaged):
    invalid = [dict(packaged, aumid='https://example.com/app'), dict(packaged, process='cmd.exe'),
               dict(packaged, aumid='Claude_pzs8sxrjxfjjc!../cmd.exe'), dict(packaged, aumid=None)]
    with patch.object(app_discovery, 'shortcut_records', return_value=[]), patch.object(app_discovery, 'app_path_records', return_value=[]), patch.object(app_discovery, 'packaged_records', return_value=[packaged, *invalid]):
        apps = app_discovery.discover_apps()
    assert len(apps) == 1 and apps[0]['name'] == 'Claude'
    registry = AppRegistry(tmp_path/'selected.json')
    registry.detected = {apps[0]['id']: apps[0]}
    registry.discovered_at = time.monotonic()
    catalog = registry.add(apps[0]['id'])
    assert all(not {'target', 'args', 'aumid', 'packageRoot', 'logo'} & app.keys() for app in catalog)
    with patch('backend.controllers.os.startfile') as start, patch('backend.controllers.subprocess.Popen') as popen:
        registry.launch(apps[0]['id'])
        start.assert_called_once_with('shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude')
        popen.assert_not_called()
    restored = AppRegistry(tmp_path/'selected.json')
    assert restored.apps[-1]['aumid'] == packaged['aumid']
    (tmp_path/'package/AppxManifest.xml').unlink()
    with patch('backend.controllers.os.startfile') as start:
        with pytest.raises(HTTPException, match='could not be opened'):
            restored.launch(apps[0]['id'])
        start.assert_not_called()


def test_app_icons_authenticated_cached_and_removed(tmp_path, detected):
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        url = '/api/apps/'+detected['id']+'/artwork'
        assert client.get(url).status_code == 401
        client.post('/api/pair', json={'code':'ABCD1234'}, headers=ORIGIN)
        registry = app.state.registry
        registry.detected = {detected['id']:detected}
        registry.discovered_at = time.monotonic()
        registry.add(detected['id'])
        with patch('backend.controllers.installed_icon', return_value=b'fixture-icon') as icon:
            result = client.get(url)
            assert result.status_code == 200 and result.content == b'fixture-icon'
            assert result.headers['content-type'] == 'image/png'
            assert client.get(url).status_code == 200
            icon.assert_called_once()
        assert client.get('/api/apps/unknown/artwork').status_code == 404
        registry.remove(detected['id'])
        assert client.get(url).status_code == 404


def test_package_logo_stays_inside_installation(packaged, tmp_path):
    from backend.app_icons import installed_icon
    assert installed_icon(packaged).startswith(b'\x89PNG')
    outside = tmp_path/'outside.png'
    outside.write_bytes(b'\x89PNG')
    assert installed_icon(dict(packaged, logo=str(outside))) is None
    assert installed_icon(dict(packaged, logo=packaged['packageRoot']+'/missing.png')) is None


def test_transient_windows_save_lock_is_bounded(tmp_path, detected):
    from pathlib import Path
    registry = AppRegistry(tmp_path/'saved.json')
    locked = PermissionError('temporary sharing violation')
    locked.winerror = 32
    replace = Path.replace
    calls = 0

    def retry(path, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise locked
        return replace(path, destination)

    with patch.object(Path, 'replace', retry):
        registry._save([detected])
    assert calls == 2 and AppRegistry(tmp_path/'saved.json').apps == [detected]
    with patch.object(Path, 'replace', side_effect=locked) as retry, patch('backend.controllers.time.sleep'):
        with pytest.raises(HTTPException, match='unchanged'):
            registry._save([])
        assert retry.call_count == 5
    assert registry.apps == [detected]
