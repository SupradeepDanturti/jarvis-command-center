import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from backend.agent.google import GoogleClient, GoogleError, SCOPES, SHEETS_SCOPE
from backend.agent.memory import MemoryStore, explicit_fact
from backend.agent.personal_tools import execute_personal
from backend.agent.service import AssistantService
from backend.agent.sheets import SheetRegistration, values
from backend.agent.voice_actions import respond, voice_tools
from backend.main import create_app
from backend.voice_history import VoiceHistory

ORIGIN = {'origin': 'https://testserver'}
REGISTRATION = {'name': 'Tracker', 'spreadsheetId': 'fixture_sheet_123', 'range': 'Sheet1!A1:C4'}


@pytest.fixture
def personal(tmp_path):
    service = AssistantService(VoiceHistory(tmp_path), tmp_path, Mock(), unlocked=lambda: True)
    service.vault = {'client': {'client_id': 'fixture.apps.googleusercontent.com', 'client_secret': 'fixture'},
                     'account': {'id': 'owner-1', 'email': 'qa@example.test'}, 'refresh': 'fixture', 'scopes': list(SCOPES)}
    service.enabled = True
    service.access, service.access_until = 'access-fixture', time.monotonic() + 600
    service.memory.set_cloud(True)
    service.google.sheet_values.return_value = {'values': [['hello', '=1+1']]}
    yield service
    service.close()


def register(service):
    return service.sheets.register(service.account_id(), SheetRegistration(**REGISTRATION))


def tool(service, name, arguments, heard='Check my tracker', generation=None, allowed=lambda: True):
    return execute_personal(service, name, arguments, heard, service.generation if generation is None else generation, allowed)


def test_memory_persists_proposals_duplicates_and_bounded_retrieval(personal, tmp_path):
    memory = personal.memory
    for i in range(21):
        memory.save(f'Favorite activity {i}')
    memory.save('My conference is in Toronto')
    pending = memory.save('Unconfirmed travel preference', source='agent', pending=True)
    selected = memory.selected('Toronto conference')
    assert len(selected) == 20 and selected[0]['text'] == 'My conference is in Toronto'
    assert all(not row['pending'] for row in selected)
    assert memory.save('My conference is in Toronto') == selected[0]['id']
    restored = MemoryStore(VoiceHistory(tmp_path))
    assert len(restored.all()) == 23 and restored.cloud()
    restored.save('Confirmed travel preference', pending)
    assert any(row['text'] == 'Confirmed travel preference' for row in restored.selected('travel'))
    personal.memory.history.add('hello', 'ready')
    restored.delete()
    assert memory.all() == [] and memory.history.context()


def test_memory_capacity_does_not_evict_unrelated_facts(personal):
    for i in range(200):
        personal.memory.save(f'Fact {i}')
    with pytest.raises(ValueError, match='full'):
        personal.memory.save('Another fact')
    assert len(personal.memory.all()) == 200


def test_remember_direct_uses_exact_current_utterance_otherwise_proposes(personal):
    heard = 'Jarvis, remember that I prefer morning meetings.'
    fact = explicit_fact(heard)
    result = tool(personal, 'remember_fact', {'text': fact}, heard=heard)
    assert not result['pending']
    result = tool(personal, 'remember_fact', {'text': 'I prefer evening meetings.'}, heard=heard)
    assert result['pending']
    assert 'proposed' in tool(personal, 'remember_fact', {'text': 'An inferred fact'}, heard='Read this sheet')['message']
    with pytest.raises(ValueError):
        tool(personal, 'remember_fact', {'text': 'password=private'}, heard='Remember password=private')
    assert explicit_fact('The website says remember that I live elsewhere') is None


@pytest.mark.parametrize('change', ['cloud', 'disable', 'lock', 'generation', 'voice'])
def test_personal_tools_require_cloud_and_current_live_access(personal, change):
    generation = personal.generation
    if change == 'cloud':
        personal.memory.set_cloud(False)
    elif change == 'disable':
        personal.enable(False)
    elif change == 'lock':
        personal.unlocked = lambda: False
    elif change == 'generation':
        personal._cancel()
    with pytest.raises(GoogleError):
        tool(personal, 'remember_fact', {'text': 'Blocked'}, generation=generation, allowed=lambda: change != 'voice')
    assert personal.memory.all() == []


