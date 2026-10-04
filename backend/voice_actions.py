"""Small voice adapter for the same trusted actions as the touch interface."""
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlsplit

from .controllers import MEDIA_KEYS, media_action
from .ambient import ambient_options, load_ambient_scenes

VOICE_MODEL = 'gpt-6-luna'
PROMPT_PATH = Path(__file__).with_name('jarvis_prompt.txt')

# Display destinations only. These IDs never grant access to the controls on a page.
VOICE_SCREENS = {
    'home': 'Home', 'gaming': 'Live performance', 'games': 'Game library',
    'apps': 'Applications', 'hardware': 'Hardware monitor', 'graphs': 'Live graphs',
    'clock': 'Clock', 'focus': 'Focus timer', 'ambient': 'Ambient',
    'media': 'Now playing', 'system': 'System & controls', 'devices': 'Device access',
    'rest': 'Rest & alarms', 'voice': 'Jarvis', 'widgets': 'Widgets',
    'weather': 'Weather & air quality', 'f1': 'F1 next race',
}


def _rest_command(text):
    """Normalize only punctuation around Jarvis, never quoted/model instructions."""
    if not isinstance(text, str) or len(text) > 1000:
        return ''
    command = re.sub(r'\s+', ' ', text.lower()).strip().rstrip('.!?,')
    command = re.sub(r'^(?:hey[,.!?:\s]+)?jarvis[,.!?:\s]+', '', command).strip()
    command = re.sub(r'[,\s]+jarvis$', '', command).strip()
    return command


def rest_entry_requested(text):
    return _rest_command(text) in {'enter rest mode', 'please enter rest mode', 'enter rest mode please'}


def rest_wake_requested(text):
    return _rest_command(text) in {'wake up', 'please wake up', 'wake up please'}


def voice_tools(registry):
    apps = [app for app in registry.catalog() if app['available']]
    tools = []
    for name, description, field, values in [
        ('launch_app', 'Open an installed laptop app: ' + ', '.join(f"{a['id']} = {a['name']}" for a in apps), 'id', [a['id'] for a in apps]),
        ('media_control', 'Change laptop sound or control its current media player. Play-pause toggles playback.', 'action', list(MEDIA_KEYS)),
        ('show_screen', 'Request a dashboard screen on already connected, visible approved browsers. '
         'Opening a screen does not launch apps/games, start timers, change settings or enter Rest. '
         'Destinations: ' + ', '.join(f'{key} = {label}' for key, label in VOICE_SCREENS.items()),
         'screen', list(VOICE_SCREENS)),
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
    tools.append({'type': 'web_search', 'search_context_size': 'low'})
    return scene_voice_tools(tools)


def scene_voice_tools(tools):
    # Refresh per turn, so an enabled worker sees catalog additions/removals without a prompt edit.
    result = [tool for tool in tools if tool.get('name') not in {'list_ambient_scenes', 'show_ambient'}]
    result.append({'type': 'function', 'name': 'list_ambient_scenes',
                   'description': 'Discover the currently available local Ambient scenes and their IDs before choosing a named scene.',
                   'strict': True, 'parameters': {'type': 'object', 'properties': {},
                                                'required': [], 'additionalProperties': False}})
    options = ambient_options()
    if options:
        result.append({'type': 'function', 'name': 'show_ambient',
                       'description': 'Open Ambient and select one scene discovered with list_ambient_scenes. '
                                      'Available scene IDs and names: ' + ', '.join(f"{scene['id']} = {scene['name']}" for scene in options),
                       'strict': True, 'parameters': {'type': 'object', 'properties': {
                           'scene': {'type': 'string', 'enum': [scene['id'] for scene in options]}},
                           'required': ['scene'], 'additionalProperties': False}})
    return result


def safe_sources(sources):
    result, seen = [], set()
    for source in (sources or [])[:20]:
        if not isinstance(source, dict):
            continue
        url = str(source.get('url', ''))[:2048]
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or url in seen:
            continue
        seen.add(url)
        result.append({'url': url, 'title': str(source.get('title') or parsed.hostname)[:180]})
        if len(result) == 5:
            break
    return result


def response_sources(response):
    sources = []
    for item in response.output:
        if item.type != 'message':
            continue
        for content in getattr(item, 'content', []):
            for annotation in getattr(content, 'annotations', []):
                if annotation.type == 'url_citation':
                    sources.append({'url': annotation.url, 'title': annotation.title})
    return safe_sources(sources)


def spoken_reply(text):
    # Source links remain visible beside the answer; don't read URL strings aloud.
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\s)]+\)', r'\1', text)
    text = re.sub(r'[^]*', '', text)
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()[:500]


def execute_tool(name, arguments, registry, telemetry, navigate=None):
    # Treat model output as untrusted, even with strict API schemas.
    if not isinstance(arguments, dict):
        raise ValueError('Invalid action arguments.')
    if name == 'list_ambient_scenes' and not arguments:
        options = ambient_options()
        return {'ok': bool(options), 'scenes': options,
                'message': 'Available local Ambient scenes.' if options else 'Local Ambient scenes are unavailable.'}
    if name == 'show_ambient' and set(arguments) == {'scene'}:
        scene = arguments['scene']
        if not isinstance(scene, str) or scene not in load_ambient_scenes():
            raise ValueError('This Ambient scene is unavailable.')
        if navigate is None:
            return {'ok': False, 'message': 'Dashboard navigation is unavailable.'}
        return navigate('ambient', scene=scene)
    if name == 'show_screen' and set(arguments) == {'screen'}:
        screen = arguments['screen']
        if not isinstance(screen, str) or screen not in VOICE_SCREENS:
            raise ValueError('Unknown dashboard screen.')
        if navigate is None:
            return {'ok': False, 'message': 'Dashboard navigation is unavailable.'}
        return navigate(screen)
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


def respond(client, text, tools, dispatch, allowed=lambda: True, history=None, cite=lambda sources: None):
    """Load the trusted local prompt; the optional SDK stays inside the voice worker."""
    instructions = PROMPT_PATH.read_text(encoding='utf-8').replace('{now}', datetime.now().astimezone().isoformat())
    from .voice_agent import run_turn
    return run_turn(client, instructions, text, scene_voice_tools(tools), dispatch, allowed, history, cite)
