# Corruption and Repair Comparison Report

## Evaluation metrics

| Metric | Baseline | Corrupted | Repaired | Corruption delta | Recovery delta | Recovery ratio | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| samples | 12 | 12 | 12 | 0 | 0 | N/A | sample-count signal |
| retrieval_hit_rate | 1.0 | 0.6666666666666666 | 1.0 | -0.33333333333333337 | 0.33333333333333337 | 1.0 | recovered |
| exact_lookup_hit_rate | 1.0 | 0.6666666666666666 | 1.0 | -0.33333333333333337 | 0.33333333333333337 | 1.0 | recovered |
| mean_token_f1 | 0.21369674615848297 | 0.16319467676454766 | 0.21452908193582848 | -0.05050206939393531 | 0.05133440517128082 | 1.0164812212120058 | recovered |
| judge_accuracy | 0.5 | 0.25 | 0.5 | -0.25 | 0.25 | 1.0 | recovered |
| mean_judge_score | 3 | 2.1666666666666665 | 3 | -0.8333333333333335 | 0.8333333333333335 | 1.0 | recovered |
| judge_provenance | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| answerer_provenance | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| ragas | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

Recovery ratio = (repaired - corrupted) / (baseline - corrupted).

## Evaluation provenance

| Component | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Answerer | {"fallback_samples": 0, "modes": {"langchain_tool_agent": 12}} | {"fallback_samples": 0, "modes": {"langchain_tool_agent": 12}} | {"fallback_samples": 0, "modes": {"langchain_tool_agent": 12}} |
| Judge | {"fallback_samples": 0, "model": "gpt-4o-mini", "modes": {"deterministic_authors": 3, "deterministic_categories": 3, "deterministic_date": 3, "llm_judge": 3}, "provider": "openai"} | {"fallback_samples": 0, "model": "gpt-4o-mini", "modes": {"deterministic_authors": 3, "deterministic_categories": 3, "deterministic_date": 3, "llm_judge": 3}, "provider": "openai"} | {"fallback_samples": 0, "model": "gpt-4o-mini", "modes": {"deterministic_authors": 3, "deterministic_categories": 3, "deterministic_date": 3, "llm_judge": 3}, "provider": "openai"} |
| Ragas | {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."} | {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."} | {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."} |

## Data quality comparison

| Signal | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Status | pass | fail | pass |
| Passed | PASS | FAIL | PASS |
| Total rows | 24 | 24 | 24 |
| Failed checks | [] | ["paper_id_unique", "duplicate_rows", "summary_min_length", "stale_rows"] | [] |

## Freshness comparison

| Signal | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Status | fresh | stale | fresh |
| Is fresh | PASS | FAIL | PASS |
| Stale rows | 0 | 1 | 0 |
| Invalid published rows | 0 | 0 | 0 |
| Total rows | 24 | 24 | 24 |

## Per-scenario impact (ablation)

Ablation deltas use the same deterministic answerer for their own baseline and every isolated scenario; they are not compared with the main LLM-agent Token F1.

| Scenario | Affected eval IDs | Retrieval hit | Retrieval delta | Token F1 | Token F1 delta |
| --- | --- | --- | --- | --- | --- |
| drop_eval_record | ["10.1111/exsy.70341"] | 0.6666666666666666 | -0.33333333333333337 | 0.6284187076826516 | -0.19474233843434952 |
| blank_summary | ["10.1007/s10278-026-02086-9"] | 1.0 | 0.0 | 0.7967821492345072 | -0.026378896882493952 |
| inject_embedding_noise | ["10.1093/sleep/zsag091.0346"] | 1.0 | 0.0 | 0.8097861417181164 | -0.01337490439888478 |
| make_published_date_stale | ["10.1007/s10278-026-02086-9"] | 1.0 | 0.0 | 0.7398277127836679 | -0.08333333333333326 |
| add_duplicate_rows | ["10.1093/sleep/zsag091.0346"] | 1.0 | 0.0 | 0.8231610461170011 | 0.0 |

## Checkpoint interpretation

- Most severe retrieval scenario: `drop_eval_record` with retrieval delta `-0.33333333333333337`, measured independently by ablation.
- Frozen-test overlap IDs: `["10.1007/s10278-026-02086-9", "10.1093/sleep/zsag091.0346", "10.1111/exsy.70341"]`.
- Repair source: `D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\raw\crossref_records.json`. Repair rebuilds clean data from the saved raw snapshot instead of fetching Crossref again because the API result and metadata may change over time; the snapshot keeps the experiment reproducible and isolates the effect of corruption.
