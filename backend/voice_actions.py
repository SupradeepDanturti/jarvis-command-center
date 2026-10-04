"""Small voice adapter for the same trusted actions as the touch interface."""
import json

from fastapi import HTTPException

from .controllers import MEDIA_KEYS, media_action

VOICE_MODEL = 'gpt-6-luna'


def voice_tools(registry):
    apps = [app for app in registry.catalog() if app['available']]
    tools = []
    for name, description, field, values in [
        ('launch_app', 'Open an installed laptop app: ' + ', '.join(f"{a['id']} = {a['name']}" for a in apps), 'id', [a['id'] for a in apps]),
        ('media_control', 'Change laptop sound or control its current media player. Play-pause toggles playback.', 'action', list(MEDIA_KEYS)),
    ]:
        if not values:
            continue
        tools.append({'type': 'function', 'name': name, 'description': description,
                      'strict': True, 'parameters': {'type': 'object', 'properties': {
                          field: {'type': 'string', 'enum': values}},
                          'required': [field], 'additionalProperties': False}})
    tools.append({'type': 'function', 'name': 'system_status', 'description': 'Read current CPU, RAM and GPU readings.',
                  'strict': True, 'parameters': {'type': 'object', 'properties': {},
                                               'required': [], 'additionalProperties': False}})
    return tools


def execute_tool(name, arguments, registry, telemetry):
    # Treat model output as untrusted, even with strict API schemas.
    if not isinstance(arguments, dict):
        raise ValueError('Invalid action arguments.')
    if name == 'launch_app' and set(arguments) == {'id'}:
        app_id = arguments['id']
        if not isinstance(app_id, str) or app_id not in {a['id'] for a in registry.catalog() if a['available']}:
            raise ValueError('This application is not available.')
        return registry.launch(app_id)
    if name == 'media_control' and set(arguments) == {'action'}:
        action = arguments['action']
        if not isinstance(action, str) or action not in MEDIA_KEYS:
            raise ValueError('Unknown sound control.')
        return media_action(action)
    if name == 'system_status' and not arguments:
        data = telemetry.latest
        if not data:
            return {'ok': False, 'message': 'Hardware readings are unavailable.'}
        return {'ok': True, 'cpuPercent': data['cpu']['usage'], 'memoryPercent': data['memory']['percent'],
                'gpu': data.get('gpu') and {key: data['gpu'].get(key) for key in ('name', 'usage', 'temperature')}}
    raise ValueError('This voice action is not allowed.')


def respond(client, text, tools, dispatch, allowed=lambda: True):
    """One bounded turn; never retry a physical action or run arbitrary code."""
    instructions = ('You are Jarvis, the user\'s concise laptop assistant. Reply in one or two short sentences. '
                    'Use only the supplied tools for explicit laptop requests. Never invent successful actions. '
                    'Ask for clarification if ambiguous; reject shell commands, arbitrary URLs, files, installation, '
                    'account changes and destructive actions. One action per request. For play or pause, use '
                    'play-pause only once. No markdown. You are an AI assistant with a synthetic Jarvis-style voice.')
    response = client.responses.create(model=VOICE_MODEL, reasoning={'effort': 'none'}, instructions=instructions,
                                       input=text[:1000], tools=tools, parallel_tool_calls=False,
                                       max_output_tokens=350, store=False)
    calls = [item for item in response.output if item.type == 'function_call']
    if not allowed():
        return ''
    if not calls:
        return (response.output_text or 'Please repeat that, sir.')[:500]
    if len(calls) != 1:
        return 'Please give me one laptop command at a time, sir.'
    call = calls[0]
    try:
        arguments = json.loads(call.arguments)
        result = dispatch(call.name, arguments)
    except (ValueError, TypeError, json.JSONDecodeError, HTTPException):
        return 'I could not carry out that action, sir.'
    # The action has already happened. A failed follow-up must not repeat it.
    try:
        followup = client.responses.create(model=VOICE_MODEL, reasoning={'effort': 'none'}, instructions=instructions,
            input=[{'role': 'user', 'content': text[:1000]}, *response.output,
                   {'type': 'function_call_output', 'call_id': call.call_id, 'output': json.dumps(result)}],
            max_output_tokens=200, store=False)
        return (followup.output_text or result.get('message') or 'Done, sir.')[:500]
    except Exception:
        return str(result.get('message') or 'The action completed, sir.')[:500]
