"""Requested local artifacts and Markdown memory retain dashboard trust boundaries."""
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest
from fastapi.testclient import TestClient

from backend.agent.artifacts import ArtifactStore, prepare_artifact, artifact_tools
from backend.agent.memory import MemoryStore
from backend.agent.memory_files import MemoryFiles, execute_memory_file, memory_file_tools
from backend.agent.service import AssistantService
from backend.agent.voice_actions import respond
from backend.main import create_app
from backend.voice_history import VoiceHistory
from backend.voice import VoiceService

ORIGIN = {'origin': 'https://testserver'}


def test_artifact_store_bounds_formats_and_no_arbitrary_paths(tmp_path):
    store = ArtifactStore(VoiceHistory(tmp_path))
    first = store.create({'title': 'Interactive <page>', 'format': 'html', 'content': '<h1>Hello</h1>'})
    identity = first['id']
    assert store.get(identity)['content'] == b'<h1>Hello</h1>'
    for index in range(20):
        store.create({'title': f'Note {index}', 'format': 'txt', 'content': 'Private note'})
    assert len(store.all()) == 20
    with pytest.raises(Exception):
        store.get(identity)
    for fields in [{'title': 'Bad', 'format': 'exe', 'content': 'code'},
                   {'title': 'Bad', 'format': 'txt', 'content': 'x'*100001},
                   {'title': 'Bad\nheader', 'format': 'txt', 'content': 'text'},
                   {'title': 'Bad', 'format': 'txt', 'content': 'text', 'path': '../secret'},
                   {'title': 'Bad', 'format': 'json', 'content': '{invalid json}'},
                   {'title': 'Bad', 'format': 'pdf', 'content': 'raw PDF bytes'}]:
        with pytest.raises(ValueError):
            store.create(fields)
    assert not (tmp_path / 'secret').exists()


def test_pdf_is_local_text_rendering_with_no_actions_or_external_resources(tmp_path):
    arguments = {'title': 'Daily report', 'format': 'pdf',
                 'content': '# Plan\nRésumé and café.\n- First task\n| Time | Plan |\n| --- | --- |\n| 09:00 | Focus |\n<script>bad</script>\n<image src="https://evil.example">'}
    result = ArtifactStore(VoiceHistory(tmp_path)).create(prepare_artifact(arguments))
    pdf = ArtifactStore(VoiceHistory(tmp_path)).get(result['id'])['content']
    assert pdf.startswith(b'%PDF-') and pdf.rstrip().endswith(b'%%EOF')
    assert b'/OpenAction' not in pdf and b'/S /JavaScript' not in pdf and b'/EmbeddedFile' not in pdf and b'/URI ' not in pdf
    assert len(pdf) <= 256000
    assert max(map(int, re.findall(rb'/Count (\d+)', pdf))) <= 30
    with pytest.raises(ValueError):
        prepare_artifact({**arguments, 'path': 'C:/secret'})
    with pytest.raises(ValueError):
        prepare_artifact({**arguments, 'content': 'x'*20001})


def test_artifact_approved_tablet_preview_download_and_owner_delete(tmp_path, monkeypatch):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: True)
    item = app.state.artifacts.create({'title': 'Page "quoted"', 'format': 'html', 'content': '<script>document.body.textContent="Works"</script>'})
    path = '/api/artifacts/'+item['id']
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 1)) as owner:
        assert owner.get(path+'/preview').status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        with TestClient(app, base_url='https://testserver', client=('192.168.1.2', 2)) as tablet:
            device = tablet.post('/api/device/request', json={'name': 'Artifact QA'}, headers=ORIGIN).json()['device']
            assert tablet.get('/api/artifacts').status_code == 401
            owner.post(f"/api/devices/{device['id']}/approve", headers=ORIGIN)
            preview = tablet.get(path+'/preview')
            assert preview.status_code == 200 and 'document.body' in preview.text
            policy = preview.headers['content-security-policy']
            assert 'sandbox allow-scripts' in policy and 'allow-same-origin' not in policy
            assert "connect-src 'none'" in policy and "frame-src 'none'" in policy and "form-action 'none'" in policy
            assert preview.headers['cache-control'] == 'no-store'
            download = tablet.get(path+'/download')
            assert download.status_code == 200 and 'attachment' in download.headers['content-disposition']
            assert '\n' not in download.headers['content-disposition']
            assert tablet.delete(path, headers={**ORIGIN, 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
            assert owner.delete(path, headers={'origin': 'https://evil.example'}).status_code == 403
            monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: False)
            assert tablet.get(path+'/preview').status_code == 409
            monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: True)
            owner.post(f"/api/devices/{device['id']}/revoke", headers=ORIGIN)
            assert tablet.get(path+'/download').status_code == 401
        assert owner.delete(path, headers=ORIGIN).status_code == 200
        assert owner.get(path+'/preview').status_code == 404


