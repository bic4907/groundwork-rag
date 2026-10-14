import json

import httpx
import pytest
from langchain_core.runnables import RunnableSequence

from groundwork import langchain_models as lc
from groundwork.providers import Models, ProviderError
from groundwork.settings import Settings, load_config
from groundwork.pipeline import SYSTEM_PROMPT
from test_providers import mock_client
from test_streaming import Pieces


def router():
    return Models(Settings(_env_file=None, generation_provider='remote',
                          generation_base_url='https://openrouter.ai/api/v1',
                          generation_model='fixture-model', generation_api_key='fixture-value'))


def completion(content='{}', stream=False, usage=True):
    choice={'index':0,'finish_reason':'stop','logprobs':None}
    choice['delta' if stream else 'message']={'role':'assistant','content':content}
    result={'id':'fixture-id','created':1,'model':'fixture-model','system_fingerprint':None,
            'object':'chat.completion.chunk' if stream else 'chat.completion','choices':[choice]}
    if usage: result['usage']={'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}
    return result


def test_openrouter_uses_langchain_chain_with_identical_messages_and_parameters(monkeypatch):
    messages=[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':'{"question":"Who?","evidence":[]}'}]
    def handler(request):
        assert request.url.path=='/api/v1/chat/completions'
        body=json.loads(request.content)
        assert body['messages']==messages
        assert body['model']=='fixture-model' and body['temperature']==0
        assert body['max_tokens']==650 and body['stream'] is False
        assert body['response_format']=={'type':'json_object'}
        assert all(k not in body for k in ('tools','seed','reasoning','max_completion_tokens'))
        return httpx.Response(200,json=completion())
    mock_client(monkeypatch,handler)
    original=RunnableSequence.invoke; chains=[]
    def invoke(self,*args,**kwargs):
        chains.append(self)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(RunnableSequence,'invoke',invoke)
    result=router().chat(messages,{},load_config('baseline'))
    assert result.content=='{}' and result.model=='fixture-model'
    assert result.usage=={'input_tokens':12,'output_tokens':3} and chains


def test_openrouter_streams_through_langchain_and_preserves_terminal_usage(monkeypatch):
    one=completion('hel',stream=True,usage=False);one['choices'][0]['finish_reason']=None
    two=completion('lo',stream=True,usage=False)
    usage=completion('',stream=True);usage['choices']=[]
    frames=[('data: '+json.dumps(x)+'\n\n').encode() for x in (one,two,usage)]+[b'data: [DONE]\n\n']
    stream=Pieces(frames)
    def handler(request):
        body=json.loads(request.content)
        assert body['stream'] and body['stream_options']=={'include_usage':True}
        assert body['max_tokens']==650
        return httpx.Response(200,headers={'Content-Type':'text/event-stream'},stream=stream)
    mock_client(monkeypatch,handler);seen=[]
    result=router().chat_stream([],{},load_config('baseline'),lambda t:seen.append((t,stream.read)))
    assert seen==[('hel',1),('lo',2)]
    assert result.content=='hello' and result.usage=={'input_tokens':12,'output_tokens':3}
    assert stream.closed


def test_missing_usage_remains_unknown(monkeypatch):
    mock_client(monkeypatch,lambda _:httpx.Response(200,json=completion(usage=False)))
    assert router().chat([],{},load_config('baseline')).usage=={'input_tokens':None,'output_tokens':None}


def test_openrouter_retries_are_bounded_without_sdk_nested_retries(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(503,json={'error':{'message':'private response'}})
    mock_client(monkeypatch,handler)
    monkeypatch.setattr(lc.time,'sleep',lambda _:None)
    with pytest.raises(ProviderError,match='HTTP 503') as error:router().chat([],{},load_config('baseline'))
    assert len(calls)==3 and 'private response' not in str(error.value)


def test_ollama_sync_keeps_json_mode_seed_and_context_options(monkeypatch):
    def handler(request):
        body=json.loads(request.content)
        assert body['stream'] is False and body['format']=='json'
        assert body['options']=={'temperature':0,'seed':42,'num_predict':650,'num_ctx':8192}
        assert body['messages'][0]['role']=='system' and body['messages'][0]['content']==SYSTEM_PROMPT
        return httpx.Response(200,json={'model':'fixture-local','message':{'role':'assistant','content':'{}'},
                                       'done':True,'prompt_eval_count':8,'eval_count':2})
    mock_client(monkeypatch,handler)
    models=Models(Settings(_env_file=None,generation_provider='ollama',generation_model='fixture-local'))
    result=models.chat([{'role':'system','content':SYSTEM_PROMPT}],{},load_config('baseline'))
    assert result.content=='{}' and result.usage=={'input_tokens':8,'output_tokens':2}
