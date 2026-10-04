import json
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.alarms import RestAlarms
from backend.display_power import DisplayPower, WindowsDisplay, CONTINUOUS, SYSTEM, DISPLAY
from backend.monitor_power import MonitorPower
from backend.alarm_audio import alarm_worker
from backend.main import create_app

ORIGIN = {'origin': 'https://testserver'}


class Clock:
    def __init__(self):
        self.wall, self.mono = 1800000000., 100.

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


class Power:
    available = True

    def __init__(self):
        self.held = False
        self.calls = []

    def hold(self, value):
        self.held = value
        self.calls.append(('hold', value))

    def probe(self):
        return 2

    def off(self, allowed=lambda: True):
        if not allowed():
            raise OSError('Cancelled')
        self.calls.append(('display', False))

    def wake(self):
        self.calls.append(('display', True))

    def close(self):
        self.held = False


def service(clock=None, path=None):
    clock = clock or Clock()
    audio = Mock()
    audio.ready.return_value = True
    audio.status.return_value = {'ready': True, 'phase': 'off', 'message': ''}
    return RestAlarms(Power(), audio, path=path, wall=lambda: clock.wall, monotonic=lambda: clock.mono), clock


def arm(rest, clock, delay=10, speech=True):
    return rest.arm(rest.revision, clock.wall+delay, 'wake up', speech)


def test_rest_nonce_bound_to_device_expiry_single_use_and_no_startup_effects():
    rest, clock = service()
    assert rest.power.calls == []
    nonce = rest.prepare('owner')['nonce']
    with pytest.raises(HTTPException):
        rest.enter('tablet', nonce, 0)
    assert rest.power.calls == []
    clock.advance(31)
    with pytest.raises(HTTPException):
        rest.enter('owner', nonce, 0)
    nonce = rest.prepare('tablet')['nonce']
    result = rest.enter('tablet', nonce, 0)
    assert result['rest'] and rest.power.held
    assert rest.power.calls[-1] == ('display', False)
    with pytest.raises(HTTPException):
        rest.enter('tablet', nonce, rest.revision)
    assert len([call for call in rest.power.calls if call == ('display', False)]) == 1
    assert rest.wake()['rest'] is False
    assert rest.power.held is False


def test_alarm_fires_once_wakes_exits_rest_snooze_dismiss_and_cancels_audio(tmp_path):
    rest, clock = service(path=tmp_path/'alarms.json')
    rest.before_ring = Mock()
    arm(rest, clock)
    rest.enter('tablet', rest.prepare('tablet')['nonce'], rest.revision)
    clock.advance(10); rest.tick()
    assert rest.alarm['status'] == 'ringing' and not rest.rest
    saved = json.loads(rest.path.read_text())
    assert saved['alarm']['status'] == 'ringing'
    rest.before_ring.assert_called_once()
    rest.audio.start.assert_called_once_with('wake up', clock.wall+600)
    for _ in range(3): rest.tick()
    assert rest.audio.start.call_count == 1
    assert len([call for call in rest.power.calls if call == ('display', True)]) == 1
    with pytest.raises(HTTPException):
        rest.command(rest.revision-1, 'dismiss')
    rest.command(rest.revision, 'snooze')
    assert rest.alarm['dueAt'] == clock.wall+300 and rest.alarm['status'] == 'armed'
    clock.advance(300); rest.tick()
    assert rest.audio.start.call_count == 2
    rest.command(rest.revision, 'dismiss')
    assert not rest.power.held and rest.alarm['status'] == 'dismissed'
    clock.advance(1000);rest.tick();assert rest.audio.start.call_count == 2


def test_restart_recovers_future_but_overdue_and_ringing_are_silent(tmp_path):
    path=tmp_path/'alarms.json'
    rest, clock=service(path=path);arm(rest,clock)
    recovered,_=service(clock,path)
    assert recovered.alarm['status']=='armed' and recovered.power.calls==[]
    recovered.tick();assert recovered.power.held
    clock.advance(11)
    overdue,_=service(clock,path)
    assert overdue.alarm['status']=='missed' and overdue.power.calls==[]
    overdue.audio.start.assert_not_called()
    recovered.tick()
    interrupted,_=service(clock,path)
    assert interrupted.alarm['status']=='missed'
    interrupted.audio.start.assert_not_called()


