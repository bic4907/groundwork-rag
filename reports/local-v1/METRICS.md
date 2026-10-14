# Measured benchmark comparison

Before: `20261014T080728Z-baseline-8d442d`
After: `20261014T081713Z-hybrid-de1756`

These are actual local model executions. Null semantic scores were not measured.
Predictions contain only public benchmark questions and source excerpts (CC BY-SA 4.0).

## all (40 questions)

| Metric | Before | After | Delta (pp) |
| --- | ---: | ---: | ---: |
| evidence_recall | 96.88 | 93.75 | -3.12 |
| all_evidence_found | 93.75 | 87.50 | -6.25 |
| answer_token_f1 | 39.56 | 45.23 | 5.66 |
| answer_exact_match | 25.00 | 28.12 | 3.12 |
| citation_validity | 100.00 | 100.00 | 0.00 |
| judge_correctness | N/A | N/A | N/A |
| citation_support | N/A | N/A | N/A |
| abstention_precision | 14.29 | 25.00 | 10.71 |
| abstention_recall | 12.50 | 12.50 | 0.00 |
| abstention_f1 | 13.33 | 16.67 | 3.33 |
| error_rate | 5.00 | 2.50 | -2.50 |
| answer_rate | 77.50 | 87.50 | 10.00 |

## dev (15 questions)

| Metric | Before | After | Delta (pp) |
| --- | ---: | ---: | ---: |
| evidence_recall | 100.00 | 95.83 | -4.17 |
| all_evidence_found | 100.00 | 91.67 | -8.33 |
| answer_token_f1 | 33.01 | 41.80 | 8.79 |
| answer_exact_match | 16.67 | 25.00 | 8.33 |
| citation_validity | 100.00 | 100.00 | 0.00 |
| judge_correctness | N/A | N/A | N/A |
| citation_support | N/A | N/A | N/A |
| abstention_precision | 25.00 | 0.00 | -25.00 |
| abstention_recall | 33.33 | 0.00 | -33.33 |
| abstention_f1 | 28.57 | 0.00 | -28.57 |
| error_rate | 0.00 | 0.00 | 0.00 |
| answer_rate | 73.33 | 93.33 | 20.00 |

## test (25 questions)

| Metric | Before | After | Delta (pp) |
| --- | ---: | ---: | ---: |
| evidence_recall | 95.00 | 92.50 | -2.50 |
| all_evidence_found | 90.00 | 85.00 | -5.00 |
| answer_token_f1 | 43.49 | 47.28 | 3.79 |
| answer_exact_match | 30.00 | 30.00 | 0.00 |
| citation_validity | 100.00 | 100.00 | 0.00 |
| judge_correctness | N/A | N/A | N/A |
| citation_support | N/A | N/A | N/A |
| abstention_precision | 0.00 | 33.33 | 33.33 |
| abstention_recall | 0.00 | 20.00 | 20.00 |
| abstention_f1 | 0.00 | 25.00 | 25.00 |
| error_rate | 8.00 | 4.00 | -4.00 |
| answer_rate | 80.00 | 84.00 | 4.00 |

