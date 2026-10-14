"""Rebuild the checked-in benchmark from a pinned, checksummed public artifact."""
import json
from collections import Counter
from urllib.parse import quote

import httpx
import pyarrow.parquet as pq

from .io import atomic_text, digest, write_json
from .schemas import Document, GoldCase, Sentence
from .settings import ROOT

REVISION = '1908d6afbbead072334abe2965f91bd2709910ab'
SOURCE_URL = f'https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/{REVISION}/distractor/validation-00000-of-00001.parquet'
SOURCE_HASH = 'c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6'


def row_documents(row):
    docs = {}
    for title, texts in zip(row['context']['title'], row['context']['sentences'], strict=True):
        doc_id = 'd-' + digest([title, texts])[:16]
        docs[title] = Document(id=doc_id, title=title,
                              url='https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_'), safe=''),
                              sentences=[Sentence(id=f'{doc_id}:s{i}', text=t.strip()) for i, t in enumerate(texts)])
    return docs


def support(row, docs):
    return [docs[t].sentences[i].id for t, i in zip(row['supporting_facts']['title'],
                                                  row['supporting_facts']['sent_id'], strict=True)]


def build_dataset():
    path = ROOT / 'data/raw/hotpot-validation.parquet'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            response = client.get(SOURCE_URL)
            response.raise_for_status()
        path.write_bytes(response.content)
    if digest(path.read_bytes()) != SOURCE_HASH:
        raise ValueError('Upstream dataset checksum mismatch; do not silently refresh it')
    rows = sorted(pq.read_table(path).to_pylist(), key=lambda x: digest(['groundwork-v1', x['id']]))
    selected, used_titles = [], set()
    for category in ('bridge', 'comparison'):
        for row in rows:
            titles = set(row['supporting_facts']['title'])
            if row['type'] != category or titles & used_titles:
                continue
            docs = row_documents(row)
            try:
                support(row, docs)
            except (KeyError, IndexError):
                continue
            selected.append(row)
            used_titles |= titles
            if sum(r['type'] == category for r in selected) == 12:
                break
    corpus, gold = {}, []
    for n, row in enumerate(selected):
        docs = row_documents(row)
        corpus.update({d.id: d for d in docs.values()})
        gold.append(GoldCase(id=row['id'], source_id=row['id'], split='dev' if n % 3 == 0 else 'test',
            category=row['type'], question=row['question'], answerable=True, answers=[row['answer']],
            required_evidence=support(row, docs),
            acceptance=[f"The direct answer is {row['answer']}.", 'Explain the connection or comparison using all required supporting facts.'],
            construction='Original HotpotQA question, answer and sentence-level supporting facts; deterministic sample.'))
    # Summary variants stay in their parent question's split. They are not human labels.
    for n in [0, 1, 2, 3, 12, 13, 14, 15]:
        row = selected[n]
        docs = row_documents(row)
        doc = docs[row['supporting_facts']['title'][0]]
        facts = [s for s in doc.sentences if len(s.text.split()) >= 5][:2]
        gold.append(GoldCase(id=row['id'] + '-summary', source_id=row['id'], split=gold[n].split,
            category='summary', question=f'Summarize the main facts about {doc.title} in two sentences, focusing on the first two substantive statements in its document.',
            answerable=True, answers=[' '.join(s.text for s in facts)], required_evidence=[s.id for s in facts],
            acceptance=[s.text for s in facts] + ['Preserve these facts in a concise paraphrase; do not add unsupported facts.'],
            construction='Deterministic source-grounded summary task; reference copies two source sentences. Human review pending.'))
    # Controlled evidence removal: remove a necessary article, and reject cases whose
    # reference answer appears anywhere in the remaining pooled corpus.
    withheld, no_answer = set(), []
    for row in rows:
        if len(no_answer) == 8:
            break
        if row['type'] != 'bridge' or len(row['answer']) < 5:
            continue
        titles = set(row['supporting_facts']['title'])
        if titles & used_titles or titles & withheld:
            continue
        docs = row_documents(row)
        removable = [t for t in titles if row['answer'].casefold() in ' '.join(s.text for s in docs[t].sentences).casefold()]
        if not removable:
            continue
        drop = set(removable)
        if drop & {d.title for d in corpus.values()}:
            continue
        candidates = {d.id: d for t, d in docs.items() if t not in drop | withheld}
        pooled = {**corpus, **candidates}
        if any(row['answer'].casefold() in ' '.join(s.text for s in d.sentences).casefold() for d in pooled.values()):
            continue
        # New distractors must not accidentally restore an earlier withheld answer.
        if any(x['answer'].casefold() in ' '.join(s.text for s in d.sentences).casefold() for x in no_answer for d in candidates.values()):
            continue
        corpus = pooled
        withheld |= drop
        used_titles |= titles
        no_answer.append({'id': row['id'], 'answer': row['answer'], 'withheld_titles': sorted(drop)})
        gold.append(GoldCase(id=row['id'] + '-missing', source_id=row['id'], split='dev' if (len(no_answer)-1) % 3 == 0 else 'test',
            category='unanswerable', question=row['question'], answerable=False, answers=[], required_evidence=[],
            acceptance=['Return insufficient_evidence.', 'Do not guess the missing fact or use model memory.'],
            construction='A necessary supporting article was removed from the whole corpus. Reference answer string absent from the remaining corpus; implicit alternate proofs remain a limitation.'))
    if len(gold) != 40 or len(corpus) < 20:
        raise ValueError('Dataset construction failed the required size invariants')
    if withheld & {d.title for d in corpus.values()}:
        raise ValueError('Withheld evidence reintroduced')
    corpus_text = ''.join(d.model_dump_json() + '\n' for d in sorted(corpus.values(), key=lambda d: d.id))
    gold_text = ''.join(g.model_dump_json() + '\n' for g in gold)
    atomic_text(ROOT / 'data/corpus.jsonl', corpus_text)
    atomic_text(ROOT / 'data/gold.jsonl', gold_text)
    manifest = {'name': 'Groundwork Hotpot Mini v1', 'upstream': SOURCE_URL, 'upstream_revision': REVISION,
                'upstream_sha256': SOURCE_HASH, 'license': 'CC-BY-SA-4.0', 'sampling_version': 1,
                'documents': len(corpus), 'questions': len(gold),
                'categories': dict(Counter(g.category for g in gold)), 'splits': dict(Counter(g.split for g in gold)),
                'corpus_sha256': digest(corpus_text.encode()), 'gold_sha256': digest(gold_text.encode()),
                'withheld_cases': no_answer, 'human_review': 'pending',
                'limitations': ['English Wikipedia introductory paragraphs, historical snapshot.',
                    'Small purposive sample, not an official HotpotQA benchmark score.',
                    'Parent question and derived summary correlated; keep grouped in analysis.',
                    'Controlled absence is easier than naturally ambiguous questions.',
                    'Answer-string absence is not a proof that every alternate inference is impossible.',
                    'Public benchmark may overlap model pretraining.']}
    write_json(ROOT / 'data/manifest.json', manifest)
    return manifest
