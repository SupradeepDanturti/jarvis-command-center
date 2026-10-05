from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.mark.parametrize('jarvis,assistant', [(False, False), (True, False), (False, True), (True, True)])
def test_startup_options_are_independent_and_do_not_retry_after_stop(jarvis, assistant):
    app = create_app(pairing_code='QA123456', start_jarvis=jarvis, start_assistant=assistant)
    with patch.object(app.state.voice, 'start') as start, patch.object(app.state.voice, 'stop') as stop:
        with TestClient(app, base_url='https://testserver'):
            assert app.state.assistant.enabled is assistant
            assert start.call_count == int(jarvis)
            app.state.assistant.enable(False)
            app.state.voice.stop()
            assert not app.state.assistant.enabled
            assert start.call_count == int(jarvis)
        assert not app.state.assistant.enabled
        assert stop.call_count >= 2


@pytest.mark.parametrize('detail', ['Install the local voice components first.', 'Save an OpenAI key first.',
                                  'Windows could not unlock the saved key.'])
def test_expected_voice_setup_failure_keeps_dashboard_available(detail):
    app = create_app(pairing_code='QA123456', start_jarvis=True, start_assistant=True)
    with patch.object(app.state.voice, 'start', side_effect=HTTPException(409, detail)) as start:
        with TestClient(app, base_url='https://testserver') as client:
            assert client.get('/api/health').status_code == 200
            assert app.state.assistant.enabled
            assert app.state.voice.phase == 'off'
            assert app.state.voice.message == detail
            assert app.state.voice.process is None
            # Default-on does not grant an unapproved browser any access.
            assert client.get('/api/assistant/status').status_code == 401
            assert client.get('/api/voice/status').status_code == 401
            start.assert_called_once_with()


def test_unconfigured_startup_does_not_start_voice_worker():
    app = create_app(pairing_code='QA123456', start_jarvis=True)
    with TestClient(app, base_url='https://testserver') as client:
        assert client.get('/api/health').status_code == 200
        assert app.state.voice.process is None
        assert app.state.voice.phase == 'off'
        assert 'Install' in app.state.voice.message