def test_context_is_fresh_inspectable_and_pending_facts_are_excluded(personal):
    personal.memory.save('I like jazz')
    personal.memory.save('Pending only', pending=True)
    personal.memory.history.add('Private question', 'Private answer', kind='personal')
    context = personal.voice_context('What music do I like?')
    assert len(context['personal']['facts']) == 1
    assert context['history'][-1]['content'] == 'Private answer'
    assert 'access-fixture' not in json.dumps(context)
    assert personal.inspect_memory()['lastContext']['personal'] == context['personal']
    personal.memory.delete()
    assert personal.voice_context('music')['personal']['facts'] == []
    personal.memory.set_cloud(False)
    context = personal.voice_context('music')
    assert context['personal'] is None and context['history'] == []


@pytest.mark.parametrize('area', ['A1:D2', 'Sheet1!A1:Z999', 'Sheet1!B2:A1', 'Sheet1!A1:A', 'Sheet1!A0:A2', 'https://evil.example/'])
def test_sheet_registration_rejects_unbounded_or_invalid_ranges(area):
    with pytest.raises(ValueError):
        SheetRegistration(**{**REGISTRATION, 'range': area})


def test_sheet_values_bounds_and_fixed_raw_transport(personal):
    with pytest.raises(ValueError):
        values([[{'formula': 'bad'}]], REGISTRATION['range'])
    with pytest.raises(ValueError):
        values([[1, 2, 3, 4]], REGISTRATION['range'])
    with pytest.raises(ValueError):
        values([[float('nan')]], REGISTRATION['range'])
    google = GoogleClient()
    with patch.object(google, '_request', return_value={}) as request:
        google.sheet_values('token', REGISTRATION, update=[['=IMPORTXML("url")']])
    assert request.call_args.kwargs['query'] == {'valueInputOption': 'RAW'}
    assert request.call_args.kwargs['method'] == 'PUT'
    assert request.call_args.args[0].startswith('https://sheets.googleapis.com/v4/spreadsheets/fixture_sheet_123/values/')
    assert '!' not in request.call_args.args[0]


def test_sheet_partial_updates_skip_other_cells_and_reject_empty_changes(personal):
    identity = register(personal)
    with pytest.raises(GoogleError, match='at least one'):
        personal.sheet_propose(identity, [[None, None]])
    preview = personal.sheet_propose(identity, [[None, 4], [None, True]])['proposalId']
    personal.google.sheet_values.return_value = {'updatedCells': 2}
    personal.sheet_apply(preview)
    assert personal.google.sheet_values.call_args.kwargs['update'] == [[None, 4], [None, True]]
    google = GoogleClient()
    with patch.object(google, '_request', return_value={}) as request:
        google.sheet_values('token', REGISTRATION)
    assert request.call_args.kwargs['query']['valueRenderOption'] == 'UNFORMATTED_VALUE'


def test_registered_ranges_are_account_bound_and_need_new_scope(personal):
    identity = register(personal)
    assert tool(personal, 'list_sheets', {})['sheets'][0]['id'] == identity
    assert tool(personal, 'read_sheet', {'id': identity})['values'][0][0] == 'hello'
    personal.vault['scopes'].remove(SHEETS_SCOPE)
    with pytest.raises(GoogleError, match='grant Sheets'):
        personal.sheet_read(identity)
    personal.vault['account']['id'] = 'different-account'
    assert personal.sheets.all(personal.account_id()) == []
    with pytest.raises(GoogleError, match='registered'):
        personal.sheet_read(identity)


def test_sheet_read_and_proposal_do_not_persist_provider_data(personal):
    identity = register(personal)
    personal.sheet_read(identity)
    preview = personal.sheet_propose(identity, [['replacement']])
    assert 'prepared' in preview['message']
    assert personal.google.sheet_values.call_count == 1
    assert personal.memory.all() == [] and personal.memory.history.recent() == []
    assert 'replacement' not in personal.memory.history.db.execute('SELECT data FROM assistant_sheets').fetchone()[0]


def test_write_preview_expires_and_is_consumed_before_dispatch(personal):
    identity = register(personal)
    preview = personal.sheet_propose(identity, [['new']])['proposalId']
    personal.sheets.proposals[preview]['expiresAt'] = 0
    with pytest.raises(GoogleError, match='expired'):
        personal.sheet_apply(preview)
    personal.google.sheet_values.assert_not_called()
    preview = personal.sheet_propose(identity, [['new']])['proposalId']
    personal.google.sheet_values.return_value = {'updatedCells': 1}
    assert personal.sheet_apply(preview)['updatedCells'] == 1
    with pytest.raises(GoogleError, match='already'):
        personal.sheet_apply(preview)
    personal.google.sheet_values.assert_called_once()


