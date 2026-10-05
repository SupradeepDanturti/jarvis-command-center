"""Typed input adapter. Optional model dependencies load only in this child."""
import os
import time


def chat_worker(pipe, stop, key, text, tools, context):
    # Set privacy controls before importing any optional provider dependency.
    os.environ['OPENAI_AGENTS_DONT_LOG_MODEL_DATA'] = '1'
    os.environ['OPENAI_AGENTS_DONT_LOG_TOOL_DATA'] = '1'
    os.environ['OPENAI_AGENTS_DISABLE_TRACING'] = '1'
    try:
        from openai import OpenAI
        from .voice_actions import respond, safe_sources, rest_entry_requested, rest_wake_requested
        client = OpenAI(api_key=key, base_url='https://api.openai.com/v1', timeout=30, max_retries=0)
        key = None
        deadline = time.monotonic() + 120

        def allowed():
            return not stop.is_set() and time.monotonic() < deadline

        def dispatch(name, arguments):
            if not allowed():
                return {'ok': False, 'message': 'Request cancelled.'}
            pipe.send({'type': 'action', 'name': name, 'arguments': arguments})
            while allowed():
                if pipe.poll(.1):
                    return pipe.recv()
            return {'ok': False, 'message': 'Request cancelled.'}

        sources = []
        if rest_entry_requested(text) or rest_wake_requested(text):
            result = dispatch('rest-entry' if rest_entry_requested(text) else 'rest-wake', {})
            reply = result.get('message', 'Rest control is unavailable.')
        else:
            reply = respond(client, text, tools, dispatch, allowed, context['history'],
                            cite=sources.extend, personal_context=context.get('personal'),
                            memory_files=context.get('memoryFilesEnabled', False))
        if reply and allowed():
            pipe.send({'type': 'reply', 'reply': reply[:500], 'sources': safe_sources(sources)})
    except Exception as error:
        # Exceptions may contain prompts, credentials or provider responses.
        message = ('Check the OpenAI key on the PC.' if getattr(error, 'status_code', None) == 401 else
                   'Check OpenAI billing or limits on the PC.' if getattr(error, 'status_code', None) == 429 else
                   'Jarvis could not finish this request. Please try again.')
        if not stop.is_set():
            pipe.send({'type': 'error', 'message': message})
    finally:
        pipe.close()
