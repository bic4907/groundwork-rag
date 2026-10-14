import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from groundwork import api
from groundwork.providers import ModelResult, Models, ProviderError, StreamCancelled
from groundwork.schemas import QueryRequest
from groundwork.settings import Settings, load_config
from groundwork.streaming import answer_preview
from test_pipeline import answer, decision, pipeline_with_responses
from test_providers import mock_client


def test_partial_json_keeps_text_paths_and_unicode_across_every_boundary():
    value = {'status': 'answered', 'short_answer': '서울 "City" 😀',
             'claims': [{'text': '한 줄\n다음 줄 \\ 끝', 'evidence': [{'quote': 'PRIVATE QUOTE', 'chunk_id': 'PRIVATE ID'}]}], 'reason': ''}
    raw = json.dumps(value, ensure_ascii=True)
    for i in range(len(raw)+1):
        preview = answer_preview(raw[:i])
        assert value['short_answer'].startswith(preview['short_answer'])
        assert 'PRIVATE' not in json.dumps(preview)
        for text in preview['claims']:
            assert value['claims'][0]['text'].startswith(text)
    assert answer_preview(raw) == {'short_answer': value['short_answer'], 'claims': [value['claims'][0]['text']], 'reason': ''}


def test_preview_does_not_extract_fields_from_quote_strings_or_wrong_types():
    assert answer_preview('{"claims": null, "short_answer": 123}') == {'short_answer': '', 'claims': [], 'reason': ''}
    raw = json.dumps({'evidence': [{'text': 'Not a claim', 'quote': '"short_answer":"Fake"'}]})
    assert not any(answer_preview(raw).values())


def remote_models():
    return Models(Settings(generation_provider='remote',generation_base_url='https://models.example/v1',generation_api_key='fixture-value'))


class Pieces(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed, self.read = chunks, False, 0
    def __iter__(self):
        for chunk in self.chunks:
            self.read += 1
            yield chunk
    def close(self):
        self.closed = True


def test_remote_stream_delivers_before_completion_and_collects_terminal_usage(monkeypatch):
    stream = Pieces([b': keepalive\r\n\r\ndata: {"choices":[{"delta":{"content":"hel"}}]}\r\n\r\n',
                     b'data: {"model":"actual","choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n',
                     b'data: {"choices":[],\ndata: "usage":{"prompt_tokens":12,"completion_tokens":2}}\n\n',
                     b'data: [DONE]\n\n'])
    def handler(request):
        body = json.loads(request.content)
        assert body['stream'] is True and body['stream_options']['include_usage']
        return httpx.Response(200, stream=stream)
    mock_client(monkeypatch, handler)
    seen=[]
    result=remote_models().chat_stream([],{},load_config('baseline'),lambda t:seen.append((t,stream.read)))
    assert seen == [('hel',1),('lo',2)]
    assert result.content=='hello' and result.model=='actual'
    assert result.usage=={'input_tokens':12,'output_tokens':2}
    assert stream.closed


@pytest.mark.parametrize('ending',[b'',b'data: {"error":{"message":"secret-fixture-value"}}\n\n'])
def test_broken_stream_never_replays_or_returns_a_success(ending,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,content=b'data: {"choices":[{"delta":{"content":"draft"}}]}\n\n'+ending)
    mock_client(monkeypatch,handler)
    seen=[]
    with pytest.raises(ProviderError) as exc:
        remote_models().chat_stream([],{},load_config('baseline'),seen.append)
    assert seen==['draft'] and len(calls)==1
    assert 'secret-fixture-value' not in str(exc.value)


def test_ollama_ndjson_stream_and_usage(monkeypatch):
    def handler(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200,content=b'{"message":{"content":"{}"},"done":false}\n{"message":{"content":""},"done":true,"prompt_eval_count":7,"eval_count":2}\n')
    mock_client(monkeypatch,handler)
    seen=[]
    result=Models(Settings(generation_provider='ollama')).chat_stream([],{},load_config('baseline'),seen.append)
    assert seen==['{}'] and result.usage['input_tokens']==7


def test_cancellation_closes_upstream_and_stops_content(monkeypatch):
    stream=Pieces([b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n',
                   b'data: {"choices":[{"delta":{"content":"second"}}]}\n\n',b'data: [DONE]\n\n'])
    mock_client(monkeypatch,lambda _:httpx.Response(200,stream=stream))
    cancelled=threading.Event();seen=[]
    def on_text(text):
        seen.append(text);cancelled.set()
    with pytest.raises(StreamCancelled):
        remote_models().chat_stream([],{},load_config('baseline'),on_text,cancelled=cancelled)
    assert seen==['first'] and stream.closed


def stream_pipeline(replies):
    p=pipeline_with_responses([])
    replies=iter(replies)
    def chat_stream(messages,schema,config,on_text,cancelled=None):
        raw=next(replies)
        for i in range(0,len(raw),7):
            on_text(raw[i:i+7])
        return ModelResult(raw,{'input_tokens':5,'output_tokens':3},'fixture')
    p.models.chat_stream=chat_stream
    return p


def test_streamed_answer_validates_citations_and_resets_failed_draft():
    p=stream_pipeline([answer('invented').model_dump_json(),answer().model_dump_json()])
    events=[]
    result=p.answer('Who wrote the algorithm?',lambda e,d:events.append((e,d)),stream=True)
    assert result['status']=='answered' and result['validation']['repairs']==1
    assert result['timings']['first_draft_ms']>=0
    assert [d['attempt'] for e,d in events if e=='draft_reset']==[1,2]
    assert any(e=='repairing' for e,d in events)
    drafts=[d for e,d in events if e=='draft']
    assert len(drafts)>2 and all(d['verified'] is False for d in drafts)
    assert all('evidence' not in d and 'citations' not in d for d in drafts)
    assert [a['usage']['input_tokens'] for a in result['attempts']]==[5,5]


def test_gate_abstention_skips_streaming_generator():
    p=pipeline_with_responses([decision(False)])
    p.config=load_config('sufficient')
    events=[]
    result=p.answer('When?',lambda e,d:events.append(e),stream=True)
    assert result['status']=='insufficient_evidence' and 'draft' not in events


def test_api_stream_sends_verified_answer_only_after_drafts(monkeypatch):
    monkeypatch.setattr(api,'Pipeline',lambda *_:stream_pipeline([answer().model_dump_json()]))
    response=TestClient(api.app).post('/api/qa/stream',json={'question':'Who wrote the algorithm?','config':'baseline'})
    assert response.status_code==200
    text=response.text
    assert text.index('event: evidence')<text.index('event: draft\n')<text.index('event: validating')<text.index('event: answer')<text.index('event: done')
    assert '"citation_ids_and_quotes_valid": true' in text


def test_closing_api_iterator_signals_worker_cancellation(monkeypatch):
    stopped=threading.Event()
    def answer_method(question,emit,stream,cancelled):
        try:
            while True:
                emit('draft',{'short_answer':'pending'})
        finally:
            stopped.set()
    monkeypatch.setattr(api,'Pipeline',lambda *_:SimpleNamespace(answer=answer_method))
    class Request:
        async def is_disconnected(self): return False
    async def scenario():
        response=api.qa_stream(QueryRequest(question='Who?'),Request())
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
        assert await asyncio.to_thread(stopped.wait,2)
    asyncio.run(scenario())
