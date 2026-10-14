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


def test_api_rejects_path_traversal_invalid_config_and_bad_question():
    assert client.post('/api/qa',json={'question':'Who is this?','config':'../../.env'}).status_code==422
    assert client.post('/api/qa',json={'question':'a'}).status_code==422
    assert client.get('/api/runs/invalid-run').status_code==400
    assert client.get('/api/corpus?limit=10000').status_code==400


def test_mutations_reject_foreign_origins():
    r=client.post('/api/jobs',json={'kind':'ingest'},headers={'Origin':'https://untrusted.example'})
    assert r.status_code==403


def test_dns_rebinding_host_is_rejected():
    assert client.get('/api/status',headers={'Host':'attacker.example'}).status_code==403