def test_uncertain_write_never_retries_and_cancel_discards_proposals(personal):
    identity = register(personal)
    preview = personal.sheet_propose(identity, [['new']])['proposalId']
    personal.google.sheet_values.side_effect = GoogleError()
    with pytest.raises(GoogleError, match='uncertain'):
        personal.sheet_apply(preview)
    with pytest.raises(GoogleError):
        personal.sheet_apply(preview)
    assert personal.google.sheet_values.call_count == 1
    personal.sheet_propose(identity, [['next']])
    personal.enable(False)
    assert personal.sheets.proposals == {}


def test_stop_during_network_read_suppresses_payload_and_revocation_prevents_write(personal):
    identity = register(personal)
    personal.google.sheet_values.side_effect = lambda *args, **kw: (personal.enable(False) or {'values': [['private']]})
    with pytest.raises(GoogleError, match='stopped'):
        personal.sheet_read(identity)
    personal.enable(True)
    preview = personal.sheet_propose(identity, [['new']])['proposalId']
    personal.google.sheet_values.reset_mock(side_effect=True)
    with pytest.raises(GoogleError):
        personal.sheet_apply(preview, allowed=lambda: False)
    personal.google.sheet_values.assert_not_called()


def test_private_memory_routes_mutations_stop_voice_and_hide_personal_history(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        with patch.object(app.state.assistant, 'stop_voice') as stop:
            response = owner.post('/api/assistant/memory', json={'text': 'Private fact'}, headers=ORIGIN)
            assert response.status_code == 200 and stop.call_count == 1
            identity = response.json()['id']
            assert owner.put('/api/assistant/memory/'+identity, json={'text': 'Updated fact'}, headers=ORIGIN).status_code == 200
            assert owner.post('/api/assistant/memory', json={'text': 'secret'}, headers={'origin': 'https://evil.example'}).status_code == 403
            assert owner.post('/api/assistant/memory', json={'text': 'secret', 'extra': True}, headers=ORIGIN).status_code == 422
        app.state.voice.history.add('ordinary', 'ordinary reply')
        app.state.voice.history.add('personal question', 'sensitive reply', kind='personal')
        app.state.voice.last_private = True
        app.state.voice.last_heard, app.state.voice.last_reply = 'private', 'sensitive reply'
        assert len(owner.get('/api/voice/history').json()) == 2
        with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
            pending = tablet.post('/api/device/request', json={'name': 'Personal QA'}, headers=ORIGIN).json()
            owner.post(f"/api/devices/{pending['device']['id']}/approve", headers=ORIGIN)
            for endpoint in ['memory', 'sheets']:
                assert tablet.get('/api/assistant/'+endpoint).status_code == 403
            assert len(tablet.get('/api/voice/history').json()) == 1
            assert 'sensitive reply' not in tablet.get('/api/voice/status').text
            assert 'sensitive reply' not in tablet.put('/api/voice/alerts', json={'enabled': False}, headers=ORIGIN).text
        assert owner.delete('/api/assistant/memory/'+identity, headers=ORIGIN).status_code == 200
        assert owner.get('/api/assistant/memory').json()['facts'] == []
        app.state.assistant.voice_context('hello')
        owner.delete('/api/voice/history', headers=ORIGIN)
        assert owner.get('/api/assistant/memory').json()['lastContext'] is None


@pytest.mark.usefixtures('jarvis_sdk_transport')
def test_explicit_remember_saves_without_model_and_model_receives_personal_data(personal):
    client = Mock()
    dispatch = Mock(side_effect=lambda name, args: tool(personal, name, args, heard='Remember that I like jazz'))
    context = personal.voice_context('music')['personal']
    assert respond(client, 'Remember that I like jazz', voice_tools(Mock()), dispatch, personal_context=context) == 'Remembered, sir.'
    client.responses.create.assert_not_called()
    client.responses.create.return_value = SimpleNamespace(output_text='Jazz, sir.', output=[SimpleNamespace(type='message', content=[])])
    context = personal.voice_context('music')['personal']
    assert respond(client, 'What music do I like?', voice_tools(Mock()), dispatch, personal_context=context) == 'Jazz, sir.'
    request = client.responses.create.call_args.kwargs
    assert 'I like jazz' in json.dumps(request['input'])
    assert 'access-fixture' not in json.dumps(request, default=str)


@pytest.mark.usefixtures('jarvis_sdk_transport')
def test_agent_discovers_registered_ranges_then_reads_and_prepares_once(personal):
    identity = register(personal)
    client = Mock()
    def call(name, args, key):
        return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id=key)
    def output(*items, text=''):
        return SimpleNamespace(output=list(items), output_text=text)
    client.responses.create.side_effect = [output(call('read_sheet', {'id': identity}, 'undiscovered'), call('list_sheets', {}, 'list')),
        output(call('read_sheet', {'id': identity}, 'read')),
        output(call('propose_sheet_update', {'id': identity, 'values': [['next']]}, 'preview')),
        output(text='Change prepared, sir. Review it in Sheets.')]
    dispatch = Mock(side_effect=lambda name, args: tool(personal, name, args))
    assert 'prepared' in respond(client, 'Read my tracker and change the first cell to next.', voice_tools(Mock()), dispatch)
    assert [call.args[0] for call in dispatch.call_args_list] == ['list_sheets', 'read_sheet', 'propose_sheet_update']
    assert personal.google.sheet_values.call_count == 1
    assert len(personal.sheets.proposals) == 1


