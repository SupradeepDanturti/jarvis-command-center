import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from backend import ambient
from backend.main import create_app
from backend.voice import VoiceService
from backend.agent.voice_actions import execute_tool, respond, voice_tools


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'
    assets.mkdir()
    path = tmp_path / 'ambient-scenes.json'
    monkeypatch.setattr(ambient, 'ASSET_DIR', assets)
    monkeypatch.setattr(ambient, 'CATALOG_PATH', path)
    def save(scenes):
        path.write_text(json.dumps(scenes), encoding='utf-8')
        for scene in scenes.values():
            if isinstance(scene, dict) and scene.get('file') in {'fixture', 'new-fixture'}:
                (assets / (scene['file'] + '.webm')).write_bytes(b'fixture only')
                (assets / (scene['file'] + '.jpg')).write_bytes(b'fixture only')
    return path, assets, save


def scene(name='Ocean glow', file='fixture'):
    return {'name': name, 'description': 'A new local option.', 'file': file, 'type': 'video/webm', 'credit': ''}


def tool_specs():
    registry = Mock()
    registry.catalog.return_value = []
    return voice_tools(registry)


def call(name, arguments, identity):
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=identity)


def output(*items, text=''):
    return SimpleNamespace(output=list(items), output_text=text)


def test_ui_asset_discovery_and_selection_share_the_catalog(catalog):
    path, assets, save = catalog
    save({'ocean-glow': scene(), 'another-scene': scene('Another scene', 'new-fixture')})
    app = create_app(pairing_code='ABCD1234')
    with TestClient(app, base_url='https://testserver') as client:
        response = client.get('/static/ambient-scenes.js')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-cache'
        catalog_js = json.loads(response.text.removeprefix('const ambientScenes=').strip().removesuffix(';'))
        assert catalog_js == ambient.load_ambient_scenes()
        assert list(catalog_js) == ['ocean-glow', 'another-scene']
    options = execute_tool('list_ambient_scenes', {}, Mock(), Mock())['scenes']
    assert [option['id'] for option in options] == list(catalog_js)
    assert all('file' not in option and 'type' not in option for option in options)
    schema = next(tool for tool in tool_specs() if tool.get('name') == 'show_ambient')
    assert schema['parameters']['properties']['scene']['enum'] == list(catalog_js)
    navigate = Mock(return_value={'ok': True})
    assert execute_tool('show_ambient', {'scene': 'ocean-glow'}, Mock(), Mock(), navigate=navigate)['ok']
    navigate.assert_called_once_with('ambient', scene='ocean-glow')
    # Removing the movie immediately removes it from the UI asset, discovery and parent allowlist.
    (assets / 'fixture.webm').unlink()
    assert [option['id'] for option in ambient.ambient_options()] == ['another-scene']
    with pytest.raises(ValueError):
        execute_tool('show_ambient', {'scene': 'ocean-glow'}, Mock(), Mock(), navigate=navigate)
    assert navigate.call_count == 1


@pytest.mark.parametrize('value', [[], {'bad': {}}, {'bad': scene(file='../private/key')},
    {'bad': scene(file='https://example.com/movie')}, {'bad': {**scene(), 'type': 'text/html'}},
    {'bad': {**scene(), 'command': 'whoami'}}, {'__proto__': scene()}])
def test_catalog_never_exposes_nonlocal_or_invalid_entries(catalog, value):
    path, assets, save = catalog
    path.write_text(json.dumps(value), encoding='utf-8')
    assert ambient.load_ambient_scenes() == {}
    assert execute_tool('list_ambient_scenes', {}, Mock(), Mock())['ok'] is False
    assert not any(tool.get('name') == 'show_ambient' for tool in tool_specs())


@pytest.mark.parametrize('arguments', [{'scene': 'unknown'}, {'scene': []}, {'scene': '../../private/key'},
    {'scene': 'ocean-glow', 'url': 'https://example.com'}, {'scene': 'ocean-glow', 'screen': 'system'}])
def test_scene_arguments_cannot_escape_the_parent_allowlist(catalog, arguments):
    catalog[2]({'ocean-glow': scene()})
    navigate = Mock()
    with pytest.raises(ValueError):
        execute_tool('show_ambient', arguments, Mock(), Mock(), navigate=navigate)
    navigate.assert_not_called()


@pytest.mark.usefixtures('jarvis_sdk_transport')
def test_enabled_worker_refreshes_new_options_then_discovers_and_selects(catalog):
    save = catalog[2]
    save({'old-scene': scene('Old scene')})
    startup_tools = tool_specs()
    save({'new-scene': scene('Newly installed scene', 'new-fixture')})
    client, navigate = Mock(), Mock(return_value={'ok': True, 'message': 'New scene requested.'})
    client.responses.create.side_effect = [output(call('list_ambient_scenes', {}, 'discover')),
        output(call('show_ambient', {'scene': 'new-scene'}, 'select')), output(text='New scene requested.')]
    dispatch = Mock(side_effect=lambda name, args: execute_tool(name, args, Mock(), Mock(), navigate=navigate))
    assert respond(client, 'Show the newly installed scene in Ambient.', startup_tools, dispatch) == 'New scene requested.'
    schemas = client.responses.create.call_args_list[0].kwargs['tools']
    selector = next(tool for tool in schemas if tool.get('name') == 'show_ambient')
    assert selector['parameters']['properties']['scene']['enum'] == ['new-scene']
    assert [item.args[0] for item in dispatch.call_args_list] == ['list_ambient_scenes', 'show_ambient']
    navigate.assert_called_once_with('ambient', scene='new-scene')


@pytest.mark.usefixtures('jarvis_sdk_transport')
def test_selection_requires_discovery_and_uses_the_shared_screen_slot(catalog):
    catalog[2]({'ocean-glow': scene()})
    client, dispatch = Mock(), Mock()
    client.responses.create.side_effect = [output(call('show_ambient', {'scene': 'ocean-glow'}, 'premature')),
                                           output(text='Which scene would you like?')]
    respond(client, 'Show Ambient.', tool_specs(), dispatch)
    dispatch.assert_not_called()
    navigate = Mock(return_value={'ok': True, 'message': 'Scene requested.'})
    dispatch.side_effect = lambda name, args: execute_tool(name, args, Mock(), Mock(), navigate=navigate)
    client.responses.create.side_effect = [output(call('list_ambient_scenes', {}, 'discover')),
        output(call('show_ambient', {'scene': 'ocean-glow'}, 'scene'), call('show_screen', {'screen': 'home'}, 'second-screen')),
        output(text='Scene requested.')]
    respond(client, 'Show Ocean glow.', tool_specs(), dispatch)
    navigate.assert_called_once_with('ambient', scene='ocean-glow')


def test_navigation_preserves_selected_id_and_rejects_removed_scene(catalog):
    catalog[2]({'ocean-glow': scene()})
    service = VoiceService(None, Mock(), Mock())
    service._show_screen('ambient', scene='ocean-glow')
    assert service.navigation['screen'] == 'ambient' and service.navigation['scene'] == 'ocean-glow'
    catalog[0].write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        service._show_screen('ambient', scene='ocean-glow')


def test_missing_corrupt_or_empty_catalog_fails_honestly(catalog):
    assert ambient.load_ambient_scenes() == {}
    catalog[0].write_text('invalid JSON', encoding='utf-8')
    assert ambient.load_ambient_scenes() == {}
    catalog[0].write_text('{}', encoding='utf-8')
    assert ambient.load_ambient_scenes() == {}