def test_clock_jump_pauses_even_when_storage_fails_and_never_wakes(tmp_path):
    rest,clock=service(path=tmp_path/'alarms.json');arm(rest,clock)
    clock.wall += 3600
    with patch('pathlib.Path.replace',side_effect=OSError):
        with pytest.raises(HTTPException): rest.tick()
    assert rest.snapshot()['alarm']['status']=='paused'
    rest.tick();assert rest.alarm['status']=='paused'
    rest.audio.start.assert_not_called()
    assert ('display',True) not in rest.power.calls


def test_storage_failure_does_not_arm_or_dispatch_due_effects(tmp_path):
    rest,clock=service(path=tmp_path/'alarms.json')
    with patch('pathlib.Path.replace',side_effect=OSError):
        with pytest.raises(HTTPException): arm(rest,clock)
    assert rest.alarm is None and not rest.power.held
    arm(rest,clock);clock.advance(10)
    with patch('pathlib.Path.replace',side_effect=OSError):
        with pytest.raises(HTTPException): rest.tick()
    assert rest.alarm['status']=='armed'
    rest.audio.start.assert_not_called()
    assert ('display',True) not in rest.power.calls


def test_missing_voice_visual_only_cancel_late_and_ten_minute_limit():
    rest,clock=service();rest.audio.ready.return_value=False
    with pytest.raises(HTTPException): arm(rest,clock)
    assert rest.alarm is None
    arm(rest,clock,speech=False);clock.advance(10);rest.tick()
    rest.audio.start.assert_not_called()
    clock.advance(600);rest.tick();assert rest.alarm['status']=='missed'
    arm(rest,clock,speech=False);rest.command(rest.revision,'cancel')
    clock.advance(10);rest.tick();assert rest.alarm is None
    assert len([call for call in rest.power.calls if call==('display',True)])==1
    arm(rest,clock,speech=False);rest.closed.set();clock.advance(10);rest.tick()
    assert rest.alarm['status']=='armed'


def test_display_requests_and_lease_clear_use_one_thread():
    calls=[]
    class Native:
        def hold(self,value):calls.append(('hold',value,threading.get_ident()))
        def display(self,value,expires,allowed):calls.append(('display',value,threading.get_ident()))
        def close(self):self.hold(False)
    power=DisplayPower(factory=Native)
    power.hold(True);power.off();power.wake();power.hold(False);power.close()
    assert [(kind,value) for kind,value,_ in calls]==[('hold',True),('display',False),('display',True),('hold',False),('hold',False)]
    assert len({thread for _,_,thread in calls})==1
    assert not power.held
    with pytest.raises(OSError):power.off()


def test_api_auth_origin_extra_fields_finite_time_and_confirmation():
    app=create_app(pairing_code='ABCD1234')
    rest=app.state.rest
    # Inject hardware/audio adapters; QA never dispatches physical monitor or speaker actions.
    rest.power=Power();rest.audio=service()[0].audio
    client=TestClient(app,base_url='https://testserver',client=('127.0.0.1',4000))
    for url in ['/api/alarms','/api/rest/prepare','/api/rest/enter','/api/rest/wake']:
        response=client.get(url) if url=='/api/alarms' else client.post(url,headers=ORIGIN,json={'revision':0,'nonce':'a'*24} if url.endswith('enter') else {})
        assert response.status_code==401
    client.post('/api/pair',json={'code':'ABCD1234'},headers=ORIGIN)
    body={'revision':0,'dueAt':__import__('time').time()+60,'label':'wake up','speech':False}
    assert client.put('/api/alarms',json=body,headers={'origin':'https://evil.example'}).status_code==403
    assert client.put('/api/alarms',json={**body,'path':'cmd.exe'},headers=ORIGIN).status_code==422
    assert client.put('/api/alarms',json={**body,'revision':True},headers=ORIGIN).status_code==422
    assert client.put('/api/alarms',json={**body,'label':'\n'},headers=ORIGIN).status_code==422
    assert client.put('/api/alarms',json=body,headers=ORIGIN).status_code==200
    assert client.post('/api/rest/enter',json={'revision':1,'nonce':'a'*24},headers=ORIGIN).status_code==409
    nonce=client.post('/api/rest/prepare',json={},headers=ORIGIN).json()['nonce']
    result=client.post('/api/rest/enter',json={'revision':1,'nonce':nonce},headers=ORIGIN)
    assert result.status_code==200 and result.json()['rest']
    assert client.post('/api/rest/wake',json={},headers={'origin':'https://evil.example'}).status_code==403
    client.post('/api/logout',headers=ORIGIN)
    assert client.get('/api/alarms').status_code==401
    assert client.post('/api/rest/wake',json={},headers=ORIGIN).status_code==401


