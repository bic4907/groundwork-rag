"""Small explicit model adapters. Errors never include headers, bodies, or URLs."""
import json
import time
from dataclasses import dataclass

import httpx
import numpy as np

from .io import digest
from .settings import Settings


class ProviderError(RuntimeError):
    pass


class StreamCancelled(ProviderError):
    pass


def check_cancelled(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise StreamCancelled('Request cancelled')


def sse_data(lines):
    """SSE framing: comments and other fields are ignored; data lines are joined."""
    parts = []
    for line in lines:
        if not line:
            if parts:
                yield '\n'.join(parts)
                parts = []
        elif line.startswith('data:'):
            parts.append(line[5:].removeprefix(' '))
    if parts:
        yield '\n'.join(parts)


@dataclass
class ModelResult:
    content: str
    usage: dict
    model: str


class Models:
    def __init__(self, settings: Settings):
        self.settings = settings

    def identity(self, role: str):
        s = self.settings
        provider = getattr(s, f'{role}_provider')
        model = getattr(s, f'{role}_model')
        identity = {'provider': provider, 'model': model,
                    'endpoint_hash': digest(getattr(s, f'{role}_base_url'))}
        if provider == 'ollama':
            try:
                data = self._request(role, '/api/tags', method='GET')
                identity['digest'] = next((x['digest'] for x in data['models'] if x['name'] == model), None)
            except ProviderError:
                identity['digest'] = None
        return identity

    def _request(self, role: str, path: str, payload=None, method='POST'):
        s = self.settings
        base = getattr(s, f'{role}_base_url').rstrip('/')
        if not base:
            raise ProviderError(f'{role}: endpoint is not configured')
        key = getattr(s, f'{role}_api_key').get_secret_value()
        headers = {'Authorization': f'Bearer {key}'} if key else {}
        for attempt in range(3):
            try:
                with httpx.Client(timeout=s.api_timeout_seconds, follow_redirects=False) as client:
                    r = client.request(method, base + path, json=payload, headers=headers)
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                if not r.is_success:
                    raise ProviderError(f'{role}: HTTP {r.status_code}; check endpoint, model, and credentials')
                return r.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise ProviderError(f'{role}: {type(exc).__name__}') from None
                time.sleep(2 ** attempt)
            except (ValueError, httpx.HTTPError):
                raise ProviderError(f'{role}: invalid provider response') from None
        raise ProviderError(f'{role}: request exhausted')

    def embed(self, texts: list[str], query=False):
        s = self.settings
        # Nomic's task prefixes are part of the embedding contract and cache key.
        if 'nomic-embed-text' in s.embedding_model:
            prefix = 'search_query: ' if query else 'search_document: '
            texts = [prefix + t for t in texts]
        if s.embedding_provider == 'ollama':
            data = self._request('embedding', '/api/embed', {'model': s.embedding_model, 'input': texts, 'truncate': False})
            vectors = data['embeddings']
        else:
            data = self._request('embedding', '/embeddings', {'model': s.embedding_model, 'input': texts})
            vectors = [x['embedding'] for x in sorted(data['data'], key=lambda x: x['index'])]
        values = np.asarray(vectors, dtype=np.float32)
        if values.ndim != 2 or len(values) != len(texts) or not np.isfinite(values).all():
            raise ProviderError('embedding: invalid vector dimensions or values')
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        if (norms == 0).any():
            raise ProviderError('embedding: zero-length vector')
        return values / norms

    def chat(self, messages: list[dict], schema: dict, config, role='generation') -> ModelResult:
        s = self.settings
        provider = getattr(s, f'{role}_provider')
        model = getattr(s, f'{role}_model')
        if provider == 'disabled':
            raise ProviderError(f'{role}: disabled')
        if provider == 'ollama':
            data = self._request(role, '/api/chat', {
                'model': model, 'messages': messages, 'stream': False, 'format': 'json',
                'options': {'temperature': config.temperature, 'seed': config.seed,
                            'num_predict': config.max_output_tokens, 'num_ctx': 8192},
            })
            return ModelResult(data['message']['content'], {
                'input_tokens': data.get('prompt_eval_count'), 'output_tokens': data.get('eval_count')}, data.get('model', model))
        body = {'model': model, 'messages': messages, 'temperature': config.temperature,
                'max_tokens': config.max_output_tokens, 'response_format': {'type': 'json_object'}}
        if s.send_remote_seed:
            body['seed'] = config.seed
        data = self._request(role, '/chat/completions', body)
        usage = data.get('usage', {})
        return ModelResult(data['choices'][0]['message']['content'], {
            'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens')}, data.get('model', model))

    def cost(self, usage: dict, role='generation'):
        inp = getattr(self.settings, f'{role}_input_price')
        out = getattr(self.settings, f'{role}_output_price')
        if inp is None or out is None or any(usage.get(k) is None for k in ('input_tokens', 'output_tokens')):
            return None
        return (usage['input_tokens'] * inp + usage['output_tokens'] * out) / 1_000_000

    def chat_stream(self, messages, schema, config, on_text, cancelled=None, role='generation'):
        """Stream content only; return the full JSON and terminal usage for validation.

        Never replay a partially delivered response. Cancellation is cooperative at
        frame boundaries; a stalled upstream read remains bounded by the HTTP timeout.
        """
        s = self.settings
        provider, model = getattr(s, f'{role}_provider'), getattr(s, f'{role}_model')
        if provider == 'disabled':
            raise ProviderError(f'{role}: disabled')
        base = getattr(s, f'{role}_base_url').rstrip('/')
        if not base:
            raise ProviderError(f'{role}: endpoint is not configured')
        key = getattr(s, f'{role}_api_key').get_secret_value()
        headers = {'Authorization': f'Bearer {key}'} if key else {}
        body = {'model': model, 'messages': messages, 'stream': True}
        if provider == 'ollama':
            path = '/api/chat'
            body.update(format='json', options={'temperature': config.temperature, 'seed': config.seed,
                        'num_predict': config.max_output_tokens, 'num_ctx': 8192})
        else:
            path = '/chat/completions'
            body.update(temperature=config.temperature, max_tokens=config.max_output_tokens,
                        response_format={'type': 'json_object'}, stream_options={'include_usage': True})
            if s.send_remote_seed:
                body['seed'] = config.seed
        for attempt in range(3):
            check_cancelled(cancelled)
            chunks, size, received = [], 0, False
            usage = {'input_tokens': None, 'output_tokens': None}
            actual_model = model
            try:
                with httpx.Client(timeout=s.api_timeout_seconds, follow_redirects=False) as client:
                    with client.stream('POST', base + path, json=body, headers=headers) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            if attempt < 2:
                                time.sleep(2 ** attempt)
                                continue
                        if not response.is_success:
                            raise ProviderError(f'{role}: HTTP {response.status_code}; check endpoint, model, and credentials')
                        def lines():
                            for line in response.iter_lines():
                                check_cancelled(cancelled)
                                yield line
                        frames = lines() if provider == 'ollama' else sse_data(lines())
                        done = False
                        for frame in frames:
                            if not frame:
                                continue
                            received = True
                            if frame == '[DONE]' and provider != 'ollama':
                                done = True
                                break
                            data = json.loads(frame)
                            if not isinstance(data, dict) or data.get('error'):
                                raise ProviderError(f'{role}: upstream stream error')
                            actual_model = data.get('model') or actual_model
                            if provider == 'ollama':
                                content = data.get('message', {}).get('content') or ''
                                if data.get('done'):
                                    done = True
                                    usage = {'input_tokens': data.get('prompt_eval_count'),
                                             'output_tokens': data.get('eval_count')}
                            else:
                                choices = data.get('choices') or []
                                choice = choices[0] if choices else {}
                                if choice.get('finish_reason') == 'error':
                                    raise ProviderError(f'{role}: upstream stream error')
                                content = (choice.get('delta') or {}).get('content') or ''
                                if data.get('usage'):
                                    usage = {'input_tokens': data['usage'].get('prompt_tokens'),
                                             'output_tokens': data['usage'].get('completion_tokens')}
                            if not isinstance(content, str):
                                raise ProviderError(f'{role}: invalid stream content')
                            if content:
                                size += len(content)
                                if size > 131072:
                                    raise ProviderError(f'{role}: stream response too large')
                                chunks.append(content)
                                check_cancelled(cancelled)
                                on_text(content)
                            if done:
                                break
                        check_cancelled(cancelled)
                        if not done:
                            raise ProviderError(f'{role}: stream interrupted before completion')
                        return ModelResult(''.join(chunks), usage, actual_model)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if not received and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError(f'{role}: {type(exc).__name__}') from None
            except (ValueError, KeyError, TypeError, AttributeError, httpx.HTTPError):
                raise ProviderError(f'{role}: invalid streaming response') from None
        raise ProviderError(f'{role}: request exhausted')
