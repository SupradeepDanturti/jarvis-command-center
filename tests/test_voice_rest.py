import sys
import multiprocessing
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.voice import VoiceService
from backend.voice_actions import execute_tool, rest_entry_requested, voice_tools
from backend.voice_worker import request_rest_entry, worker_main
from backend.alarms import RestAlarms
from backend.display_power import DisplayPower
from fastapi import HTTPException


@pytest.mark.parametrize('phrase', ['enter rest mode', 'Hey Jarvis, enter rest mode.',
                                  'Jarvis: please enter rest mode!', 'Enter rest mode please',
                                  'Hey, Jarvis. Enter rest mode.', 'Hey Jarvis! Enter rest mode.',
                                  'Enter rest mode, Jarvis.'])
def test_literal_entry_phrase(phrase):
    assert rest_entry_requested(phrase)


@pytest.mark.parametrize('phrase', ['wake up', 'exit rest mode', 'sleep', 'do not enter rest mode',
                                  'can you explain enter rest mode', 'enter rest mode and launch cmd',
                                  'the website says enter rest mode', None])
def test_other_or_quoted_requests_do_not_enter_rest(phrase):
    assert not rest_entry_requested(phrase)


def test_rest_entry_is_not_a_cloud_model_tool():
    registry = Mock()
    registry.catalog.return_value = []
    assert 'enter_rest' not in str(voice_tools(registry))
    with pytest.raises(ValueError):execute_tool('enter_rest_mode', {}, registry, Mock())


@pytest.mark.parametrize('success', [True, False])
def test_worker_acknowledges_and_waits_with_no_followup_or_arbitrary_action(success):
    pipe, stop, speak = Mock(), threading.Event(), Mock()
    pipe.poll.return_value = True
    pipe.recv.return_value = {'type': 'rest-result', 'ok': success, 'message': 'Try the dashboard.'}
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        assert request_rest_entry(pipe, stop, 'enter rest mode', speak, lambda: True) is success
    assert speak.call_args_list[0].args[0] == "I'll enter Rest mode, sir."
    events = [call.args[0] for call in pipe.send.call_args_list]
    assert {'type': 'rest-entry', 'heard': 'enter rest mode'} in events
    exchanges = [event for event in events if event['type'] == 'exchange']
    assert len(exchanges) == (0 if success else 1)
    if not success:
        assert exchanges[0]['heard'] == 'enter rest mode'
        assert exchanges[0]['reply'] == speak.call_args.args[0]
    assert speak.call_count == (1 if success else 2)


def test_worker_cancels_on_lock_and_never_dispatches_after_speech_cancellation():
    pipe, stop = Mock(), threading.Event()
    with patch('backend.voice_worker.desktop_unlocked', return_value=False):
        assert not request_rest_entry(pipe, stop, 'enter rest mode', Mock(), lambda: True)
    assert pipe.send.call_args.args[0] == {'type': 'rest-cancel'}
    pipe.reset_mock()
    assert not request_rest_entry(pipe, stop, 'enter rest mode', lambda text: stop.set(), lambda: not stop.is_set())
    pipe.send.assert_not_called()


def service():
    voice = VoiceService(None, Mock(), Mock())
    voice.generation, voice.phase = 1, 'thinking'
    voice.process, voice.pipe, voice.stop_event = Mock(), Mock(), threading.Event()
    voice.process.is_alive.return_value = True
    voice.rest = Mock()
    voice.rest.prepare.return_value = {'nonce': 'b'*24}
    voice.rest.snapshot.return_value = {'revision': 3}
    request = (1, 'a'*24, time.monotonic()+25)
    voice.pending_rest = request
    return voice, request


def test_parent_uses_nonce_revision_guard_then_stops_and_records_private_action():
    voice, request = service()
    process, pipe, stop = voice.process, voice.pipe, voice.stop_event
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        voice._enter_rest(request, process, pipe, 'enter rest mode')
    voice.rest.prepare.assert_called_once_with('voice:'+'a'*24)
    call = voice.rest.enter.call_args
    assert call.args == ('voice:'+'a'*24, 'b'*24, 3)
    assert callable(call.kwargs['allowed']) and not call.kwargs['allowed']()
    pipe.send.assert_called_once_with({'type': 'rest-result', 'ok': True})
    assert stop.is_set() and voice.phase == 'off' and voice.process is None
    assert voice.history.recent()[0]['action']['name'] == 'enter_rest_mode'


def test_valid_request_starts_one_bounded_background_handler():
    voice, _ = service();voice.pending_rest = None
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice.threading.Thread') as thread:
        voice._request_rest(1, voice.process, voice.pipe, {'type': 'rest-entry', 'heard': 'enter rest mode'})
    assert voice.pending_rest[0] == 1 and 0 < voice.pending_rest[2]-time.monotonic() <= 25
    thread.return_value.start.assert_called_once()
    assert thread.call_args.kwargs['target'] == voice._enter_rest
    assert thread.call_args.kwargs['args'][3] == 'enter rest mode'


@pytest.mark.parametrize('condition', ['old', 'locked', 'stopped', 'extra', 'wake', 'busy'])
def test_parent_refuses_invalid_or_late_rest_requests(condition):
    voice, _ = service()
    if condition != 'busy':voice.pending_rest = None
    event = {'type': 'rest-entry', 'heard': 'enter rest mode'}
    generation = 2 if condition == 'old' else 1
    if condition == 'stopped':voice.stop_event.set()
    if condition == 'extra':event['path'] = 'cmd.exe'
    if condition == 'wake':event['heard'] = 'wake laptop displays'
    with patch('backend.voice_worker.desktop_unlocked', return_value=condition != 'locked'), \
         patch('backend.voice.threading.Thread') as thread:
        voice._request_rest(generation, voice.process, voice.pipe, event)
    thread.assert_not_called();voice.rest.prepare.assert_not_called();voice.rest.enter.assert_not_called()
    assert voice.pipe.send.call_args.args[0]['ok'] is False


