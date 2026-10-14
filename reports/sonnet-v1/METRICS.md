# Sonnet benchmark: four RAG configurations

Model: `anthropic/claude-sonnet-5.5` through OpenRouter. 40 questions per configuration; 160 executions.

Embedding: local Nomic. Each configuration uses top-k 6 and the same generation prompt.
No LLM Judge or human labels were collected. Token F1 measures lexical overlap; citation validity checks IDs and quotes.

Cost is the estimate from configured $2/M input and $10/M output tokens, including returned repair/gate calls. Embeddings and requests without usage are excluded.

## test: 25 questions (20 answerable)

| Configuration | Evidence recall % | Answer F1 % | Answer rate % | Abstention F1 % | Error % | p50 s | p95 s | Est. USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 95.00 | 58.13 | 80.00 | 100.00 | 0.00 | 2.82 | 5.22 | 0.1599 |
| BM25 | 78.33 | 37.20 | 56.00 | 62.50 | 0.00 | 3.03 | 5.19 | 0.1611 |
| Hybrid (RRF) | 92.50 | 41.08 | 72.00 | 83.33 | 0.00 | 2.86 | 5.51 | 0.1649 |
| Dense + Sufficiency | 95.00 | 47.67 | 72.00 | 83.33 | 0.00 | 5.09 | 6.08 | 0.2667 |

Answer F1 is averaged over answerable questions (abstentions/errors score zero). Answer/error rates use all questions.

## dev: 15 questions (12 answerable)

| Configuration | Evidence recall % | Answer F1 % | Answer rate % | Abstention F1 % | Error % | p50 s | p95 s | Est. USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 100.00 | 57.28 | 66.67 | 85.71 | 6.67 | 2.77 | 8.56 | 0.1065 |
| BM25 | 86.11 | 50.24 | 60.00 | 85.71 | 13.33 | 3.27 | 12.66 | 0.1267 |
| Hybrid (RRF) | 95.83 | 58.53 | 66.67 | 75.00 | 0.00 | 2.73 | 7.86 | 0.1097 |
| Dense + Sufficiency | 100.00 | 54.97 | 66.67 | 75.00 | 0.00 | 4.69 | 6.25 | 0.1525 |

Answer F1 is averaged over answerable questions (abstentions/errors score zero). Answer/error rates use all questions.

## all: 40 questions (32 answerable)

| Configuration | Evidence recall % | Answer F1 % | Answer rate % | Abstention F1 % | Error % | p50 s | p95 s | Est. USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 96.88 | 57.81 | 75.00 | 94.12 | 2.50 | 2.79 | 5.80 | 0.2663 |
| BM25 | 81.25 | 42.09 | 57.50 | 69.57 | 5.00 | 3.12 | 7.42 | 0.2878 |
| Hybrid (RRF) | 93.75 | 47.62 | 70.00 | 80.00 | 0.00 | 2.84 | 5.95 | 0.2746 |
| Dense + Sufficiency | 96.88 | 50.41 | 70.00 | 80.00 | 0.00 | 5.02 | 6.24 | 0.4193 |

Answer F1 is averaged over answerable questions (abstentions/errors score zero). Answer/error rates use all questions.

## Runs

- Dense: `20261014T092943Z-baseline-871232`
- BM25: `20261014T093509Z-bm25-334d2e`
- Hybrid (RRF): `20261014T093740Z-hybrid-26d608`
- Dense + Sufficiency: `20261014T093156Z-sufficient-3f68bf`

Comparison JSON files contain paired cluster-bootstrap intervals, per-question deltas, model-call counts and changed settings.
The test split was inspected in earlier development; it is a regression set, not a new unseen holdout.
Single draw per configuration; no statistical significance or semantic correctness improvement is claimed.
Predictions contain public benchmark questions and source excerpts under CC BY-SA 4.0.
