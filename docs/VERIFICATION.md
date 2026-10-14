# Verification record

## Published evaluation: Sonnet (before LangChain migration)

- The active benchmark is `reports/sonnet-v1/`: Dense, BM25, Hybrid and Dense with
  a sufficiency gate, each evaluated on all 40 questions (160 executions).
- Generation/gate model: OpenRouter `anthropic/claude-sonnet-5.5`. Embeddings: local
  Nomic, 310 documents, 332 chunks, 768 dimensions.
- Each report preserves actual responses, errors, returned model identifiers, usage,
  configuration, prompt/data/index hashes and source commit. Errors remain in metric
  denominators. Dev/test/all comparisons use the same Dense run.
- Prior runtime runs, comparisons, diagnostic traces and published benchmark reports
  were removed from the current workspace at the user's request. See the current
  METRICS and ANALYSIS files for measured results.
- All four configurations used the same clean evaluation implementation commit.
  The suite command/UI invokes the same evaluator and was verified separately.
- Dense and Sufficiency retrieved identical chunks, scores and ordering on all 40
  questions. See `reports/sonnet-v1/audit.json`.

- GUI verified the all-configuration button, default All split and completed Sonnet
  runs. Test comparison showed Dense 58.13% vs Sufficiency 47.67% Token F1, identical
  recall, and recorded model-call counts. Inspected console had no errors/warnings.
  Screenshots: `docs/images/sonnet-comparison.jpg`, `docs/images/sonnet-sufficiency.jpg`.
- A separately user-started Dense dev run was preserved and excluded from the four-run
  comparison. Its overlap with Hybrid means latency includes concurrent load.

## Implementation verification

- Previously completed offline suite: 39 tests covering corpus invariants, retrieval,
  citation validation, repair, abstention/error metrics, provider adapters, access
  boundaries, context sufficiency, SSE/NDJSON, Unicode previews, usage and cancellation.
- 42 offline tests passed after adding the suite command/API, including ordered execution,
  common-baseline comparison, overall progress, persisted partial failure and job routing.
  JavaScript syntax checks passed. Batch implementation commit: `888cd0f`.
- Live Sonnet streaming showed incomplete text under “생성 중 · 검증 전”, then a final
  answer. Citation clicks expanded sources. Stopping generation discarded the draft
  and enabled another question. Screenshot: `docs/images/token-streaming.jpg`.
- Browser corpus search, source sentence IDs, human-review evidence and local OpenAPI
  reference were inspected during implementation. No human labels were submitted.
- Fresh clone dependency installation and embedding ingestion previously reproduced
  the corpus, chunks, vectors and index hashes.
- Publication scan checks tracked environment files, credential-like patterns and
  restricted wording without printing matched secret values.

## LangChain migration verification

- 47 offline tests passed after migrating generation, sufficiency and judge model calls
  to official LangChain integrations. Contract tests cover unchanged messages, JSON mode,
  generation parameters, streaming callbacks, raw usage, bounded retries and Ollama options.
  Existing cancellation, truncated-stream, repair, metrics and sequential suite tests passed.
- Replayed retrieval for all 160 stored question/configuration pairs: chunk IDs, content,
  scores and ordering matched exactly. Corpus, Gold, configurations, retrieval implementation,
  index manifest and generation/sufficiency/judge prompt hashes were unchanged.
- Live OpenRouter Sonnet calls verified Dense synchronous answering and Sufficiency streaming,
  including the gate, citations and token usage. GUI Dense summary streaming showed an
  incomplete draft followed by “인용 검증됨”; inspected console had no errors/warnings.
  Screenshot: `docs/images/langchain-streaming.jpg`.
- New manifests record `execution.framework` and integration versions; comparisons expose
  before/after execution metadata. Historical reports remain unchanged and represent the
  previous direct HTTP implementation. No full paid answer-quality evaluation was rerun.

## Limits

- The 25-question test split has been inspected in development. It is a regression
  set, not new unseen evidence of generalization. Only one draw per configuration.
- Token F1 is lexical overlap, not semantic correctness. Citation validity checks IDs
  and source quotes, not entailment. No LLM Judge or human alignment was measured in
  the current Sonnet benchmark.
- Latency includes provider/network variability. Costs use configured per-token prices
  and returned usage; embeddings and requests without usage are excluded.
- Desktop was visually verified; mobile rendering and Docker execution are unverified.
- Existing Starlette TestClient httpx-adapter deprecation warning remains unsuppressed.
- Partial or failed suites retain completed runs and progress and are not labelled complete.
