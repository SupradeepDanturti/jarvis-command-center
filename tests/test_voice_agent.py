import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.voice_actions import respond, voice_tools

pytestmark = pytest.mark.usefixtures('jarvis_sdk_transport')


def specs():
    registry = Mock()
    registry.catalog.return_value = [{'id': 'steam', 'name': 'Steam', 'available': True},
                                    {'id': 'discord', 'name': 'Discord', 'available': True}]
    return voice_tools(registry)


def call(name, arguments, identity):
    import json
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=identity)


def output(*items, text=''):
    return SimpleNamespace(output=list(items), output_text=text)


def test_sdk_parallel_batch_can_show_screen_read_hardware_and_launch_once():
    client, dispatch = Mock(), Mock(return_value={'ok': True, 'message': 'Completed.'})
    client.responses.create.side_effect = [output(
        call('show_screen', {'screen': 'games'}, 'screen'), call('system_status', {}, 'read'),
        call('launch_app', {'id': 'steam'}, 'app')), output(text='Steam is open and the game library was requested.')]
    assert 'game library' in respond(client, 'Open Steam, show games and read my CPU.', specs(), dispatch)
    assert [item.args[0] for item in dispatch.call_args_list] == ['show_screen', 'system_status', 'launch_app']
    for request in client.responses.create.call_args_list:
        assert request.kwargs['parallel_tool_calls'] is True
        assert request.kwargs['store'] is False
        assert request.kwargs.get('previous_response_id') != 'resp_qa'


def test_parallel_physical_budget_and_duplicate_call_ledger_survive_extra_sdk_round():
    client, dispatch = Mock(), Mock(return_value={'ok': True, 'message': 'Steam opened.'})
    client.responses.create.side_effect = [output(call('launch_app', {'id': 'steam'}, 'app-1'),
        call('launch_app', {'id': 'discord'}, 'app-2'), call('media_control', {'action': 'volume-up'}, 'media')),
        output(call('launch_app', {'id': 'steam'}, 'repeat')), output(text='Steam opened.')]
    assert respond(client, 'Open Steam and Discord.', specs(), dispatch) == 'Steam opened.'
    dispatch.assert_called_once_with('launch_app', {'id': 'steam'})


def test_disable_between_parallel_calls_prevents_later_dispatch_and_reply():
    client, dispatch = Mock(), Mock()
    live = [True]
    def dispatched(*args):
        live[0] = False
        return {'ok': True, 'message': 'Screen requested.'}
    dispatch.side_effect = dispatched
    client.responses.create.return_value = output(call('show_screen', {'screen': 'games'}, 'screen'),
                                                call('launch_app', {'id': 'steam'}, 'app'))
    assert respond(client, 'Show games and open Steam.', specs(), dispatch, allowed=lambda: live[0]) == ''
    dispatch.assert_called_once_with('show_screen', {'screen': 'games'})
    assert client.responses.create.call_count == 1


def test_sdk_run_has_no_tracing_or_sensitive_data_and_is_bounded():
    import backend.voice_agent as agent
    client = Mock()
    client.responses.create.return_value = output(text='Ready.')
    native_run = agent.Runner.run
    captured = []
    async def run(*args, **kwargs):
        captured.append(kwargs)
        return await native_run(*args, **kwargs)
    with patch.object(agent.Runner, 'run', side_effect=run):
        assert respond(client, 'Hello', specs(), Mock()) == 'Ready.'
    assert captured[0]['run_config'].tracing_disabled is True
    assert captured[0]['run_config'].trace_include_sensitive_data is False
    assert captured[0]['max_turns'] == 3
    assert agent.logging.getLogger('openai.agents').disabled
    assert agent.os.environ['OPENAI_AGENTS_DONT_LOG_MODEL_DATA'] == '1'
    assert agent.os.environ['OPENAI_AGENTS_DONT_LOG_TOOL_DATA'] == '1'


def test_followup_failure_reports_all_completed_tools_without_retry():
    client = Mock()
    dispatch = Mock(side_effect=[{'ok': True, 'message': 'Steam opened.'},
                                {'ok': True, 'message': 'Games requested.'}])
    client.responses.create.side_effect = [output(call('launch_app', {'id': 'steam'}, 'app'),
                                                  call('show_screen', {'screen': 'games'}, 'screen')), RuntimeError()]
    assert respond(client, 'Open Steam and show games.', specs(), dispatch) == 'Steam opened. Games requested.'
    assert dispatch.call_count == 2


def test_unknown_tools_and_extra_arguments_never_grant_access():
    from backend.voice_actions import execute_tool
    client = Mock()
    dispatch = lambda name, args: execute_tool(name, args, Mock(), Mock())
    client.responses.create.side_effect = [output(call('launch_app', {'id': 'steam', 'command': 'whoami'}, 'bad')),
                                           output(text='The request failed.')]
    assert respond(client, 'Open Steam', specs(), dispatch) == 'The request failed.'


def test_disabled_dashboard_never_imports_the_optional_agents_sdk():
    subprocess.run([sys.executable, '-c',
        "import sys; import backend.main; assert 'agents' not in sys.modules; "
        "assert 'backend.voice_agent' not in sys.modules"], check=True)


def test_late_parent_result_cannot_be_misattributed_to_the_next_tool():
    import threading
    from backend.voice_worker import request_tool_action
    pipe, control = Mock(), Mock()
    messages = []
    def sent(event):
        messages.extend([{'type': 'result', 'id': 'old-request', 'result': {'ok': True, 'message': 'Old result'}},
                         {'type': 'alerts', 'enabled': False},
                         {'type': 'result', 'id': event['id'], 'result': {'ok': True, 'message': 'New result'}}])
    pipe.send.side_effect = sent
    pipe.poll.side_effect = lambda *args: bool(messages)
    pipe.recv.side_effect = lambda: messages.pop(0)
    assert request_tool_action(pipe, threading.Event(), 'show_screen', {'screen': 'games'},
                               lambda: True, control)['message'] == 'New result'
    assert control.call_count == 2
