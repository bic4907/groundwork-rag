"""LangChain chat adapters with the existing wire and failure contracts."""
import codecs
import json
import time
from contextlib import ExitStack
from urllib.parse import urlparse

import httpx
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama
from langsmith import tracing_context
from openrouter import OpenRouter

from .providers import ModelResult, ProviderError, StreamCancelled, check_cancelled, sse_data


class CompatibleChatOpenAI(ChatOpenAI):
    """Keep the original generic /chat/completions payload, including max_tokens."""
    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if 'max_completion_tokens' in payload:
            payload['max_tokens'] = payload.pop('max_completion_tokens')
        for message in payload['messages']:
            if message['role'] == 'developer':
                message['role'] = 'system'
        return payload


class WireState:
    """Observe terminal markers/raw usage; SDKs can otherwise accept truncated streams.

    Parsing/generation is performed by the LangChain integration. This observer also
    preserves absent usage as None instead of accepting SDK-inferred zero counts.
    """
    def __init__(self, role, provider, streaming, cancelled):
        self.role, self.provider, self.streaming, self.cancelled = role, provider, streaming, cancelled
        self.status = None
        self.received = self.done = self.error = False
        self.usage = {'input_tokens': None, 'output_tokens': None}
        self.model = None
        self.responses = []
        self.buffer = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')()

    def observe(self, data):
        if not isinstance(data, dict):
            raise ProviderError(f'{self.role}: invalid provider response')
        self.received = True
        self.model = data.get('model') or self.model
        self.error |= bool(data.get('error'))
        if self.provider == 'ollama':
            self.done |= bool(data.get('done'))
            if data.get('done') or not self.streaming:
                self.usage = {'input_tokens': data.get('prompt_eval_count'), 'output_tokens': data.get('eval_count')}
        else:
            if data.get('usage'):
                self.usage = {'input_tokens': data['usage'].get('prompt_tokens'),
                              'output_tokens': data['usage'].get('completion_tokens')}
            self.error |= any(c.get('finish_reason') == 'error' for c in data.get('choices') or [])

    def feed(self, raw, final=False):
        check_cancelled(self.cancelled)
        self.buffer += self.decoder.decode(raw, final=final)
        self.buffer = self.buffer.replace('\r\n', '\n')
        delimiter = '\n' if self.provider == 'ollama' else '\n\n'
        while delimiter in self.buffer:
            block, self.buffer = self.buffer.split(delimiter, 1)
            self.frame(block)
        if len(self.buffer) > 1048576:
            raise ProviderError(f'{self.role}: stream frame too large')
        if final and self.buffer:
            self.frame(self.buffer)
            self.buffer = ''

    def frame(self, block):
        frames = [block] if self.provider == 'ollama' else sse_data(block.split('\n'))
        for frame in frames:
            if not frame.strip():
                continue
            if frame == '[DONE]' and self.provider != 'ollama':
                self.done = True
            else:
                self.observe(json.loads(frame))

    def hook(self, response):
        self.status = response.status_code
        self.responses.append(response)
        if not response.is_success:
            return
        if not self.streaming:
            response.read()
            self.observe(response.json())
            return
        if response.is_stream_consumed:
            self.feed(response.content, final=True)
            return
        state, original = self, response.stream
        class ObservedStream(httpx.SyncByteStream):
            def __iter__(self):
                for raw in original:
                    state.feed(raw)
                    yield raw
                state.feed(b'', final=True)
            def close(self):
                original.close()
        response.stream = ObservedStream()

    def close(self):
        for response in self.responses:
            response.close()


