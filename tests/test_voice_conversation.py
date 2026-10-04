from array import array
from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.voice_actions import respond, safe_sources, spoken_reply, voice_tools
from backend.voice_history import VoiceHistory
from backend.voice_worker import collect_utterance, worker_main

ORIGIN = {'origin': 'https://testserver'}
SILENCE = b'\0\0' * 1280
SPEECH = array('h', [800] * 1280).tobytes()


def test_saved_history_retention_pagination_context_restart_and_clear(tmp_path):
    history = VoiceHistory(tmp_path)
    for i in range(505):
        history.add(f'question {i}', f'answer {i}', {'name': 'system_status', 'ok': True},
                    [{'url': 'https://example.com/source', 'title': 'Source'}])
    assert history.db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0] == 500
    recent = history.recent()
    assert len(recent) == 50
    older = history.recent(before=recent[0]['id'])
    assert older[-1]['id'] < recent[0]['id']
    restored = VoiceHistory(tmp_path)
    assert restored.context()[-1]['content'] == 'answer 504'
    assert len(restored.context()) == 12
    assert restored.recent()[-1]['sources'][0]['title'] == 'Source'
    restored.clear()
    assert restored.context() == []
    assert history.recent() == []


def test_history_and_followup_authorization_persistence_and_bounds(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    app.state.voice.history.add('How are you?', 'At your service, sir.')
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.get('/api/voice/history').status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert len(owner.get('/api/voice/history').json()) == 1
        assert owner.put('/api/voice/followup', json={'seconds': 30}, headers=ORIGIN).status_code == 200
        assert owner.get('/api/voice/status').json()['followupSeconds'] == 30
        assert create_app(pairing_code='ABCD1234', voice_dir=tmp_path).state.voice.followup_seconds == 30
        assert owner.put('/api/voice/followup', json={'seconds': 600}, headers=ORIGIN).status_code == 400
        assert owner.put('/api/voice/followup', json={'seconds': False}, headers=ORIGIN).status_code == 422
        assert owner.put('/api/voice/followup', json={'seconds': 0}, headers={'origin': 'https://evil.example'}).status_code == 403
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            request = tablet.post('/api/device/request', json={'name': 'History QA'}, headers=ORIGIN).json()
            owner.post(f"/api/devices/{request['device']['id']}/approve", headers=ORIGIN)
            assert tablet.get('/api/voice/history').json()[0]['heard'] == 'How are you?'
            assert tablet.delete('/api/voice/history', headers=ORIGIN).status_code == 403
            owner.post(f"/api/devices/{request['device']['id']}/revoke", headers=ORIGIN)
            assert tablet.get('/api/voice/history').status_code == 401
        assert owner.delete('/api/voice/history', headers=ORIGIN).status_code == 200
        assert owner.get('/api/voice/history').json() == []


def test_followup_audio_timeout_cap_cancel_and_overflow():
    stream = Mock()
    stream.read.return_value = (SILENCE, False)
    assert collect_utterance(stream, lambda: True, wait_seconds=15) is None
    assert stream.read.call_count == round(15 * 12.5)
    stream.reset_mock()
    stream.read.return_value = (SPEECH, False)
    audio = collect_utterance(stream, lambda: True)
    assert len(audio) == 16000 * 2 * 10
    stream.reset_mock()
    assert collect_utterance(stream, lambda: False) is None
    stream.read.assert_not_called()
    stream.read.return_value = (SPEECH, True)
    assert collect_utterance(stream, lambda: True) is None


def test_native_web_search_citations_and_jarvis_prompt_with_conversation():
    apps = Mock()
    apps.catalog.return_value = []
    assert {'type': 'web_search', 'search_context_size': 'low'} in voice_tools(apps)
    annotation = SimpleNamespace(type='url_citation', url='https://www.nasa.gov/example', title='NASA')
    response = SimpleNamespace(output=[SimpleNamespace(type='web_search_call'),
        SimpleNamespace(type='message', content=[SimpleNamespace(annotations=[annotation])])],
        output_text='Here you are, sir. [NASA](https://www.nasa.gov/example) confirms the result.')
    client, dispatch, cite = Mock(), Mock(), Mock()
    client.responses.create.return_value = response
    history = [{'role': 'user', 'content': 'Tell me about space.'}, {'role': 'assistant', 'content': 'What would you like to know?'}]
    reply = respond(client, 'Search NASA for it.', voice_tools(apps), dispatch, history=history, cite=cite)
    assert 'https://' not in reply
    assert 'sir' in reply
    request = client.responses.create.call_args.kwargs
    assert request['input'][:2] == history
    assert 'Jarvis from Iron Man' in request['instructions']
    assert 'untrusted data' in request['instructions']
    cite.assert_called_once_with([{'url': annotation.url, 'title': 'NASA'}])
    dispatch.assert_not_called()
    assert safe_sources([{'url': 'javascript:alert(1)'}, {'url': 'https://user:password@example.com'}]) == []
    assert 'https://' not in spoken_reply('Source: https://example.com/test')
    # A search followed by a laptop function must retain the search's sources.
    response.output.append(SimpleNamespace(type='function_call', name='launch_app',
                                          arguments='{"id":"steam"}', call_id='search-then-app'))
    final = SimpleNamespace(output=[], output_text='Opening Steam, sir.')
    client.responses.create.side_effect = [response, final]
    dispatch.return_value = {'ok': True, 'message': 'Opening Steam'}
    cite.reset_mock()
    assert respond(client, 'Search, then open Steam.', [], dispatch, cite=cite) == final.output_text
    cite.assert_called_once_with([{'url': annotation.url, 'title': 'NASA'}])


def test_worker_accepts_followup_without_second_wake_and_uses_previous_question(monkeypatch, tmp_path):
    import sys
    stop = threading.Event()
    streams = []
    for chunks in ([SPEECH, SPEECH, SILENCE] + [SILENCE] * 10, [SPEECH] + [SILENCE] * 10):
        stream = Mock()
        stream.read.side_effect = [(chunk, False) for chunk in chunks]
        manager = Mock()
        manager.__enter__ = Mock(return_value=stream)
        manager.__exit__ = Mock(return_value=False)
        streams.append(manager)
    microphone = Mock()
    microphone.RawInputStream.side_effect = streams
    monkeypatch.setitem(sys.modules, 'sounddevice', microphone)
    engine = Mock()
    def synthesize(text, wav):
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
        wav.writeframes(SILENCE)
    engine.load.return_value.synthesize_wav.side_effect = synthesize
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=engine))
    speaker = Mock(SND_MEMORY=4)
    plays = []
    def play(*args):
        plays.append(args)
        if len(plays) == 2:
            stop.set()
    speaker.side_effect = play
    monkeypatch.setitem(sys.modules, 'winsound', speaker)
    wake = Mock()
    wake.predict.return_value = {'hey_jarvis': 0.9}
    fake_wake_module = SimpleNamespace(Model=Mock(return_value=wake))
    monkeypatch.setitem(sys.modules, 'openwakeword', SimpleNamespace(model=fake_wake_module))
    monkeypatch.setitem(sys.modules, 'openwakeword.model', fake_wake_module)
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.audio.transcriptions.create.side_effect = [SimpleNamespace(text='Open that app.'), SimpleNamespace(text='Steam.')]
    message = lambda text: SimpleNamespace(output_text=text, output=[SimpleNamespace(type='message', content=[])])
    tool = SimpleNamespace(output_text='', output=[SimpleNamespace(type='function_call', name='launch_app',
                                                                  arguments='{"id":"steam"}', call_id='qa')])
    client.responses.create.side_effect = [message('Which app would you like, sir?'), tool, message('Opening Steam, sir.')]
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(return_value=client)))
    pipe = Mock()
    result_pending = []
    def send(event):
        if event['type'] == 'action':
            result_pending.append({'type': 'result', 'result': {'ok': True, 'message': 'Opening Steam'}})
    pipe.send.side_effect = send
    pipe.poll.side_effect = lambda *args: bool(result_pending)
    pipe.recv.side_effect = lambda: result_pending.pop(0)
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice_audio.resolve_input', return_value={'index': 1, 'name': 'Webcam'}), \
         patch('backend.voice_audio.resolve_output', return_value={'index': 12, 'name': 'Laptop speakers'}), \
         patch('backend.voice_audio.play_on_speaker', speaker):
        worker_main(pipe, stop, str(tmp_path), 'sk-qa-only', [], followup_seconds=15)
    assert len(plays) == 2
    assert wake.predict.call_count == 1
    assert microphone.RawInputStream.call_count == 2
    second_input = client.responses.create.call_args_list[1].kwargs['input']
    assert second_input[:2] == [{'role': 'user', 'content': 'Open that app.'},
                               {'role': 'assistant', 'content': 'Which app would you like, sir?'}]
    assert second_input[-1]['content'] == 'Steam.'
    phases = [call.args[0]['phase'] for call in pipe.send.call_args_list if call.args[0]['type'] == 'status']
    assert 'followup' in phases
    assert not any(phase == 'error' for phase in phases)
