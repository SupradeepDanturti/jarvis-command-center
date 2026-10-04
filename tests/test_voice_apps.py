"""Full Settings inventory for voice; all physical app dispatch and cloud transport are mocked."""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.controllers import AppRegistry
from backend.main import create_app
from backend.voice import VoiceService
from backend.agent.voice_actions import execute_tool, respond, voice_tools


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    def desktop(identity, name):
        executable = tmp_path / (identity + '.exe')
        executable.write_bytes(b'fixture only')
        return {'id': identity, 'name': name, 'target': str(executable), 'args': [],
                'process': executable.name, 'detected': True}
    saved = desktop('saved-editor', 'Saved editor')
    unselected = desktop('detected-' + 'a' * 24, 'Unselected editor')
    duplicate = {**saved, 'id': 'detected-' + 'b' * 24}
    root = tmp_path / 'package'
    root.mkdir()
    (root / 'AppxManifest.xml').write_text('<Package/>')
    packaged = {'id': 'detected-' + 'c' * 24, 'name': 'Packaged editor', 'args': [], 'kind': 'packaged',
                'aumid': 'Editor_abcdefghijklm!Editor', 'packageRoot': str(root), 'process': 'PackageEditor.exe',
                'target': 'shell:AppsFolder\\Editor_abcdefghijklm!Editor', 'detected': True}
    rows = [unselected, duplicate, packaged]
    monkeypatch.setattr('backend.controllers.discover_apps', lambda: rows)
    registry = AppRegistry(tmp_path / 'selected.json')
    registry.apps = [saved]
    return registry, rows, desktop


def test_discovery_includes_settings_inventory_without_saving_shortcuts(inventory):
    registry, rows, _ = inventory
    with patch.object(registry, '_save') as save:
        result = execute_tool('list_apps', {}, registry, Mock())
    assert result['ok']
    assert result['apps'] == [{'id': app['id'], 'name': app['name']} for app in [registry.apps[0], rows[0], rows[2]]]
    assert all(set(app) == {'id', 'name'} for app in result['apps'])
    assert {app['id'] for app in registry.discover()} <= {app['id'] for app in result['apps']}
    assert len(registry.apps) == 1 and not registry.selection_path.exists()
    save.assert_not_called()


def test_full_inventory_is_not_limited_to_twenty_five_shortcuts(inventory):
    registry, rows, desktop = inventory
    rows.extend(desktop('detected-' + f'{index + 10:024x}', 'Available editor ' + str(index)) for index in range(60))
    assert len(registry.voice_catalog()) == 63
    assert len(registry.apps) == 1


def test_unselected_desktop_and_packaged_launch_use_fixed_server_records(inventory):
    registry, rows, _ = inventory
    registry.voice_catalog()
    with patch('backend.controllers.subprocess.Popen') as popen, patch('backend.controllers.os.startfile') as start:
        assert execute_tool('launch_app', {'id': rows[0]['id']}, registry, Mock())['ok']
        popen.assert_called_once_with([rows[0]['target']], cwd=str(registry.selection_path.parent), shell=False)
        assert execute_tool('launch_app', {'id': rows[2]['id']}, registry, Mock())['ok']
        start.assert_called_once_with(rows[2]['target'])
    assert len(registry.apps) == 1 and not registry.selection_path.exists()


@pytest.mark.parametrize('arguments', [{'id': 'unknown'}, {'id': []}, {'id': '../private/key'},
    {'id': 'https://example.com'}, {'id': 'saved-editor', 'args': ['--anything']},
    {'id': 'saved-editor', 'target': 'cmd.exe'}, {'id': 'saved-editor', 'url': 'https://example.com'}])
def test_model_cannot_submit_paths_commands_urls_or_unknown_apps(inventory, arguments):
    registry = inventory[0]
    registry.voice_catalog()
    with patch('backend.controllers.subprocess.Popen') as popen, patch('backend.controllers.os.startfile') as start:
        with pytest.raises((ValueError, HTTPException)):
            execute_tool('launch_app', arguments, registry, Mock())
    popen.assert_not_called()
    start.assert_not_called()


@pytest.mark.parametrize('condition', ['stale', 'removed', 'arguments', 'missing-package', 'blocked'])
def test_unselected_launch_revalidates_availability_and_discovery(inventory, condition):
    registry, rows, _ = inventory
    registry.voice_catalog()
    identity = rows[0]['id']
    if condition == 'stale':
        registry.discovered_at = time.monotonic() - 121
    elif condition == 'removed':
        from pathlib import Path
        Path(rows[0]['target']).unlink()
    elif condition == 'arguments':
        rows[0]['args'] = ['--arbitrary']
    elif condition == 'missing-package':
        from pathlib import Path
        (Path(rows[2]['packageRoot']) / 'AppxManifest.xml').unlink()
        identity = rows[2]['id']
    elif condition == 'blocked':
        from pathlib import Path
        executable = registry.selection_path.parent / 'powershell.exe'
        executable.write_bytes(b'fixture only')
        rows[0]['target'] = str(executable)
    with patch.object(registry, '_launch') as launch:
        with pytest.raises(HTTPException):
            registry.launch_voice(identity)
    launch.assert_not_called()


