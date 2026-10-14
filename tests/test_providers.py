import httpx
import numpy as np
import pytest

from groundwork.providers import Models, ProviderError
from groundwork.settings import Settings, load_config


def mock_client(monkeypatch, handler):
    class MockClient(httpx.Client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, 'Client', MockClient)


def test_remote_embedding_sorts_indices_and_normalizes(monkeypatch):
    def handler(request):
        assert request.url.path=='/v1/embeddings'
        assert request.headers['Authorization']=='Bearer fixture-value'
        return httpx.Response(200,json={'data':[{'index':1,'embedding':[0,2]},{'index':0,'embedding':[3,0]}]})
    mock_client(monkeypatch,handler)
    settings=Settings(embedding_provider='remote',embedding_base_url='https://models.example/v1',
                      embedding_model='fixture-embedding',embedding_api_key='fixture-value')
    assert np.allclose(Models(settings).embed(['one','two']),np.eye(2))


def test_provider_errors_do_not_echo_secrets_or_response_bodies(monkeypatch):
    mock_client(monkeypatch,lambda request:httpx.Response(401,json={'error':'sensitive fixture body'}))
    model=Models(Settings(generation_provider='remote',generation_base_url='https://private.example/v1',generation_api_key='fixture-value'))
    with pytest.raises(ProviderError) as exc:
        model.chat([],{},load_config('baseline'))
    assert 'HTTP 401' in str(exc.value)
    assert all(x not in str(exc.value) for x in ('fixture-value','sensitive','private.example'))


def test_remote_generation_maps_usage_and_does_not_send_seed_by_default(monkeypatch):
    import json
    def handler(request):
        payload=json.loads(request.content)
        assert 'seed' not in payload
        assert payload['response_format']=={'type':'json_object'}
        return httpx.Response(200,json={'model':'pinned-fixture','choices':[{'message':{'role':'assistant','content':'{}'}}],
                                       'usage':{'prompt_tokens':100,'completion_tokens':20}})
    mock_client(monkeypatch,handler)
    models=Models(Settings(generation_provider='remote',generation_base_url='https://models.example/v1',
                           generation_input_price=1,generation_output_price=2))
    result=models.chat([],{},load_config('baseline'))
    assert result.usage=={'input_tokens':100,'output_tokens':20}
    assert models.cost(result.usage)==pytest.approx(.00014)