@pytest.mark.parametrize('cancel_during_synthesis',[False,True])
def test_alarm_voice_is_local_without_microphone_cloud_or_unlock(monkeypatch,tmp_path,cancel_during_synthesis):
    stop,pipe=threading.Event(),Mock()
    pipe.poll.return_value=False
    voice=Mock()
    def synthesize(text,wav):
        assert text=="Sir, it's time to wake up."
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050);wav.writeframes(b'\0\0'*100)
        if cancel_during_synthesis:stop.set()
    voice.synthesize_wav.side_effect=synthesize
    engine=Mock(return_value=voice)
    monkeypatch.setitem(sys.modules,'piper',SimpleNamespace(PiperVoice=SimpleNamespace(load=engine)))
    microphone=Mock(side_effect=AssertionError('Alarm must never open a microphone'))
    cloud=Mock(side_effect=AssertionError('Alarm must never call the cloud'))
    monkeypatch.setitem(sys.modules,'sounddevice',SimpleNamespace(RawInputStream=microphone))
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=cloud))
    calls=[]
    def playback(audio,device,allowed):
        assert allowed() and device['index']==12
        calls.append(audio)
        if len(calls)==2:stop.set()
    with patch('backend.voice_audio.resolve_output',return_value={'index':12,'name':'QA speaker'}), \
         patch('backend.voice_audio.play_on_speaker',side_effect=playback), \
         patch('backend.voice_worker.desktop_unlocked',return_value=False):
        alarm_worker(pipe,stop,str(tmp_path),None,'wake up',time.time()+10)
    assert len(calls)==(0 if cancel_during_synthesis else 2)
    microphone.assert_not_called();cloud.assert_not_called()
    assert not any(call.args[0].get('type')=='exchange' for call in pipe.send.call_args_list)


def test_failed_power_request_does_not_claim_rest_or_alarm_armed():
    rest,clock=service()
    rest.power.hold=Mock(side_effect=OSError)
    with pytest.raises(HTTPException) as error:arm(rest,clock)
    assert error.value.status_code==503 and rest.alarm is None
    with pytest.raises(HTTPException):rest.enter('tablet',rest.prepare('tablet')['nonce'],rest.revision)
    assert not rest.rest and ('display',False) not in rest.power.calls


def test_invalid_saved_alarm_and_backward_clock_recovery(tmp_path):
    path=tmp_path/'alarms.json';path.write_text('x'*4097)
    rest,clock=service(path=path)
    assert rest.alarm is None and rest.power.calls==[]
    arm(rest,clock,delay=3600);clock.wall-=600
    recovered,_=service(clock,path)
    assert recovered.alarm['status']=='paused' and not recovered.rest
    assert recovered.power.calls==[]


def test_preview_is_fixed_short_local_audio_and_cancellation_does_not_change_alarm():
    rest,clock=service();rest.before_ring=Mock();arm(rest,clock)
    revision=rest.revision
    rest.preview()
    rest.before_ring.assert_called_once()
    rest.audio.start.assert_called_once_with('wake up',clock.wall+10)
    assert rest.revision==revision and rest.alarm['status']=='armed'
    rest.command(revision,'cancel');rest.audio.stop.assert_called()


def test_wake_exits_rest_even_when_alarm_storage_is_unavailable(tmp_path):
    rest, _ = service(path=tmp_path/'alarms.json')
    rest.enter('tablet', rest.prepare('tablet')['nonce'], rest.revision)
    revision = rest.revision
    with patch('pathlib.Path.replace', side_effect=OSError):
        result = rest.wake()
    assert not result['rest'] and not result['keepingAwake']
    assert result['revision'] > revision and 'storage unavailable' in result['message']
    assert rest.power.calls[-2:] == [('display', True), ('hold', False)]