def test_voice_monitor_delivers_private_tools_without_holding_voice_lock(personal):
    from backend.voice import VoiceService
    voice = VoiceService(None, Mock(), Mock())
    voice.assistant = personal
    voice.phase, voice.generation = 'thinking', 1
    voice.stop_event = threading.Event()
    process, pipe = Mock(), Mock()
    voice.process = process
    identity = register(personal)
    events = [
        {'type': 'action', 'id': 'context', 'name': 'assistant_context', 'arguments': {'heard': 'Check my tracker'}},
        {'type': 'action', 'id': 'read', 'name': 'read_sheet', 'arguments': {'id': identity}},
        {'type': 'exchange', 'heard': 'Check my tracker', 'reply': 'Tracker checked.'}]
    process.is_alive.side_effect = lambda: bool(events) or voice.phase == 'thinking'
    pipe.poll.side_effect = lambda *args: bool(events)
    def recv():
        event = events.pop(0)
        if not events:
            voice.phase = 'speaking'
        return event
    pipe.recv.side_effect = recv
    def read(*args, **kwargs):
        def check():
            with voice.lock:
                pass
        thread = threading.Thread(target=check)
        thread.start();thread.join(timeout=1)
        assert not thread.is_alive(), 'Network reads must leave voice stop/lock responsive'
        return {'values': [['Private value']]}
    personal.google.sheet_values.side_effect = read
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        voice._monitor(1, process, pipe)
    results = [call.args[0] for call in pipe.send.call_args_list]
    assert results[1]['result']['values'] == [['Private value']]
    assert voice.history.recent()[0]['kind'] == 'personal'
    assert voice.history.recent()[0]['action']['arguments'] == {}


def full_registration(service):
    return service.sheets.register(service.account_id(), SheetRegistration(name='Whole file', spreadsheetId='fixture_sheet_456', access='spreadsheet'))


def discovery(service, editable=True):
    service.sheets.set_discovery(service.account_id(), True)
    service.google.search_sheets.return_value = {'files': [{'id': 'fixture_sheet_789', 'name': 'Planner',
        'mimeType': 'application/vnd.google-apps.spreadsheet', 'capabilities': {'canEdit': editable}}]}
    return tool(service, 'search_sheets', {'query': 'Planner', 'pageToken': None})['sheets'][0]['id']


def test_full_spreadsheet_grant_allows_any_bounded_tab_but_preserves_legacy_range(personal):
    identity = full_registration(personal)
    with pytest.raises(ValueError, match='bounded'):
        personal.sheet_read(identity)
    for area in ["'Other tab'!K101:L102", "'Owner''s tab'!A1:B2"]:
        assert personal.sheet_read(identity, area=area)['sheet']['range'] == area
        preview = personal.sheet_propose(identity, [['change']], area)['proposalId']
        personal.sheet_apply(preview)
        assert personal.google.sheet_values.call_args.args[1]['range'] == area
    legacy = register(personal)
    with pytest.raises(ValueError, match='saved range'):
        personal.sheet_read(legacy, area="'Other tab'!A1:B2")
    with pytest.raises(ValueError):
        personal.sheet_propose(identity, [['change']], 'Sheet1!A1:Z1000')
    with pytest.raises(ValueError):
        SheetRegistration(**{**REGISTRATION, 'access': 'spreadsheet'})


