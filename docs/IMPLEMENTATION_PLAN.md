# Implementation plan

1. Establish an isolated repository, credential boundaries, and pinned dependencies.
2. Build a reproducible public corpus and a versioned, source-grounded gold set.
3. Implement ingestion, persistent embeddings, dense/BM25/hybrid retrieval,
   structured generation, citation checks, and explicit abstention.
4. Build automated evaluation, semantic judge support, human calibration,
   paired experiments, provenance manifests, and regression gates.
5. Build an accessible browser workbench for questions, evidence, corpus inspection,
   experiment execution, comparisons, and human review.
6. Run meaningful unit/integration/browser checks and measured experiments.
7. Document the implementation and intent in Korean, including honest limitations.

Experiments must never expose gold answers to the answering pipeline. Failed requests
remain visible in the evaluation denominator. Test split results are reporting data,
not tuning feedback. No synthetic or mocked results may be presented as measured
model quality. Human alignment is not claimed until actual human labels exist.
