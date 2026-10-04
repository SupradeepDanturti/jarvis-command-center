from datetime import datetime, timezone
import io
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wave

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.voice_alerts import HardwareAlerts
from backend.voice_audio import outputs, resolve_output, play_on_speaker
from backend.voice_history import VoiceHistory
from backend.voice_worker import worker_main


def snapshot(t, cpu=90, memory=90, gpu=70):
    return {'timestamp': datetime.fromtimestamp(t, timezone.utc).isoformat(),
            'cpu': {'usage': cpu}, 'memory': {'percent': memory}, 'gpu': {'temperature': gpu}}


def test_thresholds_consecutive_samples_global_hour_cooldown_and_restart(tmp_path):
    path = tmp_path / 'alerts.json'
    policy = HardwareAlerts(path)
    for t in (1000, 1001):
        assert policy.evaluate(snapshot(t), wall=t) is None
    text = policy.evaluate(snapshot(1002), wall=1002)
    assert 'processor load is at 90 percent' in text
    assert 'memory usage is at 90 percent' in text
    assert 'GPU temperature is at 70 degrees Celsius' in text
    for t in (1003, 1303, 1500, 4601):
        assert policy.evaluate(snapshot(t), wall=t) is None
    restored = HardwareAlerts(path)
    for t in (4599, 4600, 4601):
        assert restored.evaluate(snapshot(t, cpu=95, memory=20, gpu=50), wall=t) is None, 'A different metric/restart cannot bypass the hour'
    assert restored.evaluate(snapshot(4602, cpu=95, memory=20, gpu=50), wall=4602)
    assert HardwareAlerts(path).last_alert_wall == 4602


def test_stale_missing_invalid_and_duplicate_readings_never_trigger():
    policy = HardwareAlerts()
    assert policy.evaluate(None, wall=1000) is None
    assert policy.evaluate({'timestamp': 'bad'}, wall=1000) is None
    for _ in range(10):
        assert policy.evaluate(snapshot(1000), wall=1000) is None
    assert policy.evaluate(snapshot(1000), wall=1010) is None
    for t in (1011, 1012, 1013):
        assert policy.evaluate(snapshot(t, float('nan'), None, 999), wall=t) is None


def test_explicit_realtek_speaker_selection_never_uses_headphone_default():
    devices = [{'name': name, 'max_output_channels': 2, 'hostapi': 0} for name in
               ['Microsoft Sound Mapper - Output', 'Headphones (Realtek Audio)',
                'Speakers (USB Audio)', 'Speakers (Realtek Audio)']]
    with patch('sounddevice.query_devices', return_value=devices), \
         patch('sounddevice.query_hostapis', return_value={'name': 'MME'}), \
         patch('sounddevice.check_output_settings'):
        choices = outputs()
        assert [d['name'] for d in choices] == ['Speakers (USB Audio)', 'Speakers (Realtek Audio)']
        assert resolve_output()['index'] == 3
        assert resolve_output(choices[0]['id'])['index'] == 2
        with pytest.raises(ValueError):
            resolve_output('headphone-or-missing-id')
    with patch('backend.voice_audio.outputs', return_value=[]), pytest.raises(ValueError, match='Headphones will not be used'):
        resolve_output()


def test_speaker_stream_uses_selected_endpoint_and_cancels_between_chunks(monkeypatch):
    import sys
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
        wav.writeframes(b'\0\0' * 6000)
    stream, manager = Mock(), Mock()
    manager.__enter__ = Mock(return_value=stream)
    manager.__exit__ = Mock(return_value=False)
    sound = SimpleNamespace(RawOutputStream=Mock(return_value=manager))
    monkeypatch.setitem(sys.modules, 'sounddevice', sound)
    permitted = iter([True, True, False])
    play_on_speaker(audio, {'index': 12}, lambda: next(permitted))
    sound.RawOutputStream.assert_called_once_with(device=12, samplerate=22050, channels=1, dtype='int16')
    assert stream.write.call_count == 1


def test_speaker_and_alert_preferences_authorization_and_persistence(tmp_path):
    app = create_app(pairing_code='ABCD1234', voice_dir=tmp_path)
    origin = {'origin': 'https://testserver'}
    with TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000)) as owner:
        assert owner.get('/api/voice/outputs').status_code == 401
        assert owner.put('/api/voice/alerts', json={'enabled': False}, headers=origin).status_code == 401
        owner.post('/api/pair', json={'code': 'ABCD1234'}, headers=origin)
        with patch.object(app.state.voice, 'audio_inputs', return_value=[{'id': 'real-speaker', 'name': 'Speakers'}]):
            assert owner.put('/api/voice/output', json={'id': 'fake'}, headers=origin).status_code == 400
            assert owner.put('/api/voice/output', json={'id': 'real-speaker'}, headers=origin).status_code == 200
            assert owner.put('/api/voice/output', json={'id': 'real-speaker'}, headers={'origin': 'https://evil.example'}).status_code == 403
        assert owner.put('/api/voice/alerts', json={'enabled': 'false'}, headers=origin).status_code == 422
        assert owner.put('/api/voice/alerts', json={'enabled': False}, headers=origin).status_code == 200
        owner.put('/api/voice/followup', json={'seconds': 30}, headers=origin)
    saved = create_app(pairing_code='ABCD1234', voice_dir=tmp_path).state.voice
    assert saved.output_id == 'real-speaker'
    assert saved.alerts_enabled is False
    assert saved.followup_seconds == 30
    saved.process = Mock()
    saved.process.is_alive.return_value = True
    saved.pipe = Mock()
    saved.set_alerts(True)
    saved.pipe.send.assert_called_once_with({'type': 'alerts', 'enabled': True})
    saved.process.terminate.assert_not_called()