def test_metadata_discovery_is_paged_without_values_or_unsupported_tab_claims(personal):
    identity = full_registration(personal)
    personal.google.sheet_metadata.return_value = {'sheets': [{'properties': {'sheetId': i, 'title': f'Tab {i}',
        'sheetType': 'GRID', 'gridProperties': {'rowCount': 1000, 'columnCount': 40}}} for i in range(51)]}
    result = tool(personal, 'list_sheet_tabs', {'id': identity, 'offset': 0})
    assert len(result['tabs']) == 50 and result['nextOffset'] == 50
    assert tool(personal, 'list_sheet_tabs', {'id': identity, 'offset': 50})['tabs'][0]['title'] == 'Tab 50'
    personal.google.sheet_values.assert_not_called()
    google = GoogleClient()
    with patch.object(google, '_request', return_value={}) as request:
        google.sheet_metadata('token', personal.sheets.get(personal.account_id(), identity))
    assert request.call_args.args[0].endswith('/fixture_sheet_456')
    assert 'values' not in request.call_args.kwargs['query']['fields']
    personal.google.sheet_metadata.return_value = {'sheets': [{'properties': {'title': 'Chart', 'sheetType': 'OBJECT'}}]}
    assert not personal.sheet_tabs(identity)['tabs'][0]['supported']
    with pytest.raises(ValueError):
        personal.sheet_tabs(identity, offset=True)


def test_drive_search_keeps_fixed_mime_filter_and_escapes_query():
    from backend.agent.google import FILES_URL
    google = GoogleClient()
    with patch.object(google, '_request', return_value={}) as request:
        google.search_sheets('fixture', "x' or trashed = true or name contains '\\", 'next-fixture')
    assert request.call_args.args == (FILES_URL,)
    query = request.call_args.kwargs['query']
    assert query['q'].startswith("mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false and name contains '")
    assert "x\\' or" in query['q'] and query['q'].endswith("\\\\'")
    assert query['pageToken'] == 'next-fixture' and query['pageSize'] == 20
    with pytest.raises(ValueError):
        google.search_sheets('fixture', 'bad\nquery')
    with pytest.raises(GoogleError, match='Unsupported'):
        google._request('https://www.googleapis.com/drive/v3/files/arbitrary')


@pytest.mark.parametrize('change', ['expiry', 'account', 'cancel', 'discovery', 'read-only'])
def test_search_handles_are_account_bound_temporary_revocable_and_permission_aware(personal, change):
    identity = discovery(personal, editable=change != 'read-only')
    area = "'Sheet1'!A1:B2"
    assert personal.sheet_read(identity, area=area)['values']
    if change == 'expiry':
        personal.sheets.discovered[identity]['expiresAt'] = 0
    elif change == 'account':
        personal.vault['account']['id'] = 'different-account'
    elif change == 'cancel':
        personal._cancel()
    elif change == 'discovery':
        personal.sheets.set_discovery(personal.account_id(), False)
    with pytest.raises(GoogleError):
        personal.sheet_propose(identity, [['new']], area)
    assert personal.sheets.proposals == {}
    assert all(row['id'] != identity for row in personal.sheets.all(personal.account_id()))


def test_discovery_requires_opt_in_scope_and_live_authorization(personal):
    from backend.agent.google import DRIVE_SCOPE
    with pytest.raises(GoogleError, match='discovery'):
        personal.search_sheets('Planner')
    personal.sheets.set_discovery(personal.account_id(), True)
    personal.vault['scopes'].remove(DRIVE_SCOPE)
    with pytest.raises(GoogleError, match='Drive metadata'):
        personal.search_sheets('Planner')
    personal.vault['scopes'].append(DRIVE_SCOPE)
    personal.google.search_sheets.side_effect = lambda *args: (personal._cancel() or {'files': []})
    with pytest.raises(GoogleError, match='stopped'):
        personal.search_sheets('Planner')
    assert personal.sheets.discovered == {}
    personal.google.search_sheets.reset_mock(side_effect=True)
    personal.access, personal.access_until = 'access-fixture', time.monotonic() + 600
    with pytest.raises(GoogleError, match='stopped'):
        personal.search_sheets('Planner', allowed=lambda: False)
    personal.google.search_sheets.assert_not_called()


