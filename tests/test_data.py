import json

from groundwork.io import digest, read_jsonl
from groundwork.retrieval import chunk_documents
from groundwork.schemas import Document, GoldCase
from groundwork.settings import ROOT, load_config


def test_public_corpus_and_gold_are_consistent():
    docs = [Document.model_validate(x) for x in read_jsonl(ROOT/'data/corpus.jsonl')]
    gold = [GoldCase.model_validate(x) for x in read_jsonl(ROOT/'data/gold.jsonl')]
    manifest = json.loads((ROOT/'data/manifest.json').read_text())
    assert len(docs) >= 20 and len(gold) >= 20
    assert len({d.id for d in docs}) == len(docs)
    assert len({g.id for g in gold}) == len(gold)
    sentences = {s.id for d in docs for s in d.sentences}
    assert all(set(g.required_evidence) <= sentences for g in gold)
    assert all(g.required_evidence for g in gold if g.answerable)
    assert {'summary', 'bridge', 'unanswerable'} <= {g.category for g in gold}
    groups = {}
    for g in gold:
        assert groups.setdefault(g.source_id, g.split) == g.split
    assert digest((ROOT/'data/corpus.jsonl').read_bytes()) == manifest['corpus_sha256']
    assert digest((ROOT/'data/gold.jsonl').read_bytes()) == manifest['gold_sha256']
    text = ' '.join(s.text for d in docs for s in d.sentences).casefold()
    titles = {d.title for d in docs}
    for case in manifest['withheld_cases']:
        assert case['answer'].casefold() not in text
        assert not set(case['withheld_titles']) & titles


def test_chunking_preserves_every_sentence_and_stable_identity():
    docs = [Document.model_validate(x) for x in read_jsonl(ROOT/'data/corpus.jsonl')]
    cfg = load_config('baseline')
    chunks = chunk_documents(docs, cfg)
    assert {s for c in chunks for s in c.sentence_ids} == {s.id for d in docs for s in d.sentences}
    assert all(c.text and c.sentence_ids for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    assert chunks == chunk_documents(docs, cfg)
    changed = chunk_documents(docs, cfg.model_copy(update={'chunk_words': 60}))
    assert {s for c in changed for s in c.sentence_ids} == {s.id for d in docs for s in d.sentences}
