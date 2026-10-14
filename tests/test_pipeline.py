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


def decision(sufficient=True, chunk='c1'):
    import json
    return json.dumps({'sufficient': sufficient,
                       'reason': 'The text names the author.' if sufficient else 'The text lacks the date.',
                       'missing_facts': [] if sufficient else ['Date of the algorithm'],
                       'evidence': [{'chunk_id': chunk, 'quote': 'Ada wrote the first algorithm.'}] if sufficient else []})


def test_sufficiency_block_skips_generation_and_keeps_retrieval_and_usage():
    p = pipeline_with_responses([decision(False)])
    p.config = load_config('sufficient')
    stages = []
    result = p.answer('When was the algorithm written?', lambda stage, _: stages.append(stage))
    assert result['status'] == 'insufficient_evidence'
    assert result['validation']['reason'] == 'sufficiency_gate'
    assert result['retrieval'] == HITS
    assert result['attempts'][0]['stage'] == 'sufficiency'
    assert 'generating' not in stages
    assert result['sufficiency']['missing_facts'] == ['Date of the algorithm']


def test_sufficiency_pass_preserves_baseline_generator_input_and_can_still_abstain():
    from groundwork.pipeline import SYSTEM_PROMPT
    p = pipeline_with_responses([])
    p.config = load_config('sufficient')
    calls = []
    replies = iter([decision(), GeneratedAnswer(status='insufficient_evidence', reason='Cannot establish it.').model_dump_json()])
    def chat(messages, schema, cfg):
        calls.append((messages.copy(), cfg.max_output_tokens))
        return ModelResult(next(replies), {'input_tokens': 2, 'output_tokens': 3}, 'fixture')
    p.models.chat = chat
    result = p.answer('Who wrote the algorithm?')
    assert calls[0][0][1] == calls[1][0][1]
    assert calls[1][0][0]['content'] == SYSTEM_PROMPT
    assert calls[0][1] == 500 and calls[1][1] == 650
    assert result['status'] == 'insufficient_evidence'
    assert result['sufficiency']['sufficient'] is True
    assert [a['stage'] for a in result['attempts']] == ['sufficiency', 'answer']


def test_fabricated_gate_citation_is_repaired_before_generation():
    p = pipeline_with_responses([decision(chunk='fake'), decision(), answer().model_dump_json()])
    p.config = load_config('sufficient')
    result = p.answer('Who wrote the algorithm?')
    assert result['status'] == 'answered'
    assert [a['stage'] for a in result['attempts']] == ['sufficiency', 'sufficiency', 'answer']


def test_invalid_gate_is_an_error_with_observable_call_usage():
    p = pipeline_with_responses(['{}', '{}'])
    p.config = load_config('sufficient')
    attempts = []
    with pytest.raises(ProviderError, match='sufficiency: output validation failed'):
        p.answer('Who wrote the algorithm?', lambda stage, payload: attempts.append(payload) if stage == 'model_attempt' else None)
    assert len(attempts) == 2


def test_gate_does_not_call_model_when_retrieval_is_empty():
    p = pipeline_with_responses([])
    p.config = load_config('sufficient')
    p.retriever.search = lambda _: []
    result = p.answer('Who wrote the algorithm?')
    assert result['validation']['reason'] == 'no_evidence'
    assert result['attempts'] == []
    assert result['sufficiency'] is None
