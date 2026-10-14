# Measured benchmark comparison

Before: `20261014T084750Z-baseline-60bd55`
After: `20261014T085348Z-sufficient-8fcc8d`

These are actual local model executions. Null semantic scores were not measured.
Predictions contain only public benchmark questions and source excerpts (CC BY-SA 4.0).

## dev (15 questions)

| Metric | Before | After | Delta (pp) |
| --- | ---: | ---: | ---: |
| evidence_recall | 100.00 | 100.00 | 0.00 |
| all_evidence_found | 100.00 | 100.00 | 0.00 |
| answer_token_f1 | 33.01 | 0.00 | -33.01 |
| answer_exact_match | 16.67 | 0.00 | -16.67 |
| citation_validity | 100.00 | N/A | N/A |
| judge_correctness | N/A | N/A | N/A |
| citation_support | N/A | N/A | N/A |
| abstention_precision | 25.00 | 25.00 | 0.00 |
| abstention_recall | 33.33 | 100.00 | 66.67 |
| abstention_f1 | 28.57 | 40.00 | 11.43 |
| error_rate | 0.00 | 20.00 | 20.00 |
| answer_rate | 73.33 | 0.00 | -73.33 |
| unanswerable_answer_rate | 66.67 | 0.00 | -66.67 |
| answerable_abstention_rate | 25.00 | 75.00 | 50.00 |
| answered_token_f1 | 44.02 | N/A | N/A |