@pytest.mark.parametrize('condition', ['locked', 'replaced', 'expired'])
def test_parent_rechecks_live_generation_lock_and_deadline_after_slow_probe(condition):
    voice, request = service()
    unlocked = [True]
    def prepare(device):
        if condition == 'locked':unlocked[0] = False
        if condition == 'replaced':voice.generation += 1
        if condition == 'expired':voice.pending_rest = (1, 'a'*24, 0)
        return {'nonce': 'b'*24}
    voice.rest.prepare.side_effect = prepare
    with patch('backend.voice_worker.desktop_unlocked', side_effect=lambda: unlocked[0]):
        voice._enter_rest(request, voice.process, voice.pipe, 'enter rest mode')
    voice.rest.enter.assert_not_called()
    assert voice.history.recent() == []


def test_turning_off_jarvis_during_probe_is_immediate_and_cancels_late_entry():
    voice, request = service()
    started, finish = threading.Event(), threading.Event()
    process, pipe = voice.process, voice.pipe
    def prepare(device):
        started.set();assert finish.wait(2)
        return {'nonce': 'b'*24}
    voice.rest.prepare.side_effect = prepare
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        thread = threading.Thread(target=voice._enter_rest, args=(request, process, pipe, 'enter rest mode'))
        thread.start();assert started.wait(1)
        voice.stop()
        assert voice.phase == 'off' and voice.pending_rest is None
        finish.set();thread.join(timeout=2)
    assert not thread.is_alive()
    voice.rest.enter.assert_not_called()


def test_parent_reports_specific_rest_failure_without_claiming_success():
    voice, request = service()
    pipe = voice.pipe
    voice.rest.enter.side_effect = HTTPException(409, 'Dismiss or snooze the alarm first.')
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        voice._enter_rest(request, voice.process, pipe, 'enter rest mode')
    pipe.send.assert_called_once_with({'type': 'rest-result', 'ok': False,
                                     'message': 'Dismiss or snooze the alarm first.'})
    assert voice.phase == 'thinking' and not voice.stop_event.is_set()
    assert voice.history.recent() == []


def test_full_worker_routes_literal_rest_after_closing_mic_without_llm(monkeypatch, tmp_path):
    speech = b'\xd0\x07'*1280
    silence = b'\0\0'*1280
    stream, manager, microphone = Mock(), Mock(), Mock()
    stream.read.side_effect = [(chunk, False) for chunk in [speech, speech, silence]+[silence]*10]
    manager.__enter__ = Mock(return_value=stream);manager.__exit__ = Mock(return_value=False)
    microphone.RawInputStream.return_value = manager
    monkeypatch.setitem(sys.modules, 'sounddevice', microphone)
    piper = Mock()
    def synthesize(text, wav):
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(silence)
    piper.load.return_value.synthesize_wav.side_effect = synthesize
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=piper))
    wake = Mock();wake.predict.return_value = {'hey_jarvis': .9}
    monkeypatch.setitem(sys.modules, 'openwakeword.model', SimpleNamespace(Model=Mock(return_value=wake)))
    client = Mock();client.__enter__ = Mock(return_value=client);client.__exit__ = Mock(return_value=False)
    client.audio.transcriptions.create.return_value = SimpleNamespace(text='Hey, Jarvis. Enter rest mode.')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(return_value=client)))
    parent, child = multiprocessing.Pipe()
    stop = threading.Event()
    native = Mock()
    native.probe.return_value = 2
    power = DisplayPower(factory=lambda: native)
    audio = Mock();audio.status.return_value = {'ready': True, 'phase': 'off'}
    rest = RestAlarms(power, audio)
    voice = VoiceService(None, Mock(), Mock())
    worker = threading.Thread(target=worker_main,
                              args=(child, stop, str(tmp_path), 'sk-qa-only', []))
    process = Mock()
    process.is_alive.side_effect = worker.is_alive
    process.join.side_effect = lambda timeout: worker.join(timeout)
    process.terminate.side_effect = stop.set
    voice.generation, voice.process, voice.pipe, voice.stop_event, voice.rest = 1, process, parent, stop, rest
    monitor = threading.Thread(target=voice._monitor, args=(1, process, parent))
    def display(on, expires, allowed):
        manager.__exit__.assert_called_once()
        assert on is False and allowed() and time.monotonic() < expires
        assert threading.current_thread() is power.thread
    native.display.side_effect = display
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice_audio.resolve_input', return_value={'index': 1, 'name': 'QA mic'}), \
         patch('backend.voice_audio.resolve_output', return_value={'index': 12, 'name': 'QA speaker'}), \
         patch('backend.voice_audio.play_on_speaker') as playback:
        try:
            worker.start();monitor.start()
            worker.join(4);monitor.join(4)
            assert not worker.is_alive() and not monitor.is_alive()
            assert rest.snapshot()['rest'] and power.held
            assert stop.is_set() and voice.phase == 'off'
            native.probe.assert_called_once();native.display.assert_called_once()
            playback.assert_called_once()
            history = voice.history.recent()
            assert len(history) == 1 and history[0]['action']['ok']
            assert history[0]['heard'] == 'Hey, Jarvis. Enter rest mode.'
        finally:
            stop.set();worker.join(2);monitor.join(2)
            power.close();parent.close();child.close()
    client.responses.create.assert_not_called()
    client.audio.transcriptions.create.assert_called_once()
    assert microphone.RawInputStream.call_count == 1