@pytest.mark.parametrize('fail_execution', [False, True])
def test_modern_standby_lease_holds_display_system_and_execution_and_cleans_up(fail_execution):
    native = object.__new__(WindowsDisplay)
    native.request = None
    native.kernel = SimpleNamespace(PowerCreateRequest=Mock(return_value=25),
        PowerSetRequest=Mock(side_effect=lambda handle, kind: not (fail_execution and kind == 3)),
        PowerClearRequest=Mock(return_value=True), CloseHandle=Mock(return_value=True),
        SetThreadExecutionState=Mock(return_value=CONTINUOUS))
    if fail_execution:
        with pytest.raises(OSError):native.hold(True)
        assert native.request is None
        assert [call.args[1] for call in native.kernel.PowerClearRequest.call_args_list] == [1, 0]
    else:
        native.hold(True);native.hold(True)
        assert [call.args[1] for call in native.kernel.PowerSetRequest.call_args_list] == [0, 1, 3]
        native.kernel.SetThreadExecutionState.assert_called_once_with(CONTINUOUS | SYSTEM | DISPLAY)
        native.hold(False)
        assert [call.args[1] for call in native.kernel.PowerClearRequest.call_args_list] == [3, 1, 0]
        assert native.request is None
    native.kernel.CloseHandle.assert_called_once_with(25)


def test_ddc_power_uses_fixed_values_retains_wake_handles_and_rolls_back_partial_failure():
    assert MonitorPower.supports_power('(vcp(10 12 d6(01 04 05)))')
    assert not MonitorPower.supports_power('(vcp(10 d6(01 05)))')
    native = object.__new__(MonitorPower)
    native.handles, native.off_handles = [11, 12], []
    native.targets, native.prepared_at = [11, 12], time.monotonic()
    native.dx = SimpleNamespace(SetVCPFeature=Mock(return_value=True), DestroyPhysicalMonitor=Mock())
    native.display(False, time.monotonic()+5)
    assert [call.args for call in native.dx.SetVCPFeature.call_args_list] == [(11, 0xd6, 4), (12, 0xd6, 4)]
    native.dx.SetVCPFeature.side_effect=lambda handle, code, value: handle != 12
    with pytest.raises(OSError):native.display(True, time.monotonic()+5)
    assert native.off_handles == [12]
    native.dx.SetVCPFeature.side_effect=None
    native.close();assert native.off_handles == []
    native.handles, native.off_handles = [11, 12], []
    native.targets, native.prepared_at = [11, 12], time.monotonic()
    native.dx.SetVCPFeature.reset_mock()
    native.dx.SetVCPFeature.side_effect=lambda handle, code, value: not (handle == 12 and value == 4)
    with pytest.raises(OSError):native.display(False, time.monotonic()+5)
    assert native.off_handles == []
    assert [call.args for call in native.dx.SetVCPFeature.call_args_list] == [(11, 0xd6, 4), (12, 0xd6, 4), (11, 0xd6, 1)]
    native.dx.SetVCPFeature.reset_mock()
    with pytest.raises(OSError):native.display(False, time.monotonic()-1)
    native.dx.SetVCPFeature.assert_not_called()
    native.targets=[]
    with pytest.raises(OSError):native.display(False, time.monotonic()+5)
    native.dx.SetVCPFeature.assert_not_called()


def test_slow_monitor_preparation_does_not_block_shared_state_or_issue_power_off():
    rest, _ = service()
    entered, finish = threading.Event(), threading.Event()
    def probe():
        entered.set()
        assert finish.wait(2)
        return 2
    rest.power.probe = probe
    result = []
    thread = threading.Thread(target=lambda: result.append(rest.prepare('tablet')))
    thread.start();assert entered.wait(1)
    assert rest.lock.acquire(blocking=False)
    try:
        assert rest.snapshot()['rest'] is False
    finally:
        rest.lock.release()
        finish.set();thread.join(timeout=2)
    assert result[0]['nonce'] and rest.power.calls == []
    rest.power.probe = Mock(return_value=0)
    with pytest.raises(HTTPException):rest.prepare('other')
    assert 'other' not in rest.nonces


def test_cancelled_voice_guard_prevents_entry_and_rolls_back_partial_monitor_off():
    rest, _ = service()
    nonce = rest.prepare('voice')['nonce']
    with pytest.raises(HTTPException):rest.enter('voice', nonce, rest.revision, allowed=lambda: False)
    assert rest.power.calls == [] and not rest.rest
    native = object.__new__(MonitorPower)
    native.targets, native.prepared_at, native.off_handles = [11, 12], time.monotonic(), []
    native.dx = SimpleNamespace(SetVCPFeature=Mock(return_value=True))
    decisions = iter([True, True, False])
    with pytest.raises(OSError):native.display(False, time.monotonic()+5, allowed=lambda: next(decisions))
    assert [call.args for call in native.dx.SetVCPFeature.call_args_list] == [(11, 0xd6, 4), (11, 0xd6, 1)]
    assert not native.off_handles