def test_markdown_files_are_actual_files_with_revision_and_cancel_protection(tmp_path):
    files = MemoryFiles(VoiceHistory(tmp_path), tmp_path)
    assert files.enabled()
    initial = files.read('diet.md')
    assert initial['revision'] is None
    files.write('diet.md', '# Diet\n- I am vegetarian.', None)
    path = tmp_path/'memory/diet.md'
    assert path.read_text(encoding='utf-8') == '# Diet\n- I am vegetarian.'
    prior = files.read('diet.md')
    with pytest.raises(ValueError):
        files.write('diet.md', 'Stale edit', None)
    calls = iter([True, False])
    with pytest.raises(ValueError):
        files.write('diet.md', 'Cancelled edit', prior['revision'], lambda: next(calls))
    assert path.read_text(encoding='utf-8') == prior['content']
    assert not list(path.parent.glob('*.tmp'))
    files.write('diet.md', '# Diet\n- I am vegan now.', prior['revision'])
    reopened = MemoryFiles(VoiceHistory(tmp_path), tmp_path)
    assert 'vegan' in reopened.selected('diet')[0]['content']
    assert not reopened.history.db.execute('SELECT name FROM sqlite_master WHERE name="memory_files"').fetchall()
    files.set_enabled(False)
    assert reopened.selected('diet') == []
    files.delete('diet.md')
    assert not path.exists()


@pytest.mark.parametrize('name', ['../secret', 'C:/secret', 'profile.js', 'con.md', 'lpt1', 'foo/bar', '.hidden', 'AUX'])
def test_memory_names_never_escape_private_folder(tmp_path, name):
    files = MemoryFiles(VoiceHistory(tmp_path), tmp_path)
    with pytest.raises(ValueError):
        files.write(name, 'user fact', None)


def test_memory_blocks_credentials_and_unattributed_or_late_changes(tmp_path):
    service = AssistantService(VoiceHistory(tmp_path), tmp_path, unlocked=lambda: True)
    service.enable(True)
    generation = service.generation
    args = {'name': 'profile.md', 'content': '# Profile\n- I like jazz.', 'revision': None, 'evidence': 'I like jazz'}
    assert not service.memory.cloud()  # Local user-authorized memory is independent of Google consent.
    result = execute_memory_file(service, 'write_memory', args, 'I like jazz', generation, lambda: True)
    assert result['message'] == 'Added to memory profile.md'
    assert service.voice_context('music')['personal']['localMemory'][0]['name'] == 'profile.md'
    with pytest.raises(ValueError):
        execute_memory_file(service, 'write_memory', {**args, 'name': 'diet.md'}, 'Search result text', generation, lambda: True)
    with pytest.raises(ValueError):
        execute_memory_file(service, 'write_memory', {**args, 'name': 'diet.md'}, 'I like jazz', generation, lambda: False)
    for secret in ['password is secret', 'sk-'+'x'*30, 'refresh_token: private', '-----BEGIN PRIVATE KEY-----']:
        with pytest.raises(ValueError):
            service.files.write('secrets.md', secret, None)
    service.enable(False)
    with pytest.raises(Exception):
        execute_memory_file(service, 'write_memory', args, 'I like jazz', generation, lambda: True)
    assert not (tmp_path/'memory/secrets.md').exists()


