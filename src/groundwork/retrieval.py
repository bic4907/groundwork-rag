import json
import re
import sqlite3
import threading
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .io import atomic_text, digest, read_jsonl, write_json
from .providers import Models
from .schemas import Chunk, Document
from .settings import ROOT, ExperimentConfig

INDEX_LOCK = threading.Lock()


def tokenize(text):
    return re.findall(r"[\w]+", text.lower())


def chunk_documents(documents: list[Document], config: ExperimentConfig) -> list[Chunk]:
    result = []
    for doc in documents:
        start = 0
        while start < len(doc.sentences):
            end, size = start, 0
            while end < len(doc.sentences):
                added = len(doc.sentences[end].text.split())
                if end > start and size + added > config.chunk_words:
                    break
                size += added
                end += 1
            sentences = doc.sentences[start:end]
            text = ' '.join(s.text.strip() for s in sentences)
            result.append(Chunk(id='c-' + digest([doc.id, [s.id for s in sentences], text])[:16],
                                document_id=doc.id, title=doc.title, url=doc.url, text=text,
                                sentence_ids=[s.id for s in sentences]))
            if end == len(doc.sentences):
                break
            start = max(start + 1, end - config.overlap_sentences)
    return result


class EmbeddingCache:
    def __init__(self, models: Models, identity: dict):
        self.models = models
        self.identity = identity
        path = ROOT / 'runtime/cache/embeddings.sqlite3'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)')

    def embed(self, texts, query=False):
        keys = [digest([self.identity, 'query' if query else 'document', t]) for t in texts]
        with sqlite3.connect(self.path, timeout=30) as db:
            cached = [db.execute('SELECT vector FROM embeddings WHERE key=?', (k,)).fetchone() for k in keys]
        result = [json.loads(x[0]) if x else None for x in cached]
        missing = [i for i, x in enumerate(result) if x is None]
        for offset in range(0, len(missing), 16):
            indices = missing[offset:offset + 16]
            values = self.models.embed([texts[i] for i in indices], query=query)
            with sqlite3.connect(self.path, timeout=30) as db:
                for i, value in zip(indices, values, strict=True):
                    result[i] = value.tolist()
                    db.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?)', (keys[i], json.dumps(result[i])))
        return np.asarray(result, dtype=np.float32)


def index_signature(config, identity):
    return {'corpus_sha256': digest((ROOT / 'data/corpus.jsonl').read_bytes()),
            'chunk_words': config.chunk_words, 'overlap_sentences': config.overlap_sentences,
            'embedding': identity, 'format_version': 1}


def ingest(config: ExperimentConfig, models: Models):
    with INDEX_LOCK:
        identity = models.identity('embedding')
        signature = index_signature(config, identity)
        index_id = digest(signature)[:20]
        folder = ROOT / 'runtime/indexes' / index_id
        if (folder / 'manifest.json').exists():
            return json.loads((folder / 'manifest.json').read_text())
        documents = [Document.model_validate(d) for d in read_jsonl(ROOT / 'data/corpus.jsonl')]
        chunks = chunk_documents(documents, config)
        cache = EmbeddingCache(models, identity)
        vectors = cache.embed([c.title + '\n' + c.text for c in chunks])
        folder.mkdir(parents=True, exist_ok=True)
        # Manifest is written last; readers never observe an incomplete index.
        np.save(folder / 'vectors.npy', vectors, allow_pickle=False)
        atomic_text(folder / 'chunks.jsonl', ''.join(c.model_dump_json() + '\n' for c in chunks))
        manifest = {**signature, 'index_id': index_id, 'documents': len(documents), 'chunks': len(chunks),
                    'dimensions': int(vectors.shape[1]), 'vectors_sha256': digest((folder / 'vectors.npy').read_bytes()),
                    'chunks_sha256': digest((folder / 'chunks.jsonl').read_bytes())}
        write_json(folder / 'manifest.json', manifest)
        return manifest


class Retriever:
    def __init__(self, config: ExperimentConfig, models: Models):
        self.config, self.models = config, models
        identity = models.identity('embedding')
        signature = index_signature(config, identity)
        folder = ROOT / 'runtime/indexes' / digest(signature)[:20]
        if not (folder / 'manifest.json').exists():
            raise FileNotFoundError('Index missing or stale. Run groundwork ingest first.')
        self.manifest = json.loads((folder / 'manifest.json').read_text())
        for filename, key in [('vectors.npy', 'vectors_sha256'), ('chunks.jsonl', 'chunks_sha256')]:
            if digest((folder / filename).read_bytes()) != self.manifest[key]:
                raise ValueError('Index integrity failure; rebuild the index')
        self.chunks = [Chunk.model_validate(x) for x in read_jsonl(folder / 'chunks.jsonl')]
        self.vectors = np.load(folder / 'vectors.npy', allow_pickle=False)
        self.bm25 = BM25Okapi([tokenize(c.title + ' ' + c.text) for c in self.chunks])
        self.cache = EmbeddingCache(models, identity)

    def search(self, question: str):
        cfg = self.config
        dense = np.zeros(len(self.chunks))
        lexical = self.bm25.get_scores(tokenize(question))
        if cfg.retrieval != 'bm25':
            query = self.cache.embed([question], query=True)[0]
            if len(query) != self.vectors.shape[1]:
                raise ValueError('Embedding dimension changed; rebuild the index')
            dense = self.vectors @ query
        if cfg.retrieval == 'hybrid':
            scores = np.zeros(len(self.chunks))
            for values in (dense, lexical):
                for rank, i in enumerate(np.argsort(-values, kind='stable')[:cfg.candidate_k], 1):
                    # A zero lexical score provides no evidence of a keyword match.
                    if values is lexical and lexical[i] <= 0:
                        continue
                    scores[i] += 1 / (cfg.rrf_k + rank)
        else:
            scores = dense if cfg.retrieval == 'dense' else lexical
        hits, chars = [], 0
        for i in np.argsort(-scores, kind='stable'):
            chunk = self.chunks[int(i)]
            # Keep complete chunks so reported evidence equals model-visible evidence.
            if chars + len(chunk.text) > cfg.max_context_chars:
                continue
            hits.append({'chunk': chunk.model_dump(), 'score': float(scores[i]),
                         'dense_score': float(dense[i]), 'bm25_score': float(lexical[i])})
            chars += len(chunk.text)
            if len(hits) == cfg.top_k:
                break
        return hits
