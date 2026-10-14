from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from groundwork.pipeline import Pipeline, validate_citations
from groundwork.providers import ModelResult, ProviderError
from groundwork.schemas import GeneratedAnswer
from groundwork.settings import load_config

HITS = [{'chunk': {'id': 'c1', 'document_id': 'd1', 'title': 'Example', 'url': 'https://example.org',
                   'text': 'Ada wrote the first algorithm.', 'sentence_ids': ['s1']},
         'score': 1.0, 'dense_score': 1.0, 'bm25_score': 1.0}]


def answer(chunk='c1', quote='Ada wrote the first algorithm.'):
    return GeneratedAnswer(status='answered', short_answer='Ada', claims=[{
        'text': 'Ada wrote an algorithm.', 'evidence': [{'chunk_id': chunk, 'quote': quote}]}])


def test_citations_must_reference_visible_chunks_and_verbatim_quotes():
    assert validate_citations(answer(), HITS) == []
    assert validate_citations(answer('invented'), HITS) == ['unknown_chunk']
    assert validate_citations(answer(quote='Ada invented a computer.'), HITS) == ['quote_not_found']


def test_abstention_cannot_smuggle_an_answer():
    with pytest.raises(ValidationError):
        GeneratedAnswer(status='insufficient_evidence', short_answer='A guess')
    with pytest.raises(ValidationError):
        GeneratedAnswer(status='answered', short_answer='Uncited answer')


def pipeline_with_responses(responses):
    p = Pipeline.__new__(Pipeline)
    p.config = load_config('baseline')
    p.retriever = SimpleNamespace(search=lambda _: HITS, manifest={'index_id': 'test'})
    iterator = iter(responses)
    p.models = SimpleNamespace(chat=lambda *a, **kw: ModelResult(next(iterator), {'input_tokens': 1, 'output_tokens': 1}, 'fixture'), cost=lambda usage: None)
    return p


def test_invalid_citation_is_repaired_and_attempts_are_accounted():
    p = pipeline_with_responses([answer('fake').model_dump_json(), answer().model_dump_json()])
    result = p.answer('Who wrote the algorithm?')
    assert result['validation']['repairs'] == 1
    assert len(result['attempts']) == 2
    assert result['citations'][0]['quote'] == 'Ada wrote the first algorithm.'


def test_persistent_invalid_output_is_error_not_successful_abstention():
    p = pipeline_with_responses(['{"nope":true}', '{"nope":true}'])
    with pytest.raises(ProviderError, match='output validation failed'):
        p.answer('Who wrote the algorithm?')
