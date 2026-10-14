import pytest

from groundwork.evaluation import score_case, summarize, token_f1
from groundwork.schemas import GoldCase


def case(answerable=True):
    return GoldCase(id='x', source_id='x', split='test', category='bridge' if answerable else 'unanswerable',
                    question='Who?', answerable=answerable, answers=['Ada'] if answerable else [],
                    required_evidence=['s1', 's2'] if answerable else [], acceptance=[], construction='fixture')


def response(status='answered'):
    return {'status': status, 'short_answer': 'Ada' if status=='answered' else '', 'answer': 'Ada',
            'retrieval': [{'chunk': {'sentence_ids': ['s1']}}], 'validation': {'citation_ids_and_quotes_valid': True},
            'attempts': []}


def row(g, r=None, error=None):
    return {'answerable': g.answerable, 'response': r, 'elapsed_ms': 1, 'metrics': score_case(g, r, error)}


def test_multihop_recall_does_not_confuse_partial_with_complete():
    result=score_case(case(),response())
    assert result['evidence_recall']==.5
    assert result['all_evidence_found']==0


def test_refusing_everything_does_not_game_correctness():
    rows=[row(case(),response('insufficient_evidence')),row(case(False),response('insufficient_evidence'))]
    summary=summarize(rows)['metrics']
    assert summary['answer_token_f1']==0
    assert summary['abstention_precision']==.5
    assert summary['abstention_recall']==1
    assert summary['citation_validity'] is None


def test_errors_remain_in_denominators_and_are_not_abstentions():
    summary=summarize([row(case(False),None,'timeout'),row(case(False),response('insufficient_evidence'))])
    assert summary['n']==2
    assert summary['metrics']['abstention_recall']==.5
    assert summary['metrics']['error_rate']==.5


def test_generation_error_preserves_observed_retrieval():
    metrics=score_case(case(),None,'timeout',[{'chunk':{'sentence_ids':['s1','s2']}}])
    assert metrics['evidence_recall']==1
    assert metrics['answer_token_f1']==0


def test_token_f1_is_multiset_based():
    assert token_f1('the Ada','Ada')==1
    assert token_f1('Ada Ada','Ada')==pytest.approx(2/3)


def test_sufficiency_tradeoffs_and_usage_include_returned_calls_on_error():
    a = row(case(), response('insufficient_evidence'))
    b = row(case(False), response())
    c = row(case(), None, 'bad output')
    c['attempts_on_error'] = [{'stage': 'sufficiency', 'usage': {'input_tokens': 10, 'output_tokens': 2}, 'estimated_cost': .01}]
    result = summarize([a, b, c])
    assert result['metrics']['unanswerable_answer_rate'] == 1
    assert result['metrics']['answerable_abstention_rate'] == .5
    assert result['metrics']['answered_token_f1'] is None
    assert result['model_calls_by_stage']['sufficiency'] == 1
    assert result['generation_usage']['input_tokens'] == 10


def test_comparison_records_gate_intervention_and_rejects_bad_provenance(tmp_path, monkeypatch):
    import json
    import groundwork.evaluation as ev
    from groundwork.io import write_json
    from groundwork.settings import load_config
    monkeypatch.setattr(ev, 'ROOT', tmp_path)
    ids = ['20261014T000000Z-baseline-aaaaaa', '20261014T000001Z-sufficient-bbbbbb']
    manifests = []
    for run_id, name in zip(ids, ['baseline', 'sufficient']):
        m = {'status': 'completed', 'config': load_config(name).model_dump(), 'gold_sha256': 'gold',
             'generation': {'model': 'same'}, 'prompt_sha256': 'same', 'judge': None,
             'judge_prompt_sha256': 'same', 'index': {'index_id': 'same'},
             'sufficiency_prompt_sha256': 'gate' if name == 'sufficient' else None,
             'sufficiency_model': {'model': 'same'} if name == 'sufficient' else None}
        manifests.append(m)
        folder = tmp_path / 'runtime/runs' / run_id
        write_json(folder / 'manifest.json', m)
        r = {**row(case(), response()), 'id': 'x', 'source_id': 'x', 'question': 'Who?', 'split': 'dev', 'category': 'bridge'}
        (folder / 'predictions.jsonl').write_text(json.dumps(r)+'\n')
    assert ev.compare_runs(*ids, split='dev')['changed_settings'] == {'sufficiency_gate': {'before': False, 'after': True}}
    manifests[1]['sufficiency_model'] = {'model': 'other'}
    write_json(tmp_path / 'runtime/runs' / ids[1] / 'manifest.json', manifests[1])
    with pytest.raises(ValueError, match='sufficiency provenance'):
        ev.compare_runs(*ids, split='dev')