def test_new_apps_and_removal_reach_an_enabled_worker_without_restarting(inventory, jarvis_sdk_transport):
    registry, rows, desktop = inventory
    startup_tools = voice_tools(registry)
    assert not registry.discovered_at  # No expensive Windows inventory in voice startup.
    new = desktop('detected-' + 'd' * 24, 'Newly installed editor')
    rows.append(new)
    client = Mock()
    def call(name, arguments, identity):
        return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=identity)
    def output(*items, text=''):
        return SimpleNamespace(output=list(items), output_text=text)
    client.responses.create.side_effect = [output(call('list_apps', {}, 'discover')),
        output(call('launch_app', {'id': new['id']}, 'launch')), output(text='Opening Newly installed editor.')]
    with patch.object(registry, '_launch', return_value={'ok': True, 'message': 'Opening Newly installed editor.'}) as launch:
        dispatch = Mock(side_effect=lambda name, args: execute_tool(name, args, registry, Mock()))
        assert respond(client, 'Open Newly installed editor.', startup_tools, dispatch) == 'Opening Newly installed editor.'
        launch.assert_called_once_with(new)
    assert [item.args[0] for item in dispatch.call_args_list] == ['list_apps', 'launch_app']
    assert len(registry.apps) == 1
    rows.remove(new)
    registry.discovered_at = 0
    assert new['id'] not in {app['id'] for app in registry.voice_catalog()}
    with patch.object(registry, '_launch') as launch, pytest.raises(HTTPException):
        registry.launch_voice(new['id'])
    launch.assert_not_called()


@pytest.mark.parametrize('discovery', [None, {'ok': False, 'apps': []}, {'ok': True, 'apps': [{'id': 'other', 'name': 'Other'}]}])
def test_sdk_requires_this_turns_successful_discovery_before_launch(inventory, jarvis_sdk_transport, discovery):
    registry, rows, _ = inventory
    client, dispatch = Mock(), Mock(return_value=discovery)
    call = lambda name, args: SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id=name)
    output = lambda *items, text='': SimpleNamespace(output=list(items), output_text=text)
    turns = [] if discovery is None else [output(call('list_apps', {}))]
    client.responses.create.side_effect = [*turns, output(call('launch_app', {'id': rows[0]['id']})), output(text='Which app would you like?')]
    assert respond(client, 'Open an editor.', voice_tools(registry), dispatch) == 'Which app would you like?'
    assert all(item.args[0] == 'list_apps' for item in dispatch.call_args_list)


def test_empty_or_failed_discovery_is_not_an_old_or_invented_list(inventory):
    registry, rows, _ = inventory
    registry.apps = []
    rows.clear()
    assert execute_tool('list_apps', {}, registry, Mock()) == {'ok': False, 'apps': [], 'message': 'No available apps were found.'}
    registry.discovered_at = 0
    with patch('backend.controllers.discover_apps', side_effect=OSError()), pytest.raises(HTTPException):
        execute_tool('list_apps', {}, registry, Mock())
    assert registry.discovered_at == 0


def test_browser_launch_and_owner_shortcut_management_are_not_expanded(inventory, tmp_path):
    registry, rows, _ = inventory
    registry.voice_catalog()
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path / 'voice')
    original = app.state.registry
    original.apps, original.detected, original.discovered_at = registry.apps, registry.detected, registry.discovered_at
    origin = {'origin': 'https://testserver'}
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 50000)) as owner:
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=origin)
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 50001)) as tablet:
            device = tablet.post('/api/device/request', json={'name': 'Apps QA'}, headers=origin).json()['device']['id']
            owner.post('/api/devices/' + device + '/approve', headers=origin)
            assert tablet.get('/api/apps/detected').status_code == 403
            assert tablet.post('/api/apps/shortcuts', json={'id': rows[0]['id']}, headers=origin).status_code == 403
            with patch.object(original, '_launch') as launch:
                assert tablet.post('/api/apps/launch', json={'id': rows[0]['id']}, headers=origin).status_code == 404
                assert tablet.post('/api/apps/launch', json={'id': 'saved-editor', 'args': []}, headers=origin).status_code == 422
            launch.assert_not_called()