def test_alert_delivery_requires_live_worker_idle_unlocked_and_enabled():
    app = create_app(pairing_code='ABCD1234')
    service = app.state.voice
    service.generation = 3
    service.stop_event = threading.Event()
    service.alert_policy = Mock()
    service.alert_policy.evaluate.return_value = 'Sir, processor load is at 95 percent.'
    pipe = Mock()
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        for phase in ['off', 'preview', 'thinking', 'speaking', 'followup', 'recording']:
            service.phase = phase
            service._check_alerts(3, pipe)
        service.phase = 'listening'
        service._check_alerts(2, pipe)
        service.alerts_enabled = False
        service._check_alerts(3, pipe)
        service.alerts_enabled = True
        service.stop_event.set()
        service._check_alerts(3, pipe)
    service.stop_event.clear()
    with patch('backend.voice_worker.desktop_unlocked', return_value=False):
        service._check_alerts(3, pipe)
    pipe.send.assert_not_called()
    with patch('backend.voice_worker.desktop_unlocked', return_value=True):
        service._check_alerts(3, pipe)
    assert pipe.send.call_args.args[0]['type'] == 'alert'
    assert service.phase == 'alert'


def test_hardware_alerts_are_saved_but_excluded_from_conversation_context(tmp_path):
    history = VoiceHistory(tmp_path)
    history.add('Open Steam', 'Opening Steam, sir.')
    for _ in range(8):
        history.add('Hardware alert', 'Sir, memory usage is high.', kind='alert')
    assert len(history.recent()) == 9
    assert history.recent()[-1]['kind'] == 'alert'
    assert history.context() == [{'role': 'user', 'content': 'Open Steam'}, {'role': 'assistant', 'content': 'Opening Steam, sir.'}]


@pytest.mark.parametrize('cancelled', [False, True])
@pytest.mark.parametrize('kind', ['alert', 'reminder'])
def test_worker_speaks_spontaneous_alert_locally_without_wake_or_cloud(monkeypatch, tmp_path, cancelled, kind):
    import sys
    stop, pending = threading.Event(), []
    pipe = Mock()
    listening_count = []
    def send(event):
        if event.get('phase') == 'listening':
            listening_count.append(True)
            if len(listening_count) == 1:
                pending.append({'type': kind, 'text': 'Sir, your focus session is complete.', 'id': 'phase-one', 'expires': time.time()+60})
                if cancelled:
                    pending.append({'type': 'alerts', 'enabled': False} if kind == 'alert' else {'type': 'reminder-cancel'})
            elif cancelled:
                stop.set()
    pipe.send.side_effect = send
    pipe.poll.side_effect = lambda *args: bool(pending)
    pipe.recv.side_effect = lambda: pending.pop(0)
    manager = Mock()
    manager.__enter__ = Mock(return_value=Mock())
    manager.__exit__ = Mock(return_value=False)
    microphone = SimpleNamespace(RawInputStream=Mock(return_value=manager))
    monkeypatch.setitem(sys.modules, 'sounddevice', microphone)
    engine = Mock()
    def synthesize(text, wav):
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050); wav.writeframes(b'\0\0' * 100)
    engine.load.return_value.synthesize_wav.side_effect = synthesize
    monkeypatch.setitem(sys.modules, 'piper', SimpleNamespace(PiperVoice=engine))
    wake = Mock()
    wake_module = SimpleNamespace(Model=Mock(return_value=wake))
    monkeypatch.setitem(sys.modules, 'openwakeword', SimpleNamespace(model=wake_module))
    monkeypatch.setitem(sys.modules, 'openwakeword.model', wake_module)
    client = Mock()
    client.__enter__ = Mock(return_value=client); client.__exit__ = Mock(return_value=False)
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=Mock(return_value=client)))
    with patch('backend.voice_worker.desktop_unlocked', return_value=True), \
         patch('backend.voice_audio.resolve_input', return_value={'index': 1, 'name': 'Webcam'}), \
         patch('backend.voice_audio.resolve_output', return_value={'index': 12, 'name': 'Speakers'}), \
         patch('backend.voice_audio.play_on_speaker', side_effect=lambda *args: stop.set()) as play:
        worker_main(pipe, stop, str(tmp_path), 'sk-qa-only', [])
    if cancelled:
        play.assert_not_called()
    else:
        play.assert_called_once()
    wake.predict.assert_not_called()
    client.audio.transcriptions.create.assert_not_called()
    client.responses.create.assert_not_called()
    assert any(call.args[0].get('kind') == 'alert' for call in pipe.send.call_args_list) is (kind == 'alert' and not cancelled)
    if kind == 'reminder':
        assert not any(call.args[0].get('type') == 'exchange' for call in pipe.send.call_args_list)
