import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.controllers import AppRegistry
from backend.games import GameLibrary
from backend.main import create_app


@pytest.fixture
def library(tmp_path):
    return GameLibrary(steam_roots=[tmp_path / 'steam'], epic_dir=tmp_path / 'epic',
                       riot_dir=tmp_path / 'riot', gog_records=[], custom_file=tmp_path / 'custom.json')


def steam_app(root, app_id, name, install='Game', flags='4'):
    directory = root / 'steamapps'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'common' / install).mkdir(parents=True, exist_ok=True)
    (directory / f'appmanifest_{app_id}.acf').write_text(
        f'"AppState" {{ "appid" "{app_id}" "name" "{name}" "StateFlags" "{flags}" "installdir" "{install}" }}', encoding='utf-8')


def test_steam_multiple_libraries_filters_non_games_and_missing_installs(library, tmp_path):
    secondary = tmp_path / 'secondary'
    steam_app(library.steam_roots[0], '100', 'First game')
    steam_app(secondary, '200', '日本語 Game')
    steam_app(secondary, '228980', 'Steamworks Common Redistributables', 'Shared')
    steam_app(secondary, '300', 'Incomplete', 'Incomplete', flags='2')
    steam_app(secondary, '400', 'Unsafe path', '../Outside')
    steam_app(secondary, '500', 'Removed', 'Removed')
    (secondary / 'steamapps/common/Removed').rmdir()
    encoded = str(secondary).replace('\\', '\\\\')
    (library.steam_roots[0] / 'steamapps/libraryfolders.vdf').write_text(f'"libraryfolders" {{ "0" {{ "path" "{encoded}" }} }}')
    assert {game['name'] for game in library.catalog()['games']} == {'First game', '日本語 Game'}


def test_epic_filters_tools_and_incomplete_installs_and_encodes_uri(library, tmp_path):
    library.epic_dir.mkdir()
    folder = tmp_path / 'installed'
    folder.mkdir()
    for app_id, name, incomplete in [('game:with?reserved', 'A real game', False), ('UE_5.7', 'Unreal Engine', False), ('other', 'Not finished', True)]:
        (library.epic_dir / f'{name}.item').write_text(json.dumps({'AppName': app_id, 'DisplayName': name, 'InstallLocation': str(folder), 'bIsIncompleteInstall': incomplete}))
    games = library.catalog()['games']
    assert [game['name'] for game in games] == ['A real game']
    record = library.records[games[0]['id']]
    assert 'game%3Awith%3Freserved?action=launch' in record['target']
    assert 'target' not in games[0] and 'folder' not in games[0]


def test_riot_requires_installed_executable_and_uses_client(library, tmp_path):
    client = tmp_path / 'RiotClientServices.exe'
    client.touch()
    folder = tmp_path / 'VALORANT'
    folder.mkdir()
    (folder / 'VALORANT.exe').touch()
    library.riot_dir.mkdir()
    (library.riot_dir / 'RiotClientInstalls.json').write_text(json.dumps({'rc_default': str(client)}))
    for product in ('valorant', 'league_of_legends'):
        metadata = library.riot_dir / f'Metadata/{product}.live'
        metadata.mkdir(parents=True)
        (metadata / f'{product}.live.product_settings.yaml').write_text(f'product_install_full_path: "{folder.as_posix()}"')
    games = library.catalog()['games']
    assert [game['name'] for game in games] == ['VALORANT']
    record = library.records[games[0]['id']]
    assert record['target'] == str(client)
    assert record['args'] == ['--launch-product=valorant', '--launch-patchline=live']


def test_gog_custom_executable_boundaries_and_refresh(library, tmp_path):
    exe = tmp_path / 'Game.exe'
    exe.touch()
    shell = tmp_path / 'powershell.exe'
    shell.touch()
    library.gog_records = [{'gameid': '123', 'gamename': 'GOG game', 'path': str(tmp_path), 'exe': str(exe)}]
    library.custom_file.write_text(json.dumps([{'name': 'Unsafe shell', 'target': str(shell)}]))
    assert [game['name'] for game in library.catalog()['games']] == ['GOG game']
    exe.unlink()
    assert library.catalog(force=True)['games'] == []


def test_launch_only_scanned_ids_and_no_client_targets(library):
    steam_app(library.steam_roots[0], '100', 'First game')
    game_id = library.catalog()['games'][0]['id']
    with patch('backend.games.os.startfile', create=True) as launch:
        assert library.launch(game_id)['ok']
        launch.assert_called_once_with('steam://rungameid/100')
    with pytest.raises(HTTPException) as error:
        library.launch('cmd.exe')
    assert error.value.status_code == 404


def test_game_endpoints_require_approval_and_origin(library):
    steam_app(library.steam_roots[0], '100', 'First game')
    app = create_app(pairing_code='ABCD1234')
    app.state.games = library
    with TestClient(app, client=('127.0.0.1', 40000)) as client:
        assert client.get('/api/games').status_code == 401
        assert client.post('/api/games/refresh', headers={'origin': 'http://testserver'}).status_code == 401
        assert client.post('/api/games/launch', json={'id': 'anything'}, headers={'origin': 'http://testserver'}).status_code == 401
        assert client.get('/api/games/anything/artwork').status_code == 401
        client.post('/api/pair', json={'code': 'ABCD1234'}, headers={'origin': 'http://testserver'})
        catalog = client.get('/api/games').json()
        assert [game['name'] for game in catalog['games']] == ['First game']
        assert 'target' not in catalog['games'][0]
        assert client.post('/api/games/refresh', headers={'origin': 'http://testserver'}).status_code == 200
        with patch('backend.games.os.startfile', create=True) as launch:
            assert client.post('/api/games/launch', json={'id': catalog['games'][0]['id']}, headers={'origin': 'http://testserver'}).status_code == 200
            launch.assert_called_once_with('steam://rungameid/100')
        assert client.post('/api/games/refresh', headers={'origin': 'http://evil.example'}).status_code == 403
        assert client.post('/api/games/launch', json={'id': 'anything', 'target': 'cmd.exe'}, headers={'origin': 'http://testserver'}).status_code == 422
        assert client.post('/api/games/launch', json={'id': '../cmd.exe'}, headers={'origin': 'http://testserver'}).status_code == 422
        client.post('/api/logout', headers={'origin': 'http://testserver'})
        assert client.get('/api/games').status_code == 401


def test_brave_resolution_and_youtube_argument(tmp_path, monkeypatch):
    brave = tmp_path / 'BraveSoftware/Brave-Browser/Application/brave.exe'
    brave.parent.mkdir(parents=True)
    brave.touch()
    monkeypatch.setenv('PROGRAMFILES', str(tmp_path))
    with patch('backend.controllers.shutil.which', return_value=None):
        registry = AppRegistry.__new__(AppRegistry)
        registry.apps = [{'id': 'youtube', 'name': 'YouTube', 'target': 'brave.exe', 'args': ['https://www.youtube.com/']}]
        assert registry.available(registry.apps[0])
        with patch('backend.controllers.subprocess.Popen') as launch:
            registry.launch('youtube')
            assert launch.call_args.args[0] == [str(brave), 'https://www.youtube.com/']
            assert launch.call_args.kwargs['shell'] is False
