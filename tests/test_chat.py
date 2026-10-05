"""Unified chat authorization, shared context, and late-action cancellation."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.agent.chat import ChatService, ChatMessage
from backend.agent.chat_worker import chat_worker
from backend.agent.service import AssistantService
from backend.main import create_app
from backend.voice import VoiceService

ORIGIN = {'origin': 'https://testserver'}


@pytest.fixture
def chat(tmp_path):
    voice = VoiceService(tmp_path, Mock(), Mock())
    assistant = AssistantService(voice.history, tmp_path, unlocked=lambda: True)
    assistant.enable(True)
    service = ChatService(voice, assistant)
    voice.assistant, voice.chat = assistant, service
    yield service
    service.stop()
    assistant.close()


def turn(service, text='Check my PC'):
    return {'id': 'a'*24, 'phase': 'thinking', 'message': '', 'text': text,
            'context': service.assistant.voice_context(text), 'authorized': lambda: True,
            'stop': threading.Event(), 'assistantGeneration': service.assistant.generation,
            'voiceGeneration': service.voice.generation, 'deadline': time.monotonic()+120,
            'navigation': None, 'actions': []}


class Pipe:
    def __init__(self, events=()):
        self.events = list(events)
        self.sent = []
    def poll(self, *args):
        return bool(self.events)
    def recv(self):
        return self.events.pop(0)
    def send(self, item):
        self.sent.append(item)
    def close(self):
        pass


def process():
    return SimpleNamespace(is_alive=lambda: False, join=lambda **kwargs: None)


def test_approved_tablet_unified_history_and_owner_only_management(tmp_path, monkeypatch):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: True)
    app.state.voice.history.add('Spoken question', 'Spoken reply')
    app.state.voice.history.add('Private calendar question', 'Private calendar reply', kind='personal')
    captured = []
    def start(text, authorized):
        captured.append((text, authorized))
        return {'id': 'a'*24}
    monkeypatch.setattr(app.state.chat, 'start', start)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.get('/api/chat/history').status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            pending = tablet.post('/api/device/request', json={'name': 'QA tablet'}, headers=ORIGIN).json()
            assert tablet.get('/api/chat/history').status_code == 401
            owner.post(f"/api/devices/{pending['device']['id']}/approve", headers=ORIGIN)
            assert [r['heard'] for r in tablet.get('/api/chat/history').json()] == ['Spoken question', 'Private calendar question']
            assert 'Private calendar question' not in tablet.get('/api/voice/history').text
            assert tablet.post('/api/chat/messages', json={'text': 'Follow up'}, headers=ORIGIN).status_code == 200
            assert captured[-1][1]()
            assert tablet.post('/api/chat/messages', json={'text': 'Follow up'}, headers={'origin': 'https://evil.example'}).status_code == 403
            assert tablet.delete('/api/chat/history', headers={**ORIGIN, 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
            assert tablet.get('/api/assistant/status').status_code == 403
            private = 'private-message-'*100
            invalid = tablet.post('/api/chat/messages', json={'text': private}, headers=ORIGIN)
            assert invalid.status_code == 422 and 'private-message' not in invalid.text
            assert tablet.post('/api/chat/messages', json={'text': 'bad\x00'}, headers=ORIGIN).status_code == 422
            assert tablet.post('/api/chat/stop', json={'id': 'a'*24}, headers=ORIGIN).status_code == 200
            owner.post(f"/api/devices/{pending['device']['id']}/revoke", headers=ORIGIN)
            assert not captured[-1][1]()
            assert tablet.get('/api/chat/status').status_code == 401
        monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: False)
        assert owner.get('/api/chat/history').status_code == 409
        assert owner.get('/api/chat/status').json()['turn'] is None
        assert owner.delete('/api/chat/history', headers=ORIGIN).status_code == 200
        assert app.state.voice.history.recent() == []


def test_loopback_http_cannot_read_chat(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    with TestClient(app, base_url='http://testserver', client=('127.0.0.1', 4000)) as client:
        client.post('/api/pair', json={'code': 'ABCD1234'}, headers={'origin': 'http://testserver'})
        assert client.get('/api/chat/status').status_code == 426
        assert client.get('/api/chat/history').status_code == 426


def test_unconfigured_in_memory_service_has_honest_not_ready_status(monkeypatch):
    app = create_app(pairing_code='ABCD1234', start_assistant=True)
    monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: True)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as client:
        client.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        assert client.get('/api/chat/status').json()['ready'] is False
        assert client.post('/api/chat/messages', json={'text': 'Hello'}, headers=ORIGIN).status_code == 409


def test_chat_reply_is_the_next_voice_context_and_shared_clear(chat):
    chat.voice.history.add('I said this aloud', 'Voice answer')
    job = turn(chat, 'Typed follow up')
    assert job['context']['history'][-1]['content'] == 'Voice answer'
    chat._monitor(job, process(), Pipe([{'type': 'reply', 'reply': 'Typed answer',
                       'sources': [{'url': 'https://example.com/source', 'title': 'Source'}, {'url': 'javascript:bad'}]}]))
    assert job['phase'] == 'done'
    history = chat.assistant.voice_context('Spoken follow up')['history']
    assert [item['content'] for item in history] == ['I said this aloud', 'Voice answer', 'Typed follow up', 'Typed answer']
    assert len(chat.voice.history.recent()[-1]['sources']) == 1
    chat.voice.clear_history()
    assert chat.assistant.voice_context('Next')['history'] == []


@pytest.mark.parametrize('change', ['lock', 'disable', 'voice-stop', 'revoke', 'deadline', 'recording', 'consent'])
def test_cancelled_turn_cannot_act_or_save_late_reply(chat, monkeypatch, change):
    job = turn(chat)
    if change == 'lock':
        monkeypatch.setattr(chat.assistant, 'unlocked', lambda: False)
    elif change == 'disable':
        chat.assistant.enable(False)
    elif change == 'consent':
        chat.assistant.generation += 1
    elif change == 'voice-stop':
        chat.voice.stop()
    elif change == 'revoke':
        job['authorized'] = lambda: False
    elif change == 'recording':
        chat.voice.phase = 'recording'
    else:
        job['deadline'] = 0
    assert not chat.allowed(job)
    assert chat.dispatch(job, 'launch_app', {'id': 'brave'})['ok'] is False
    chat.voice.registry.launch_voice.assert_not_called()
    chat._monitor(job, process(), Pipe([{'type': 'reply', 'reply': 'Late private reply'}]))
    assert chat.voice.history.recent() == []
    assert job['phase'] == 'cancelled'
    assert job['text'] == '' and job['context'] is None


def test_personal_read_rechecks_cancellation_and_fixed_tools(chat, monkeypatch):
    job = turn(chat)
    def read(*args):
        job['stop'].set()
        return {'ok': True, 'message': 'Private result'}
    monkeypatch.setattr('backend.agent.chat.execute_personal', read)
    assert chat.dispatch(job, 'calendar_today', {}) == {'ok': False, 'message': 'Request cancelled.'}
    assert job['actions'] == []
    job = turn(chat)
    assert not chat.dispatch(job, 'run_shell', {'command': 'unsafe'})['ok']
    assert not chat.dispatch(job, 'launch_app', {'id': 'brave', 'path': 'bad.exe'})['ok']
    assert not chat.dispatch(job, 'rest-entry', {})['ok']


def test_chat_sheet_failure_preserves_safe_cause_without_raw_exception(chat, monkeypatch):
    from backend.agent.google import GoogleError
    def fail(*args):
        raise ValueError('Choose at most 100 rows, 20 columns and 1,000 cells.')
    monkeypatch.setattr('backend.agent.chat.execute_personal', fail)
    result = chat.dispatch(turn(chat), 'read_sheet', {'id': 'fixture', 'range': "'Stocks_'!A1:Z100"})
    assert result['code'] == 'invalid_sheet_range' and 'No cell read was sent' in result['message']
    def denied(*args):
        raise GoogleError('Google denied access. Check the API is enabled and the requested permissions were granted.')
    monkeypatch.setattr('backend.agent.chat.execute_personal', denied)
    assert 'Google denied access' in chat.dispatch(turn(chat), 'read_sheet', {'id': 'fixture'})['message']
    def raw(*args):
        raise ValueError('secret provider text')
    monkeypatch.setattr('backend.agent.chat.execute_personal', raw)
    assert 'secret' not in str(chat.dispatch(turn(chat), 'read_sheet', {'id': 'fixture'}))


def test_stop_targets_only_current_turn_and_voice_stop_cancels(chat):
    job = turn(chat)
    chat.turn = job
    chat.stop('b'*24)
    assert not job['stop'].is_set()
    chat.voice.stop()
    assert job['stop'].is_set()


def test_worker_uses_real_voice_runner_with_shared_context_without_audio(chat, monkeypatch, jarvis_sdk_transport):
    import openai
    client = Mock()
    client.api_key = 'sk-private-test'
    client.responses.create.return_value = SimpleNamespace(output=[], output_text='Same conversation, sir.')
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: client)
    chat.voice.history.add('Spoken earlier', 'Voice context')
    context = chat.assistant.voice_context('Typed now')
    pipe = Pipe()
    chat_worker(pipe, threading.Event(), 'sk-private-test', 'Typed now', [], context)
    assert pipe.sent[-1]['reply'] == 'Same conversation, sir.'
    inputs = json.dumps(client.responses.create.call_args.kwargs['input'])
    assert 'Spoken earlier' in inputs and 'Voice context' in inputs and 'Typed now' in inputs
    assert client.responses.create.call_args.kwargs['store'] is False


def test_text_validation_and_bounded_shared_history(chat):
    assert ChatMessage(text='  hello\nworld  ').text == 'hello\nworld'
    for index in range(505):
        chat.voice.history.add(f'voice or chat {index}', 'reply')
    assert chat.voice.history.db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0] == 500
    assert len(chat.voice.history.recent()) == 50
    assert len(chat.assistant.voice_context('follow up')['history']) == 12


def test_real_isolated_chat_process_without_microphone_or_audio_models(chat):
    # The literal introduction runs the shared dispatch path without a provider request.
    chat.voice.save_key('sk-test-' + 'x'*30)
    assert not (chat.voice.directory / 'models').exists()
    result = chat.start('Introduce yourself', lambda: True)
    assert result['id'] == chat.turn['id']
    deadline = time.monotonic() + 20
    while chat.turn['phase'] == 'thinking' and time.monotonic() < deadline:
        time.sleep(.1)
    assert chat.turn['phase'] == 'done', chat.turn['message']
    assert chat.voice.phase == 'off'
    assert chat.voice.history.recent()[-1]['heard'] == 'Introduce yourself'
    assert 'Jarvis' in chat.voice.history.recent()[-1]['reply']
