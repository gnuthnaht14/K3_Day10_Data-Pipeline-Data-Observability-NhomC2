# Phase 1 Baseline Report

## Source summary

| Field | Value |
| --- | --- |
| source_api | Crossref REST API |
| source_query | agentic retrieval augmented generation large language model |
| source_filter | from-pub-date:2026-02-07,has-abstract:true |
| load_mode | loaded_snapshot |
| raw_records | 24 |
| clean_records | 24 |
| raw_response_path | D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\raw\crossref_response.json |
| raw_records_path | D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\raw\crossref_records.json |
| clean_csv_path | D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\clean\papers_clean.csv |
| clean_json_path | D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\clean\papers_clean.json |
| test_set_path | D:\workSpace\VinAI\K3_Day10_Data-Pipeline-Data-Observability-NhomC2\data\eval\test_set.json |
| test_set_sha256 | 5899992d6c85c56c3913fa9bc316bcef4d1ae409b350ce337ca484ead2e81ed5 |
| answerer | LangChain tool-calling agent with independent semantic retrieval trace |
| generated_at | 2026-08-06T04:26:21.041172+00:00 |

## Evaluation metrics

| Metric | Value |
| --- | --- |
| samples | 12 |
| retrieval_hit_rate | 1.0 |
| exact_lookup_hit_rate | 1.0 |
| mean_token_f1 | 0.21369674615848297 |
| judge_accuracy | 0.5 |
| mean_judge_score | 3 |
| judge_provenance | {"fallback_samples": 0, "model": "gpt-4o-mini", "modes": {"deterministic_authors": 3, "deterministic_categories": 3, "deterministic_date": 3, "llm_judge": 3}, "provider": "openai"} |
| answerer_provenance | {"fallback_samples": 0, "modes": {"langchain_tool_agent": 12}} |
| ragas | {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."} |

## Data quality

- Status: **pass**
- Rows: **24**
- Checks: **10/10 passed**

| Check | Value | Threshold | Passed |
| --- | --- | --- | --- |
| row_count | 24 | {"min": 1} | PASS |
| required_schema | [] | {"required_columns": ["paper_id", "title", "summary", "published", "authors_joined", "categories_joined", "age_days", "text_for_embedding", "abs_url", "pdf_url"]} | PASS |
| paper_id_not_null | 0 | 0 | PASS |
| paper_id_unique | 0 | 0 | PASS |
| duplicate_rows | 0 | 0 | PASS |
| title_not_empty | 0 | 0 | PASS |
| summary_min_length | 0 | {"max_rows_below_threshold": 0, "min_chars": 20} | PASS |
| text_for_embedding_not_empty | 0 | 0 | PASS |
| age_days_valid | 0 | 0 | PASS |
| stale_rows | 0 | {"max_age_days": 180, "max_rows": 0} | PASS |

## Freshness

| Field | Value |
| --- | --- |
| Status | fresh |
| Is fresh | PASS |
| Latest published | 2026-08-01 |
| Oldest published | 2026-02-12 |
| Stale rows | 0 |
| Invalid published rows | 0 |
| Total rows | 24 |
| Threshold (days) | 180 |

## Metric interpretation

- `retrieval_hit_rate` measures whether semantic retrieval places a ground-truth document in the top-k results. It evaluates the retriever/index, not the correctness of the final generated answer.
- `exact_lookup_hit_rate` is reported separately and is never used to calculate semantic retrieval hit rate.
- Token F1 can be below 1.0 even when retrieval finds the correct document because an answer may summarize, paraphrase, or use only part of the reference answer. Token F1 measures lexical overlap rather than semantic equivalence.
- Answerer provenance: `{"fallback_samples": 0, "modes": {"langchain_tool_agent": 12}}`.
- Judge provenance: `{"fallback_samples": 0, "model": "gpt-4o-mini", "modes": {"deterministic_authors": 3, "deterministic_categories": 3, "deterministic_date": 3, "llm_judge": 3}, "provider": "openai"}`.
- Ragas status: `{"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}`.
