"""Mock only the SDK's network transport; tests run the actual Agent/Runner loop."""
from types import SimpleNamespace
import time

import pytest


@pytest.fixture
def jarvis_sdk_transport(monkeypatch):
    import backend.agent.voice_agent as voice_agent
    from openai.types.responses import Response
    from httpx2 import URL

    class FakeClient:
        def __init__(self, client):
            self.base_url = URL('https://api.openai.com/v1')
            self.responses = SimpleNamespace(create=self.create)
            self.client = client

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def create(self, **kwargs):
            response = self.client.responses.create(**kwargs)
            if isinstance(response, Response):
                return response
            output = []
            for index, item in enumerate(response.output):
                if item.type == 'function_call':
                    output.append({'type': 'function_call', 'id': f'fc_{index}', 'name': item.name,
                                   'arguments': item.arguments, 'call_id': item.call_id})
                elif item.type == 'web_search_call':
                    output.append({'type': 'web_search_call', 'id': 'search_qa', 'status': 'completed',
                                   'action': {'type': 'search', 'query': 'QA search'}})
                elif item.type == 'message':
                    annotations = [dict(type='url_citation', url=annotation.url, title=annotation.title,
                                        start_index=0, end_index=1)
                                   for content in getattr(item, 'content', [])
                                   for annotation in getattr(content, 'annotations', [])]
                    output.append({'type': 'message', 'id': f'msg_{index}', 'role': 'assistant', 'status': 'completed',
                                   'content': [{'type': 'output_text', 'text': response.output_text,
                                                'annotations': annotations}]})
            if response.output_text and not any(item['type'] == 'message' for item in output):
                output.append({'type': 'message', 'id': 'msg_qa', 'role': 'assistant', 'status': 'completed',
                               'content': [{'type': 'output_text', 'text': response.output_text, 'annotations': []}]})
            return Response(id='resp_qa', created_at=time.time(), model='gpt-6-luna', object='response', output=output,
                            parallel_tool_calls=True, tool_choice='auto', tools=[], usage=None)

    monkeypatch.setattr(voice_agent, 'async_client', FakeClient)