def build_model(settings, role, config, wire, stack):
    provider = getattr(settings, f'{role}_provider')
    model = getattr(settings, f'{role}_model')
    base = getattr(settings, f'{role}_base_url').rstrip('/')
    key = getattr(settings, f'{role}_api_key').get_secret_value()
    if provider == 'disabled':
        raise ProviderError(f'{role}: disabled')
    if not base:
        raise ProviderError(f'{role}: endpoint is not configured')
    kwargs = {'timeout': settings.api_timeout_seconds, 'follow_redirects': False,
              'event_hooks': {'response': [wire.hook]}}
    if provider == 'ollama':
        llm = ChatOllama(model=model, base_url=base, format='json', temperature=config.temperature,
                         seed=config.seed, num_predict=config.max_output_tokens, num_ctx=8192,
                         client_kwargs=kwargs | {'headers': {'Authorization': f'Bearer {key}'} if key else {}},
                         validate_model_on_init=False, cache=False)
        stack.callback(llm._client.close)
        return llm
    client = stack.enter_context(httpx.Client(**kwargs))
    common = dict(model=model, temperature=config.temperature, max_tokens=config.max_output_tokens,
                  api_key=key or 'not-configured', base_url=base, max_retries=0, cache=False,
                  seed=config.seed if settings.send_remote_seed else None)
    if urlparse(base).hostname == 'openrouter.ai':
        sdk = OpenRouter(api_key=key, server_url=base, client=client, retry_config=None,
                         timeout_ms=int(settings.api_timeout_seconds*1000))
        return ChatOpenRouter(**common, client=sdk, stream_usage=True,
                              app_url=None, app_title=None)
    return CompatibleChatOpenAI(**common, http_client=client, timeout=settings.api_timeout_seconds,
                                stream_usage=True, use_responses_api=False)


def run_chat(settings, messages, config, role='generation', on_text=None, cancelled=None):
    streaming = on_text is not None
    provider = getattr(settings, f'{role}_provider')
    for attempt in range(3):
        check_cancelled(cancelled)
        wire = WireState(role, provider, streaming, cancelled)
        try:
            with ExitStack() as stack, tracing_context(enabled=False):
                stack.callback(wire.close)
                llm = build_model(settings, role, config, wire, stack)
                # Keep json_object/json mode: enabling tools or strict schemas would
                # change the evaluated request and its repair/abstention behavior.
                options = {'stream': streaming} if provider == 'ollama' else {'response_format': {'type': 'json_object'}}
                if isinstance(llm, CompatibleChatOpenAI):
                    # Preserve JSON mode without SDK structured-output parsing.
                    options = {'extra_body': options}
                bound = llm.bind(**options)
                chain = ChatPromptTemplate.from_messages([MessagesPlaceholder('messages')]) | bound
                if streaming:
                    pieces, size = [], 0
                    iterator = chain.stream({'messages': messages})
                    stack.callback(iterator.close)
                    for chunk in iterator:
                        check_cancelled(cancelled)
                        content = chunk.content
                        if not isinstance(content, str):
                            raise ProviderError(f'{role}: invalid stream content')
                        size += len(content)
                        if size > 131072:
                            raise ProviderError(f'{role}: stream response too large')
                        if content:
                            pieces.append(content)
                            on_text(content)
                    check_cancelled(cancelled)
                    if not wire.done:
                        raise ProviderError(f'{role}: stream interrupted before completion')
                    content = ''.join(pieces)
                else:
                    content = chain.invoke({'messages': messages}).content
                if wire.error:
                    raise ProviderError(f'{role}: upstream stream error')
                if not isinstance(content, str):
                    raise ProviderError(f'{role}: invalid provider content')
                return ModelResult(content, wire.usage, wire.model or getattr(settings, f'{role}_model'))
        except StreamCancelled:
            raise
        except Exception as exc:
            # Never include SDK exception text: it can contain URL, key, or body.
            retryable = wire.status == 429 or (wire.status is not None and wire.status >= 500)
            retryable |= isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or type(exc).__name__ in {'APITimeoutError', 'APIConnectionError'}
            if retryable and attempt < 2 and not (streaming and wire.received):
                time.sleep(2**attempt)
                continue
            if isinstance(exc, ProviderError):
                raise
            if wire.status is not None and not 200 <= wire.status < 300:
                raise ProviderError(f'{role}: HTTP {wire.status}; check endpoint, model, and credentials') from None
            raise ProviderError(f'{role}: invalid provider response ({type(exc).__name__})') from None
    raise ProviderError(f'{role}: request exhausted')
