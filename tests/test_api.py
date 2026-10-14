from fastapi.testclient import TestClient

from groundwork.api import app

client=TestClient(app)


def test_workbench_and_readonly_routes_do_not_expose_credentials():
    assert client.get('/').status_code==200
    assert 'Groundwork' in client.get('/').text
    status=client.get('/api/status')
    assert status.status_code==200
    assert 'api_key' not in status.text.lower()
    assert 'base_url' not in status.text.lower()
    assert client.get('/api/corpus?limit=2').json()['total']>=20
    assert client.get('/docs').status_code==200
    schema=client.get('/openapi.json').json()
    assert schema['paths']['/api/qa']['post']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('QueryResponse')
    question=client.get('/api/gold').json()[0]
    detail=client.get('/api/gold/'+question['id']).json()
    assert {e['sentence_id'] for e in detail['evidence']}==set(question['required_evidence'])


def test_api_rejects_path_traversal_invalid_config_and_bad_question():
    assert client.post('/api/qa',json={'question':'Who is this?','config':'../../.env'}).status_code==422
    for question in ('', '  ', 'a'*2001):
        assert client.post('/api/qa',json={'question':question}).status_code==422
    assert client.get('/api/runs/invalid-run').status_code==400
    assert client.get('/api/corpus?limit=10000').status_code==400


def test_mutations_reject_foreign_origins():
    r=client.post('/api/jobs',json={'kind':'ingest'},headers={'Origin':'https://untrusted.example'})
    assert r.status_code==403


def test_dns_rebinding_host_is_rejected():
    assert client.get('/api/status',headers={'Host':'attacker.example'}).status_code==403


def test_sufficiency_configuration_and_trace_are_exposed(monkeypatch):
    from groundwork import api
    from groundwork.schemas import QueryRequest
    assert QueryRequest(question='Who is the author?', config='sufficient').config == 'sufficient'
    assert QueryRequest(question=' ㅎㅇ ').question == 'ㅎㅇ'
    assert 'sufficient' in {c['name'] for c in client.get('/api/status').json()['configs']}
    assert api.JobRequest(kind='experiment', after_config='sufficient').after_config == 'sufficient'
    from test_pipeline import pipeline_with_responses, decision
    from groundwork.settings import load_config
    p = pipeline_with_responses([decision(False)])
    p.config = load_config('sufficient')
    monkeypatch.setattr(api, 'Pipeline', lambda *_: p)
    r = client.post('/api/qa', json={'question': 'ㅎㅇ', 'config': 'sufficient'})
    assert r.status_code == 200
    assert r.json()['sufficiency']['sufficient'] is False
    assert r.json()['sufficiency_prompt_sha256']
