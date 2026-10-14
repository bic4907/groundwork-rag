# Requirement map

This map links behavior to implementation and evidence. It is not a claim that every
possible input or provider has been validated.

| Requirement | Implementation | Verification / evidence |
| --- | --- | --- |
| Reproducible corpus, >=20 documents | dataset.py; data/corpus.jsonl; manifest.json | 310 documents; pinned upstream hash; test_data.py |
| Ingest pipeline | retrieval.ingest; CLI ingest | Stored content-addressed index |
| Chunking strategy and rationale | chunk_documents; ARCHITECTURE.ko.md | Sentence coverage and stable ID tests |
| Embedding and index | Models.embed; EmbeddingCache; NumPy exact index | Real local model vectors; index checksums |
| Query and generation API | POST /api/qa | Request/response schema; API tests; live calls |
| Evidence citations | Claim/Evidence/Citation schemas; validate_citations | Invalid ID and quote tests; live evidence trace |
| Explicit abstention | GeneratedAnswer invariant and prompt | No-answer Gold cases; failure-aware metrics |
| Environment-based secrets | Settings; .env.example; .gitignore | Local key file ignored; API never returns keys |
| Streaming | POST /api/qa/stream | Stage + token SSE; provisional draft, validated final answer, cancellation; test_streaming.py |
| Gold set >=20, summary and reasoning | data/gold.jsonl | 40 questions, 4 categories, grouped splits |
| Construction, bias and limitations | DATASETS.ko.md; data/NOTICE.md | Provenance attached per question |
| At least two quality metrics | evaluation.py | Evidence recall, full-evidence rate, token F1, abstention |
| Judge trust and alignment discussion | JUDGE_PROMPT; Human review; calibrate | Optional semantic judge; human labels pending until entered |
| One-command full evaluation | groundwork eval | Incremental predictions, summary.json, report.md |
| Seed/model/data/code provenance | run manifest | Actual model IDs/digests, hashes, config, Git state |
| Metric blind spots | EVALUATION.ko.md; Field notes UI | Lexical vs semantic, citation existence vs entailment |
| CI regression design | checks.yml; compare threshold flags | Offline CI; trusted nightly design documented |
| Improvement hypothesis | configs/hybrid.yaml | Dense vs Dense+BM25+RRF at fixed generation settings |
| Quantitative before/after | groundwork experiment; compare_runs | Actual saved runs and comparison report |
| Hypothesis/result/analysis/next steps | README; reports/ | Populate only from measured runs |
| Browser GUI | web/index.html, style.css, app.js | QA, evidence, corpus, experiments, comparison, human review |
| Detailed implementation and intent | ARCHITECTURE.ko.md | Per-component implementation, reason, tradeoff, limitation |
| Incremental commits | Git history | Foundation → corpus/retrieval → eval/GUI → validation/docs |

Run records under `runtime/` are private/ignored by default. Only explicitly selected
public-benchmark result files are published under `reports/`. Human review and live
user questions are never automatically published.
