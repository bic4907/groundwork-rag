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
