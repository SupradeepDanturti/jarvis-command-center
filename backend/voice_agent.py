"""Optional OpenAI Agents SDK orchestration, imported only by an enabled voice worker."""
import asyncio
import json
import logging
import os

# Force privacy defaults before importing the SDK, even if the environment enables debug traces.
os.environ['OPENAI_AGENTS_DONT_LOG_MODEL_DATA'] = '1'
os.environ['OPENAI_AGENTS_DONT_LOG_TOOL_DATA'] = '1'
os.environ['OPENAI_AGENTS_DISABLE_TRACING'] = '1'
logging.getLogger('openai.agents').disabled = True

from agents import Agent, FunctionTool, ModelSettings, OpenAIResponsesModel, RunConfig, Runner, WebSearchTool, set_tracing_disabled
from openai import AsyncOpenAI
from openai.types.shared import Reasoning

from .voice_actions import VOICE_MODEL, response_sources, safe_sources, spoken_reply

set_tracing_disabled(True)


class VoiceCancelled(Exception):
    pass


def async_client(client):
    # Reuse the decrypted worker key without SDK global credentials or server-side conversation storage.
    return AsyncOpenAI(api_key=client.api_key, base_url='https://api.openai.com/v1', timeout=30, max_retries=0)


class JarvisModel(OpenAIResponsesModel):
    def __init__(self, client, allowed, sources):
        super().__init__(VOICE_MODEL, client)
        self.allowed, self.sources = allowed, sources

    async def get_response(self, *args, **kwargs):
        if not self.allowed():
            raise VoiceCancelled()
        response = await super().get_response(*args, **kwargs)
        if not self.allowed():
            raise VoiceCancelled()
        self.sources.extend(response_sources(response))
        return response


async def _run_turn(client, instructions, text, tools, dispatch, allowed, history, cite):
    # SDK function tasks can coexist, but our single parent pipe and physical controls remain serialized.
    pipe_lock = asyncio.Lock()
    completed, slots, results, sources = {}, set(), [], []

    def wrap(spec):
        async def invoke(context, raw):
            async with pipe_lock:
                if not allowed():
                    raise VoiceCancelled()
                try:
                    arguments = json.loads(raw)
                    if not isinstance(arguments, dict):
                        raise ValueError()
                except (ValueError, TypeError):
                    return {'ok': False, 'message': 'Invalid action arguments.'}
                key = (spec['name'], json.dumps(arguments, sort_keys=True))
                if key in completed:
                    return completed[key]  # Never repeat even a timed-out or failed physical request.
                slot = ('physical' if spec['name'] in {'launch_app', 'media_control'} else
                        'screen' if spec['name'] == 'show_screen' else 'read')
                if slot in slots:
                    return {'ok': False, 'message': 'One PC control, one screen request and one hardware read per turn.'}
                slots.add(slot)
                # Reserve before sending. A follow-up failure or extra SDK round cannot retry this operation.
                completed[key] = {'ok': False, 'message': 'This action could not be carried out.'}
                try:
                    result = await asyncio.to_thread(dispatch, spec['name'], arguments)
                    completed[key] = result
                except Exception:
                    result = completed[key]
                results.append(result)
                return result
        return FunctionTool(name=spec['name'], description=spec['description'],
                            params_json_schema=spec['parameters'], on_invoke_tool=invoke,
                            strict_json_schema=True)

    sdk_tools = [WebSearchTool(search_context_size='low') if spec['type'] == 'web_search' else wrap(spec) for spec in tools]
    settings = ModelSettings(parallel_tool_calls=True, store=False, reasoning=Reasoning(effort='none'),
                             max_tokens=350, extra_args={'max_tool_calls': 2}, retry={'max_retries': 0})
    try:
        async with async_client(client) as connection:
            agent = Agent(name='Jarvis', instructions=instructions, model=JarvisModel(connection, allowed, sources),
                          tools=sdk_tools, model_settings=settings)
            result = await Runner.run(agent, [*(history or [])[-12:], {'role': 'user', 'content': text[:1000]}],
                                      max_turns=3, run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False))
            return spoken_reply(str(result.final_output or 'Please repeat that, sir.')) if allowed() else ''
    except VoiceCancelled:
        return ''
    except Exception:
        if not allowed():
            return ''
        if not results:
            raise
        # Completed actions stand; report their actual results when the agent's follow-up fails.
        return spoken_reply(' '.join(str(result.get('message') or ('Done.' if result.get('ok') else 'The action failed.')) for result in results))
    finally:
        cite(safe_sources(sources))


def run_turn(client, instructions, text, tools, dispatch, allowed, history, cite):
    return asyncio.run(_run_turn(client, instructions, text, tools, dispatch, allowed, history, cite))
