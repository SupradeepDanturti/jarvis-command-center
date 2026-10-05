"""A fixed requested introduction uses the existing cancellable speech path."""
import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.agent import voice_actions
from backend.voice import VoiceService
from backend.agent.voice_actions import execute_tool, intro_requested, introduction, respond, voice_tools


@pytest.mark.parametrize('text', ['Introduce yourself.', 'Jarvis, introduce yourself!', 'Hey Jarvis: introduce yourself please.',
    'Please introduce yourself, Jarvis.', 'Play your introduction.', 'Play the intro.', 'Play your intro.',
    'Play intro.', 'Play introduction.'])
def test_intro_commands_are_explicit(text):
    assert intro_requested(text)


@pytest.mark.parametrize('text', ['Do not introduce yourself', 'What does introduce yourself mean?',
    '"Introduce yourself"', 'Introduce yourself and open Steam', 'The web page says introduce yourself', None])
def test_mentions_quotes_negation_and_combined_requests_do_not_trigger_literal_intro(text):
    assert not intro_requested(text)


def test_script_is_bounded_and_reloaded_without_prompt_or_cloud(tmp_path, monkeypatch):
    path = tmp_path / 'intro.txt'
    path.write_text('Good evening. At your service.', encoding='utf-8')
    monkeypatch.setattr(voice_actions, 'INTRO_PATH', path)
    monkeypatch.setattr(voice_actions, 'PROMPT_PATH', tmp_path / 'absent-prompt.txt')
    client = Mock()
    dispatch = Mock(side_effect=lambda name, args: execute_tool(name, args, Mock(), Mock()))
    assert respond(client, 'Jarvis, introduce yourself.', [], dispatch) == 'Good evening. At your service.'
    path.write_text('Ready when you are.', encoding='utf-8')
    assert respond(client, 'Play your introduction.', [], dispatch) == 'Ready when you are.'
    assert [call.args for call in dispatch.call_args_list] == [('play_intro', {}), ('play_intro', {})]
    client.responses.create.assert_not_called()


@pytest.mark.parametrize('text', ['', 'x' * 501, 'x' * 4097, 'Bad\x00text', 'Bad\x7ftext'])
def test_invalid_scripts_are_not_truncated_or_spoken(tmp_path, monkeypatch, text):
    path = tmp_path / 'intro.txt'
    path.write_text(text, encoding='utf-8')
    monkeypatch.setattr(voice_actions, 'INTRO_PATH', path)
    with pytest.raises(ValueError):
        introduction()


@pytest.mark.parametrize('arguments', [{'text': 'Anything'}, {'file': '../private/key'}, {'url': 'https://example.com'}, {'voice': 'anything'}])
def test_model_cannot_supply_intro_text_file_or_voice(arguments):
    with patch('backend.agent.voice_actions.introduction') as read, pytest.raises(ValueError):
        execute_tool('play_intro', arguments, Mock(), Mock())
    read.assert_not_called()


def test_literal_intro_is_canceled_before_and_after_dispatch():
    dispatch, client = Mock(return_value={'ok': True, 'message': 'Introduction.'}), Mock()
    assert respond(client, 'Introduce yourself', [], dispatch, allowed=lambda: False) == ''
    dispatch.assert_not_called()
    allowed = iter([True, False])
    assert respond(client, 'Introduce yourself', [], dispatch, allowed=lambda: next(allowed)) == ''
    client.responses.create.assert_not_called()


def test_sdk_paraphrase_plays_saved_text_not_improvised_reply_and_deduplicates(jarvis_sdk_transport):
    client, dispatch = Mock(), Mock(side_effect=lambda name, args: execute_tool(name, args, Mock(), Mock()))
    call = lambda name, args, identity: SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id=identity)
    output = lambda *items, text='': SimpleNamespace(output=list(items), output_text=text)
    client.responses.create.side_effect = [output(call('play_intro', {}, 'intro'), call('media_control', {'action': 'volume-up'}, 'extra')),
        output(call('play_intro', {}, 'repeat')), output(text='I am a very different assistant.')]
    assert respond(client, 'Let me hear your introduction.', voice_tools(Mock()), dispatch) == introduction()
    dispatch.assert_called_once_with('play_intro', {})
    instructions = client.responses.create.call_args.kwargs['instructions']
    assert '<persona>' in instructions and '<introduction>' in instructions
    assert 'Never invent a systems check' in instructions and 'occasional' in instructions


