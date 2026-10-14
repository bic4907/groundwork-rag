"""LangChain chat facade and stable embedding adapter. Errors never include headers, bodies, or URLs."""
import json
import time
from dataclasses import dataclass
from importlib.metadata import version

import httpx
import numpy as np

from .io import digest
from .settings import Settings


def execution_identity():
    return {'framework': 'langchain', 'versions': {name: version(name) for name in (
        'langchain-core', 'langchain-openrouter', 'langchain-openai', 'langchain-ollama')}}


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
        from .langchain_models import run_chat
        return run_chat(self.settings, messages, config, role)

    def cost(self, usage: dict, role='generation'):
        inp = getattr(self.settings, f'{role}_input_price')
        out = getattr(self.settings, f'{role}_output_price')
        if inp is None or out is None or any(usage.get(k) is None for k in ('input_tokens', 'output_tokens')):
            return None
        return (usage['input_tokens'] * inp + usage['output_tokens'] * out) / 1_000_000

    def chat_stream(self, messages, schema, config, on_text, cancelled=None, role='generation'):
        from .langchain_models import run_chat
        return run_chat(self.settings, messages, config, role, on_text, cancelled)