def test_reviewed_facts_migrate_to_markdown_before_sqlite_retirement(tmp_path):
    history = VoiceHistory(tmp_path)
    # Seed the pre-migration format without creating a file-backed MemoryStore.
    history.db.execute('CREATE TABLE assistant_memory (id TEXT PRIMARY KEY,text TEXT,source TEXT,pending INTEGER,updated REAL)')
    history.db.execute('INSERT INTO assistant_memory VALUES(?,?,?,?,?)', ('old', 'I like jazz', 'owner', 0, 1))
    history.db.commit()
    memory = MemoryStore(history)
    assert memory.all()[0]['text'] == 'I like jazz'
    path = tmp_path/'memory/reviewed-facts.md'
    assert '- I like jazz' in path.read_text(encoding='utf-8')
    assert history.db.execute('SELECT COUNT(*) FROM assistant_memory').fetchone()[0] == 0
    memory.save('I prefer mornings')
    assert len(MemoryStore(VoiceHistory(tmp_path)).all()) == 2
    memory.delete('old')
    assert 'I like jazz' not in path.read_text(encoding='utf-8')


def test_local_memory_history_does_not_reenable_account_context(tmp_path):
    service = AssistantService(VoiceHistory(tmp_path), tmp_path, unlocked=lambda: True)
    service.enable(True)
    service.files.write('profile.md', '# Profile\n- I like jazz.', None)
    service.memory.history.add('Calendar private', 'Account reply', kind='personal')
    service.memory.history.add('Local fact', 'Memory reply', kind='memory')
    context = service.voice_context('what music?')
    assert 'profile' not in context['personal']
    assert [item['content'] for item in context['history']] == ['Local fact', 'Memory reply']
    assert service.memory.history.recent(personal=False) == []
    service.files.set_enabled(False)
    assert service.voice_context('next')['history'] == []