@pytest.mark.parametrize('cancel', ['lock', 'stop', 'generation'])
def test_parent_discovery_releases_voice_lock_and_rechecks_after_slow_read(inventory, cancel):
    registry = inventory[0]
    service = VoiceService(None, registry, Mock())
    service.phase, service.generation = 'thinking', 1
    service.stop_event = threading.Event()
    process, pipe = Mock(), Mock()
    events = [{'type': 'action', 'id': 'catalog', 'name': 'list_apps', 'arguments': {}}]
    process.is_alive.side_effect = lambda: bool(events)
    pipe.poll.side_effect = lambda *args: bool(events)
    pipe.recv.side_effect = lambda: events.pop(0)
    unlocked = [True]
    def inventory_read():
        def change():
            with service.lock:
                if cancel == 'stop':
                    service.stop_event.set()
                elif cancel == 'generation':
                    service.generation += 1
                else:
                    unlocked[0] = False
        thread = threading.Thread(target=change, daemon=True)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive(), 'Slow app discovery must not hold the voice cancellation lock'
        return [{'id': 'saved-editor', 'name': 'Saved editor'}]
    with patch.object(registry, 'voice_catalog', side_effect=inventory_read), \
         patch('backend.voice_worker.desktop_unlocked', side_effect=lambda: unlocked[0]), patch.object(registry, '_launch') as launch:
        service._monitor(1, process, pipe)
    if cancel == 'generation':
        pipe.send.assert_not_called()
    else:
        assert pipe.send.call_args.args[0]['result']['ok'] is False
    launch.assert_not_called()


@pytest.mark.parametrize('condition', ['off', 'locked', 'stopped', 'generation'])
def test_parent_denies_catalog_reads_from_inactive_or_old_workers(inventory, condition):
    service = VoiceService(None, inventory[0], Mock())
    service.phase, service.generation = ('off' if condition == 'off' else 'thinking'), (2 if condition == 'generation' else 1)
    service.stop_event = threading.Event()
    if condition == 'stopped':
        service.stop_event.set()
    process, pipe = Mock(), Mock()
    events = [{'type': 'action', 'id': 'catalog', 'name': 'list_apps', 'arguments': {}}]
    process.is_alive.side_effect = lambda: bool(events)
    pipe.poll.side_effect = lambda *args: bool(events)
    pipe.recv.side_effect = lambda: events.pop(0)
    with patch.object(service.registry, 'voice_catalog') as read, \
         patch('backend.voice_worker.desktop_unlocked', return_value=condition != 'locked'):
        service._monitor(1, process, pipe)
    read.assert_not_called()
    if condition != 'generation':
        assert pipe.send.call_args.args[0]['result']['ok'] is False


def test_busy_discovery_cannot_delay_a_physical_launch(inventory):
    registry = inventory[0]
    started, release = threading.Event(), threading.Event()
    def hold():
        with registry.lock:
            started.set()
            release.wait(3)
    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(2)
    try:
        with patch.object(registry, '_launch') as launch, pytest.raises(HTTPException, match='being refreshed'):
            registry.launch_voice('saved-editor')
        launch.assert_not_called()
    finally:
        release.set()
        thread.join(timeout=2)


def test_discovery_pipe_has_time_for_fixed_windows_reads_but_launch_deadline_stays_short():
    from backend.voice_worker import request_tool_action
    for name in ('list_apps', 'launch_app'):
        pipe, stop = Mock(), threading.Event()
        message = []
        pipe.send.side_effect = lambda event: message.append({'type': 'result', 'id': event['id'], 'result': {'ok': True}})
        pipe.poll.return_value = True
        pipe.recv.side_effect = lambda: message.pop(0)
        with patch('backend.voice_worker.time.monotonic', side_effect=[0, 6]):
            result = request_tool_action(pipe, stop, name, {}, lambda: True, Mock())
        assert result['ok'] is (name == 'list_apps')


def test_parallel_app_and_scene_discovery_have_independent_slots(inventory, jarvis_sdk_transport):
    from backend.ambient import ambient_options
    registry, rows, _ = inventory
    scene = ambient_options()[0]
    client, navigate = Mock(), Mock(return_value={'ok': True, 'message': 'Scene requested.'})
    call = lambda name, args: SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id=name)
    output = lambda *items, text='': SimpleNamespace(output=list(items), output_text=text)
    client.responses.create.side_effect = [output(call('list_apps', {}), call('list_ambient_scenes', {}), call('system_status', {})),
        output(call('launch_app', {'id': rows[0]['id']}), call('show_ambient', {'scene': scene['id']})),
        output(text='Opening your editor and requesting the scene.')]
    telemetry = SimpleNamespace(latest={'cpu': {'usage': 12}, 'memory': {'percent': 34}, 'gpu': None})
    dispatch = Mock(side_effect=lambda name, args: execute_tool(name, args, registry, telemetry, navigate=navigate))
    with patch.object(registry, '_launch', return_value={'ok': True, 'message': 'Opening editor.'}) as launch:
        assert respond(client, 'Open my editor, select an Ambient scene and read my CPU.', voice_tools(registry), dispatch)
        launch.assert_called_once_with(rows[0])
    navigate.assert_called_once_with('ambient', scene=scene['id'])
    assert [item.args[0] for item in dispatch.call_args_list] == ['list_apps', 'list_ambient_scenes', 'system_status', 'launch_app', 'show_ambient']
