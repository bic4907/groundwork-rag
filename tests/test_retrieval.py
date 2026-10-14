from types import SimpleNamespace

import numpy as np

from groundwork.retrieval import Retriever
from groundwork.schemas import Chunk
from groundwork.settings import load_config


def retriever(mode):
    r = Retriever.__new__(Retriever)
    r.config = load_config(mode).model_copy(update={'top_k': 1, 'candidate_k': 2})
    r.chunks = [Chunk(id=f'c{i}', document_id=f'd{i}', title=f'Doc {i}', url='https://example.org',
                      text=f'Evidence {i}', sentence_ids=[f's{i}']) for i in range(3)]
    r.vectors = np.asarray([[1., 0.], [.9, .1], [.1, .9]])
    r.cache = SimpleNamespace(embed=lambda *a, **kw: np.asarray([[1., 0.]]))
    r.bm25 = SimpleNamespace(get_scores=lambda q: np.asarray([0., 10., 2.]))
    return r


def test_hybrid_combines_ranked_evidence_not_raw_score_scales():
    assert retriever('baseline').search('question')[0]['chunk']['id']=='c0'
    assert retriever('hybrid').search('question')[0]['chunk']['id']=='c1'
    assert retriever('bm25').search('question')[0]['chunk']['id']=='c1'


def test_context_budget_preserves_complete_chunks():
    r=retriever('baseline')
    r.config=r.config.model_copy(update={'max_context_chars':5})
    assert r.search('question')==[]