def test_markdown_management_remains_owner_only_and_revision_checked(tmp_path, monkeypatch):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    monkeypatch.setattr(app.state.assistant, 'unlocked', lambda: True)
    app.state.assistant.files.write('profile.md', '# Profile\n- I like jazz.', None)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 1)) as owner:
        assert owner.get('/api/assistant/memory/files').status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        data = owner.get('/api/assistant/memory/files').json()
        assert data['enabled'] and data['files'][0]['name'] == 'profile.md'
        revision = data['files'][0]['revision']
        body = {'content': '# Profile\n- I like blues.', 'revision': revision}
        assert owner.put('/api/assistant/memory/files/profile.md', json=body, headers={'origin': 'https://evil.example'}).status_code == 403
        assert owner.put('/api/assistant/memory/files/profile.md', json=body, headers=ORIGIN).status_code == 200
        assert owner.put('/api/assistant/memory/files/profile.md', json=body, headers=ORIGIN).status_code == 503
        assert owner.get('/api/assistant/memory/files/profile.md/download').text == body['content']
        with TestClient(app, base_url='https://testserver', client=('192.168.1.2', 2)) as tablet:
            device = tablet.post('/api/device/request', json={'name': 'Memory QA'}, headers=ORIGIN).json()['device']
            owner.post(f"/api/devices/{device['id']}/approve", headers=ORIGIN)
            assert tablet.get('/api/assistant/memory/files').status_code == 403
            assert tablet.put('/api/assistant/memory/files/profile.md', json=body, headers={**ORIGIN, 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
            assert tablet.delete('/api/assistant/memory/files/profile.md', headers=ORIGIN).status_code == 403
        assert owner.put('/api/assistant/memory/files/enabled', json={'enabled': False}, headers=ORIGIN).status_code == 200
        assert not app.state.assistant.files.enabled()
        assert owner.delete('/api/assistant/memory/files/profile.md', headers=ORIGIN).status_code == 200
        assert not (tmp_path/'memory/profile.md').exists()


def test_memory_topic_capacity_and_recall_are_bounded(tmp_path):
    files = MemoryFiles(VoiceHistory(tmp_path), tmp_path)
    for index in range(20):
        files.write(f'topic-{index}.md', '# Topic\n'+f'fact {index} '*100, None)
    with pytest.raises(ValueError):
        files.write('overflow.md', 'Too many files', None)
    selected = files.selected('fact')
    assert len(selected) <= 10 and sum(len(item['content']) for item in selected) <= 10000
    reviewed = MemoryStore(files.history)
    reviewed.save('An earlier approved preference')
    assert len(files.all()) == 21  # The reserved reviewed-facts file has its own 200-fact bound.


def test_spoken_parent_writes_same_markdown_recalled_by_typed_context(tmp_path, monkeypatch):
    voice = VoiceService(tmp_path, Mock(), Mock())
    service = AssistantService(voice.history, tmp_path, unlocked=lambda: True)
    service.enable(True)
    voice.assistant = service
    heard = 'I prefer jazz.'
    events = [dict(type='status', phase='thinking', message='Working'), dict(type='turn'),
              dict(type='action', name='assistant_context', arguments={'heard': heard}, id='context'),
              dict(type='action', name='read_memory', arguments={'name': 'preferences.md'}, id='read'),
              dict(type='action', name='write_memory', arguments={'name': 'preferences.md', 'content': '# Preferences\n- I prefer jazz.',
                   'revision': None, 'evidence': heard}, id='write'), dict(type='exchange', heard=heard, reply='Added to memory preferences.md.')]
    pipe = SimpleNamespace(poll=lambda *args: bool(events), recv=lambda: events.pop(0), send=Mock(), close=lambda: None)
    process = SimpleNamespace(is_alive=lambda: bool(events), join=lambda **kwargs: None)
    voice.process, voice.stop_event = process, threading.Event()
    monkeypatch.setattr('backend.voice_worker.desktop_unlocked', lambda: True)
    monkeypatch.setattr(voice, '_check_alerts', lambda *args: None)
    monkeypatch.setattr(voice, '_check_reminders', lambda *args: None)
    voice._monitor(voice.generation, process, pipe)
    assert 'jazz' in (tmp_path/'memory/preferences.md').read_text(encoding='utf-8')
    context = service.voice_context('What music do I like?')
    assert context['personal']['localMemory'][0]['name'] == 'preferences.md'
    assert context['history'][0]['content'] == heard
    row = voice.history.recent()[-1]
    assert row['kind'] == 'memory'
    assert 'evidence' not in json.dumps(row['action'])


def call(name, arguments, identity):
    return SimpleNamespace(output_text='', output=[SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps(arguments), call_id=identity)])


def test_real_runner_creates_and_opens_pdf_and_writes_evidenced_memory(tmp_path, jarvis_sdk_transport):
    store = ArtifactStore(VoiceHistory(tmp_path))
    client = Mock()
    created = {}
    def transport(**kwargs):
        if not created:
            return call('create_artifact', {'title': 'My report', 'format': 'pdf', 'content': '# Report\nA complete local report.'}, 'create')
        if len(created) == 1:
            created['opened'] = True
            return call('open_artifact', {'id': created['id']}, 'open')
        return SimpleNamespace(output=[], output_text='Your report is ready.')
    def dispatch(name, arguments):
        result = store.dispatch(name, arguments, lambda screen, **options: {'ok': True, 'message': 'Artifact opened.'})
        if name == 'create_artifact':
            created['id'] = result['id']
        return result
    client.responses.create.side_effect = transport
    assert respond(client, 'Create and open a PDF report', artifact_tools(), dispatch) == 'Your report is ready.'
    assert store.get(created['id'])['content'].startswith(b'%PDF-')
    assert client.responses.create.call_args_list[0].kwargs['max_output_tokens'] == 8000
    service = AssistantService(store.history, tmp_path, unlocked=lambda: True)
    service.enable(True)
    heard = 'I am vegetarian.'
    revision = service.files.read('diet.md')['revision']
    client.responses.create.side_effect = [call('list_memories', {}, 'list'), call('read_memory', {'name': 'diet.md'}, 'read'),
         call('write_memory', {'name': 'diet.md', 'content': '# Diet\n- I am vegetarian.', 'revision': revision, 'evidence': heard}, 'write'),
         SimpleNamespace(output=[], output_text='Added to memory diet.md.')]
    result = respond(client, heard, memory_file_tools(), lambda name, args: execute_memory_file(service, name, args, heard, service.generation, lambda: True))
    assert 'diet.md' in result and 'vegetarian' in (tmp_path/'memory/diet.md').read_text(encoding='utf-8')
