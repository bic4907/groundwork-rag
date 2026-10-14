# Verification record

## Executed

- Local offline suite: 20 meaningful tests passed. Covers dataset invariants, grouped
  splits, withheld evidence, complete sentence coverage, stable chunk IDs, retrieval
  fusion, context budgets, invalid citations, repair limits, abstention/error metric
  denominators, API contracts, access boundaries, provider request/usage mapping,
  and credential-safe provider errors.
- JavaScript syntax checks: app.js and api-docs.js passed.
- GitHub Actions: the pushed implementation passed its offline checks. Latest commit
  status must be checked in the repository Actions tab.
- Real embedding ingestion: Nomic embeddings, 310 documents, 332 chunks, 768 dimensions.
- Real generation: local Llama 3 answered a public benchmark question through the
  CLI and browser SSE path. Citation click expanded the exact source document.
- Browser: source cards, corpus search and sentence IDs, human review with original
  gold evidence, and CDN-free OpenAPI reference were visibly inspected.
- Browser comparison: completed all-question runs selected automatically, 25 paired test
  questions rendered with matching real metrics, deltas, intervals and bars. Screenshot
  saved in `docs/images/experiment-comparison.jpg`.
- Browser console: no errors or warnings in the inspected question/review/comparison flows.
- Judge integration: two repeated judgments on one development example returned
  the same correctness and claim-support labels. This checks one integration path;
  it is not broad judge consistency evidence or human alignment.
- Publication scan: tracked environment files, credential-like patterns and restricted
  wording checked without printing any matching secret values.

## Limits

- The browser reported an actual 1280-pixel layout even after requesting a mobile
  viewport override. Desktop layout was inspected; mobile rendering is not claimed
  as visually verified. Responsive CSS is present.
- Hosted provider requests were verified with mock transports, not with a live paid
  credential. The local providers were exercised with real models.
- No human review labels were fabricated or submitted by the agent. Human alignment
  remains pending until a person performs the review.
- The Dockerfile has not been built or run. The supported verified setup uses uv.
- One dependency deprecation warning: Starlette's current TestClient warns about its
  httpx adapter. Tests still pass; this is recorded rather than suppressed.
- Local model runtimes were shared with interactive preview and another development
  evaluation. Latency values are observational, not controlled deployment benchmarks.

## Completed experiment and reproduction

- Full baseline run: `20261014T080728Z-baseline-8d442d`, 40/40 processed.
- Full hybrid run: `20261014T081713Z-hybrid-de1756`, 40/40 processed.
- Both runs contain actual local model outputs, including 2 and 1 failed responses,
  respectively. Failed responses remain in the appropriate denominators.
- Paired test comparison: 25 questions; report and full traces exported to
  `reports/local-v1/`. See ANALYSIS.ko.md for negative findings and uncertainty.
- Fresh clone of the public repository: `uv sync --frozen` and real embedding ingest
  succeeded in a new temporary directory with an empty embedding cache. Corpus,
  chunk, vector and index hashes matched the original run exactly.
- Existing GUI development evaluation also completed all 15 questions before the
  original server was restarted with the updated API contract.

Partial runs are never presented as completed experiments.