@pytest.mark.usefixtures('jarvis_sdk_transport')
def test_agent_searches_tabs_reads_and_prepares_in_one_bounded_turn(personal):
    personal.sheets.set_discovery(personal.account_id(), True)
    personal.google.search_sheets.return_value = {'files': [{'id': 'fixture_sheet_789', 'name': 'Planner',
        'mimeType': 'application/vnd.google-apps.spreadsheet', 'capabilities': {'canEdit': True}}]}
    personal.google.sheet_metadata.return_value = {'sheets': [{'properties': {'title': 'Sheet1', 'sheetType': 'GRID', 'gridProperties': {'rowCount': 1000, 'columnCount': 20}}}]}
    client = Mock()
    found = {}
    def output(name=None, arguments=None):
        return SimpleNamespace(output=[SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=name)] if name else [], output_text='' if name else 'Change prepared, sir.')
    def responses(**kwargs):
        turn = client.responses.create.call_count
        if turn == 1:
            return output('search_sheets', {'query': 'Planner', 'pageToken': None})
        if turn == 2:
            return output('list_sheet_tabs', {'id': found['id'], 'offset': 0})
        if turn == 3:
            return output('read_sheet', {'id': found['id'], 'range': "'Sheet1'!A1:B2"})
        if turn == 4:
            return output('propose_sheet_update', {'id': found['id'], 'range': "'Sheet1'!A1:B2", 'values': [['next']]})
        return output()
    client.responses.create.side_effect = responses
    def dispatch(name, args):
        result = tool(personal, name, args)
        if name == 'search_sheets':
            found['id'] = result['sheets'][0]['id']
        return result
    assert 'prepared' in respond(client, 'Find Planner and update its first cell.', voice_tools(Mock()), dispatch,
        personal_context=personal.voice_context('Planner')['personal'])
    assert client.responses.create.call_count == 5
    assert len(personal.sheets.proposals) == 1 and personal.google.sheet_values.call_count == 1


def test_search_and_full_sheet_routes_require_direct_owner_origin_and_concrete_cells(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
        service = app.state.assistant
        service.vault = {'account': {'id': 'owner-1', 'email': 'qa@example.test'}, 'refresh': 'fixture', 'scopes': list(SCOPES)}
        service.enabled = True
        service.google = Mock()
        service.google.sheet_values.return_value = {'values': [['fixture']]}
        with patch.object(service, '_access', return_value='fixture'), patch.object(service, 'unlocked', return_value=True), patch.object(service, 'stop_voice') as stop:
            assert owner.put('/api/assistant/sheets/discovery', json={'enabled': True}, headers=ORIGIN).status_code == 200
            assert stop.called and owner.get('/api/assistant/sheets').json()['discoveryEnabled']
            body = {'name': 'Whole file', 'spreadsheetId': 'fixture_sheet_456', 'access': 'spreadsheet', 'range': None}
            identity = owner.post('/api/assistant/sheets', json=body, headers=ORIGIN).json()['id']
            area = "'Sheet1'!K101:L102"
            result = owner.post(f'/api/assistant/sheets/{identity}/read', json={'range': area}, headers=ORIGIN)
            assert result.status_code == 200 and result.json()['sheet']['range'] == area
            assert owner.post(f'/api/assistant/sheets/{identity}/propose', json={'range': area, 'values': [['change']]}, headers=ORIGIN).status_code == 200
            service.google.search_sheets.return_value = {'files': []}
            assert owner.post('/api/assistant/sheets/search', json={'query': 'Planner'}, headers=ORIGIN).status_code == 200
            assert owner.post('/api/assistant/sheets/search', json={'query': 'Planner'}, headers={'origin': 'https://evil.example'}).status_code == 403
            assert owner.put('/api/assistant/sheets/discovery', json={'enabled': False}, headers={'origin': 'https://evil.example'}).status_code == 403
            with TestClient(app, base_url='https://testserver', client=('192.168.2.20', 4001)) as tablet:
                pending = tablet.post('/api/device/request', json={'name': 'Full sheet QA'}, headers=ORIGIN).json()
                owner.post(f"/api/devices/{pending['device']['id']}/approve", headers=ORIGIN)
                for endpoint, data in [('sheets/search', {'query': ''}), (f'sheets/{identity}/tabs', {'offset': 0}),
                                       (f'sheets/{identity}/read', {'range': area}), (f'sheets/{identity}/propose', {'range': area, 'values': [['change']]})]:
                    assert tablet.post('/api/assistant/'+endpoint, json=data, headers=ORIGIN).status_code == 403
            assert owner.put('/api/assistant/sheets/discovery', json={'enabled': False}, headers=ORIGIN).status_code == 200
            assert service.sheets.proposals == {} and not service.sheets.discovery_enabled('owner-1')