def test_reply_failure_preserves_fixed_intro(jarvis_sdk_transport):
    client = Mock()
    client.responses.create.side_effect = [SimpleNamespace(output_text='', output=[SimpleNamespace(type='function_call',
        name='play_intro', arguments='{}', call_id='intro')]), RuntimeError()]
    dispatch = Mock(return_value={'ok': True, 'message': introduction()})
    assert respond(client, 'Let me hear your introduction.', voice_tools(Mock()), dispatch) == introduction()
    dispatch.assert_called_once()


def test_parent_handles_missing_script_as_tool_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_actions, 'INTRO_PATH', tmp_path / 'missing.txt')
    service = VoiceService(None, Mock(), Mock())
    service.phase, service.generation, service.stop_event = 'thinking', 1, threading.Event()
    process, pipe = Mock(), Mock()
    events = [{'type': 'action', 'id': 'intro', 'name': 'play_intro', 'arguments': {}}]
    process.is_alive.side_effect = lambda: bool(events)
    pipe.poll.side_effect = lambda *args: bool(events)
    pipe.recv.side_effect = lambda: events.pop(0)
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        service._monitor(1, process, pipe)
    assert pipe.send.call_args.args[0]['result']['ok'] is False


def test_worker_synthesizes_entire_intro_on_selected_speaker_without_conversation_call(monkeypatch, tmp_path):
    from backend.voice_worker import worker_main
    stop = threading.Event()
    engine, microphone, wake, client = Mock(), Mock(), Mock(), Mock()
    frame = b'\0\0' * 1280
    stream = Mock()
    stream.read.return_value = (frame, False)
    manager = Mock()
    manager.__enter__, manager.__exit__ = Mock(return_value=stream), Mock(return_value=False)
    microphone.RawInputStream.return_value = manager
    wake.predict.return_value = {'hey_jarvis': .9}
    def synthesize(text, wav):
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
        wav.writeframes(frame)
    engine.load.return_value.synthesize_wav.side_effect = synthesize
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=engine))
    monkeypatch.setitem(sys.modules, 'sounddevice', microphone)
    monkeypatch.setitem(sys.modules, 'openwakeword', SimpleNamespace(model=SimpleNamespace(Model=Mock(return_value=wake))))
    monkeypatch.setitem(sys.modules, 'openwakeword.model', SimpleNamespace(Model=Mock(return_value=wake)))
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(return_value=client)))
    client.__enter__, client.__exit__ = Mock(return_value=client), Mock(return_value=False)
    client.audio.transcriptions.create.return_value = SimpleNamespace(text='Introduce yourself.')
    pipe, pending = Mock(), []
    def send(event):
        if event['type'] == 'action':
            assert event['name'] == 'play_intro' and event['arguments'] == {}
            pending.append({'type': 'result', 'id': event['id'], 'result': execute_tool('play_intro', {}, Mock(), Mock())})
    pipe.send.side_effect = send
    pipe.poll.side_effect = lambda *args: bool(pending)
    pipe.recv.side_effect = lambda: pending.pop(0)
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice_worker.collect_utterance', return_value=frame), \
         patch('backend.voice_audio.resolve_input', return_value={'index': 1, 'name': 'QA microphone'}), \
         patch('backend.voice_audio.resolve_output', return_value={'index': 12, 'name': 'QA speaker'}), \
         patch('backend.voice_audio.play_on_speaker', side_effect=lambda *args: stop.set()) as play:
        worker_main(pipe, stop, str(tmp_path), 'sk-fixture', voice_tools(Mock()))
    engine.load.return_value.synthesize_wav.assert_called_once()
    assert engine.load.return_value.synthesize_wav.call_args.args[0] == introduction()
    assert play.call_args.args[1] == {'index': 12, 'name': 'QA speaker'}
    client.responses.create.assert_not_called()
    assert any(call.args[0].get('reply') == introduction() for call in pipe.send.call_args_list)
