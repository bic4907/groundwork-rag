import json
from pathlib import Path

import pytest

from groundwork import benchmarking as batch


def setup_suite(monkeypatch, tmp_path, fail=None):
    (tmp_path/'data').mkdir()
    (tmp_path/'data/gold.jsonl').write_text('{"split":"dev"}\n{"split":"test"}\n')
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    monkeypatch.setattr(batch, 'ingest', lambda *_: None)
    calls, comparisons = [], []
    def evaluate(config, split, judge, progress):
        calls.append(config)
        progress({'completed': 1, 'total': 2, 'run_id': config+'-run', 'question': 'Example'})
        if config == fail:
            raise RuntimeError('test failure')
        progress({'completed': 2, 'total': 2, 'run_id': config+'-run', 'question': 'Example'})
        return {'run_id': config+'-run'}
    def compare(before, after, split):
        comparisons.append((before, after, split))
        return {'before': before, 'after': after, 'split': split}
    monkeypatch.setattr(batch, 'evaluate', evaluate)
    monkeypatch.setattr(batch, 'compare_runs', compare)
    return calls, comparisons


def test_suite_runs_each_configuration_once_and_compares_to_same_baseline(monkeypatch, tmp_path):
    calls, comparisons = setup_suite(monkeypatch, tmp_path)
    progress=[]
    result=batch.run_suite('all', progress=progress.append)
    assert calls == ['baseline','bm25','hybrid','sufficient']
    assert len(comparisons)==9 and all(c[0]=='baseline-run' for c in comparisons)
    assert {c[2] for c in comparisons}=={'all','dev','test'}
    assert [p['overall_completed'] for p in progress]==sorted(p['overall_completed'] for p in progress)
    assert progress[-1]['overall_completed']==progress[-1]['overall_total']==8
    saved=json.loads(next((tmp_path/'runtime/suites').glob('*.json')).read_text())
    assert saved==result and saved['status']=='completed'
    assert all((tmp_path/c['path']).is_file() for c in result['comparisons'])


def test_suite_keeps_completed_runs_and_labels_failure(monkeypatch, tmp_path):
    calls, comparisons=setup_suite(monkeypatch,tmp_path,fail='bm25')
    with pytest.raises(RuntimeError): batch.run_suite()
    saved=json.loads(next((tmp_path/'runtime/suites').glob('*.json')).read_text())
    assert saved['status']=='failed' and saved['error_type']=='RuntimeError'
    assert saved['runs']==[{'config':'baseline','run_id':'baseline-run'}]
    assert saved['progress']['config']=='bm25' and calls==['baseline','bm25']
    assert not comparisons


def test_suite_job_api_uses_batch_progress_and_result(monkeypatch):
    from fastapi.testclient import TestClient
    from groundwork import api
    class ImmediatePool:
        def submit(self, work): work()
    monkeypatch.setattr(api,'pool',ImmediatePool())
    monkeypatch.setattr(api,'jobs',{})
    def run(split, judge, progress):
        assert split=='all' and judge is False
        progress({'completed':1,'total':2,'config':'bm25','overall_completed':3,'overall_total':8})
        return {'status':'completed','runs':[{'config':'baseline','run_id':'fixture'}]}
    monkeypatch.setattr(api,'run_suite',run)
    client=TestClient(api.app)
    response=client.post('/api/jobs',json={'kind':'suite','split':'all'})
    assert response.status_code==202
    job=client.get('/api/jobs/'+response.json()['id']).json()
    assert job['status']=='completed' and job['progress']['config']=='bm25'
    assert job['result']['runs'][0]['config']=='baseline'
