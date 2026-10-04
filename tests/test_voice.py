from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.voice import MODEL_FILES, VoiceService
from backend.voice_actions import execute_tool, respond, voice_tools

ORIGIN = {'origin': 'https://testserver'}


def test_voice_auth_key_owner_origin_and_private_storage(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path / 'voice')
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.get('/api/voice/status').status_code == 401
        assert owner.post('/api/voice/enabled', json={'enabled': True}, headers=ORIGIN).status_code == 401
        assert owner.put('/api/voice/key', json={'key': 'sk-test-' + 'x' * 30}, headers=ORIGIN).status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert owner.put('/api/voice/key', json={'key': 'sk-test-' + 'x' * 30}, headers={'origin': 'https://evil.example'}).status_code == 403
        assert owner.put('/api/voice/key', json={'key': 'bad'}, headers=ORIGIN).status_code == 400
        key = 'sk-test-' + 'x' * 30
        assert owner.put('/api/voice/key', json={'key': key}, headers=ORIGIN).status_code == 200
        encrypted = (tmp_path / 'voice/openai-key.dpapi').read_bytes()
        assert key.encode() not in encrypted
        assert key not in owner.get('/api/voice/status').text
        assert owner.get('/api/voice/status').json()['keyConfigured'] is True
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            request = tablet.post('/api/device/request', json={'name': 'QA tablet'}, headers=ORIGIN).json()
            assert tablet.get('/api/voice/status').status_code == 401
            owner.post(f"/api/devices/{request['device']['id']}/approve", headers=ORIGIN)
            assert tablet.get('/api/voice/status').status_code == 200
            assert tablet.put('/api/voice/key', json={'key': key}, headers=ORIGIN).status_code == 403
            assert tablet.delete('/api/voice/key', headers=ORIGIN).status_code == 403
            assert tablet.put('/api/voice/key', json={'key': key}, headers={**ORIGIN, 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
            with patch.object(app.state.voice, 'start') as start:
                assert tablet.post('/api/voice/enabled', json={'enabled': True}, headers=ORIGIN).status_code == 200
                start.assert_called_once_with()
            owner.post(f"/api/devices/{request['device']['id']}/revoke", headers=ORIGIN)
            assert tablet.post('/api/voice/enabled', json={'enabled': False}, headers=ORIGIN).status_code == 401
        assert owner.delete('/api/voice/key', headers=ORIGIN).status_code == 200
        assert not (tmp_path / 'voice/openai-key.dpapi').exists()


def test_voice_starts_off_missing_setup_does_not_record_and_input_restricted(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as client:
        client.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert client.get('/api/voice/status').json()['phase'] == 'off'
        assert client.get('/api/voice/status').json()['wakePhrase'] == 'Jarvis'
        assert client.post('/api/voice/enabled', json={'enabled': 'true'}, headers=ORIGIN).status_code == 422
        assert client.post('/api/voice/enabled', json={'enabled': True}, headers=ORIGIN).status_code == 409
        assert app.state.voice.process is None
        with patch.object(app.state.voice, 'audio_inputs', return_value=[{'id': 'webcam', 'name': 'Webcam microphone'}]):
            assert client.put('/api/voice/input', json={'id': 'shell://bad'}, headers=ORIGIN).status_code == 400
            assert client.put('/api/voice/input', json={'id': 'webcam'}, headers=ORIGIN).status_code == 200
            assert client.get('/api/voice/status').json()['inputId'] == 'webcam'
            assert client.put('/api/voice/input', json={'id': 'webcam'}, headers={'origin': 'https://evil.example'}).status_code == 403


def test_disabled_service_releases_worker_and_forgets_exchange():
    service = VoiceService(None, Mock(), Mock())
    process, stop = Mock(), Mock()
    service.process, service.stop_event, service.pipe = process, stop, Mock()
    service.last_heard, service.last_reply = 'private request', 'reply'
    service.stop()
    stop.set.assert_called_once()
    process.terminate.assert_called_once()
    assert service.process is None
    assert service.status()['lastHeard'] == ''
    assert service.phase == 'off'


def registry():
    result = Mock()
    result.catalog.return_value = [{'id': 'youtube', 'name': 'YouTube', 'available': True},
                                  {'id': 'missing', 'name': 'Missing', 'available': False}]
    result.launch.return_value = {'ok': True, 'message': 'Opening YouTube'}
    return result


@pytest.mark.parametrize('name,args', [('shell', {'command': 'whoami'}), ('launch_app', {'id': 'missing'}),
    ('launch_app', {'id': 'youtube', 'url': 'https://evil.example'}), ('media_control', {'action': 'shutdown'}),
    ('media_control', {'action': []}), ('system_status', {'path': 'secret'}), ('launch_app', [])])
def test_model_cannot_escape_action_allowlist(name, args):
    apps = registry()
    with pytest.raises(ValueError):
        execute_tool(name, args, apps, Mock())
    apps.launch.assert_not_called()


def test_voice_tools_and_valid_registered_action():
    apps = registry()
    tools = voice_tools(apps)
    assert tools[0]['parameters']['properties']['id']['enum'] == ['youtube']
    assert 'target' not in str(tools)
    assert execute_tool('launch_app', {'id': 'youtube'}, apps, Mock())['ok']
    apps.launch.assert_called_once_with('youtube')
    with patch('backend.voice_actions.media_action', return_value={'ok': True}) as send:
        execute_tool('media_control', {'action': 'volume-up'}, apps, Mock())
        send.assert_called_once_with('volume-up')


def tool_response(arguments='{"id":"youtube"}'):
    return SimpleNamespace(output_text='', output=[SimpleNamespace(type='function_call', name='launch_app',
                          arguments=arguments, call_id='qa-call')])


def test_cloud_reply_failure_never_repeats_completed_action():
    client, dispatch = Mock(), Mock(return_value={'ok': True, 'message': 'Opening YouTube'})
    client.responses.create.side_effect = [tool_response(), RuntimeError('network failed')]
    assert respond(client, 'open youtube', [], dispatch) == 'Opening YouTube'
    dispatch.assert_called_once_with('launch_app', {'id': 'youtube'})
    assert all(call.kwargs['store'] is False for call in client.responses.create.call_args_list)
    assert all(call.kwargs['model'] == 'gpt-6-luna' for call in client.responses.create.call_args_list)


def test_stop_during_cloud_request_blocks_action_and_multiple_calls_rejected():
    client, dispatch = Mock(), Mock()
    response = tool_response()
    client.responses.create.return_value = response
    assert respond(client, 'open youtube', [], dispatch, allowed=lambda: False) == ''
    dispatch.assert_not_called()
    response.output *= 2
    assert 'one laptop command' in respond(client, 'open youtube', [], dispatch)
    dispatch.assert_not_called()


def test_microphone_resolution_excludes_stereo_mix_and_prefers_array():
    from backend.voice_audio import inputs, resolve_input
    devices = [{'name': name, 'max_input_channels': 2, 'hostapi': 0} for name in
               ['Stereo Mix', 'Microphone Array', 'Webcam microphone']]
    with patch('sounddevice.query_devices', return_value=devices), patch('sounddevice.query_hostapis', return_value={'name': 'MME'}), patch('sounddevice.check_input_settings'):
        choices = inputs()
        assert [d['name'] for d in choices] == ['Microphone Array', 'Webcam microphone']
        assert resolve_input()['index'] == 1
        assert resolve_input(choices[1]['id'])['index'] == 2
        with pytest.raises(ValueError):
            resolve_input('forged-input')


@pytest.mark.parametrize('current_generation,unlocked', [(1, False), (2, True)])
def test_parent_refuses_locked_or_old_worker_actions(current_generation, unlocked):
    service = VoiceService(None, registry(), Mock())
    service.phase, service.generation = 'thinking', current_generation
    service.stop_event = Mock()
    service.stop_event.is_set.return_value = False
    process = Mock()
    process.is_alive.side_effect = [True, False]
    pipe = Mock()
    pipe.poll.side_effect = [True, False]
    pipe.recv.return_value = {'type': 'action', 'name': 'launch_app', 'arguments': {'id': 'youtube'}}
    with patch('backend.voice_worker.desktop_unlocked', return_value=unlocked):
        service._monitor(1, process, pipe)
    service.registry.launch.assert_not_called()
    if current_generation == 1:
        assert pipe.send.call_args.args[0]['result']['ok'] is False


def test_voice_worker_preview_does_not_touch_microphone_or_cloud(monkeypatch, tmp_path):
    import sys
    from backend.voice_worker import worker_main
    def synthesize(text, wav):
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b'\0\0' * 100)
    voice = Mock()
    voice.synthesize_wav.side_effect = synthesize
    engine = Mock()
    engine.load.return_value = voice
    speaker = Mock()
    microphone = Mock()
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=engine))
    monkeypatch.setitem(sys.modules, 'sounddevice', microphone)
    pipe, stop = Mock(), Mock()
    pipe.poll.return_value = False
    stop.is_set.return_value = False
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice_audio.resolve_output', return_value={'index': 12, 'name': 'Laptop speakers'}), \
         patch('backend.voice_audio.play_on_speaker', speaker):
        worker_main(pipe, stop, str(tmp_path), None, [], preview=True)
    speaker.assert_called_once()
    assert speaker.call_args.args[1] == {'index': 12, 'name': 'Laptop speakers'}
    microphone.RawInputStream.assert_not_called()
    assert pipe.send.call_args.args[0]['phase'] == 'off'
