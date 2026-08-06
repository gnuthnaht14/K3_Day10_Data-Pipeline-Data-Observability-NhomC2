# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
|---|---|
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm C2 |
| Repository | https://github.com/gnuthnaht14/K3_Day10_Data-Pipeline-Data-Observability-NhomC2.git |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
|---:|---|---|---|---|
| 1 | Lường Thị Hảo | 2A202601637 | Source Ingestion Owner | `src/ingestion/crossref.py`; Raw Schema/PaperRecord |
| 2 | Lê Thị Linh | 2A202601441 | Data Model & Eval Set Owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`; Clean Schema/Evaluation Set |
| 3 | Mai Hồng Sơn | 2A202601921 | Data Observability Owner | `src/observability/quality.py`, `src/observability/reporting.py`; quality/freshness reports |
| 4 | Nhữ Trọng Thành | 2A202601977 | Corruption & Integration Owner | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`; integration/dashboard |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thiện pipeline từ Crossref raw snapshot đến cleaning, ChromaDB indexing, frozen evaluation set, RAG evaluation và data observability. Baseline tạo được raw response/records, clean CSV/JSON, embedding manifest, test set, answers, metrics, quality/freshness reports và `phase1_report.md`. Baseline có 24 bản ghi, quality PASS 10/10, freshness Fresh, retrieval hit rate 1.0, mean Token F1 0.214 và judge accuracy 0.50. Nhóm áp dụng controlled corruption gồm xóa tài liệu evaluation, blank summary, chèn embedding noise, stale date và duplicate rows; các scenario đều overlap frozen test set và được ghi trong `corruption_log.json`. Corrupted quality FAIL ở 4 check, freshness chuyển sang stale, retrieval hit giảm còn 0.667, Token F1 còn 0.163 và judge accuracy còn 0.25. Repair không sửa trực tiếp dữ liệu lỗi mà rebuild từ `data/raw/crossref_records.json`, chạy lại cleaning, re-index và đánh giá bằng cùng test set. Repaired quality/freshness trở lại PASS/Fresh, retrieval phục hồi 1.0 và các metric answer trở về gần baseline. Giới hạn chính là Ragas chưa chạy và số lượng evaluation sample còn nhỏ.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref API/raw snapshot
    -> raw response/raw records
    -> cleaning và Clean Schema
    -> embedding + ChromaDB index
    -> frozen test set + agent evaluation
    -> quality/freshness + baseline report
    -> controlled corruption + corrupted CSV
    -> corrupted re-index và re-evaluate
    -> repair từ raw snapshot
    -> repaired re-index và comparison report
```

| Khối | Input | Xử lý chính | Output/artifact | Owner |
|---|---|---|---|---|
| Ingestion | Crossref API hoặc raw snapshot | Retry/backoff, parse `PaperRecord`, deduplicate DOI | `data/raw/crossref_response.json`, `crossref_records.json` | Lường Thị Hảo |
| Cleaning | Raw `PaperRecord` list | Chuẩn hóa trường, tạo joined fields, `age_days`, `text_for_embedding` | `data/clean/papers_clean.csv/json` | Lê Thị Linh |
| Embedding/index | Clean dataframe | MiniLM embeddings, ChromaDB cosine search, top-k=4 | `data/embeddings/`, `data/chroma/` | Nhữ Trọng Thành |
| Evaluation | Index + frozen test set | Agent answer, semantic retrieval trace, Token F1, judge | `data/results/*answers.json`, `*metrics.json` | Lê Thị Linh/Nhữ Trọng Thành |
| Observability | Clean/corrupted/repaired dataframe | Completeness, uniqueness, validity, freshness | `data/quality/*.json` | Mai Hồng Sơn |
| Corruption/repair | Clean CSV + raw snapshot | Controlled corruption, raw-based repair, comparison | `papers_corrupted.csv`, log, reports | Nhữ Trọng Thành |
| Orchestration | Settings và các artifact | Điều phối C3/C4 theo đúng thứ tự | `phase1_report.md`, `corruption_report.md` | Nhữ Trọng Thành |

## 4. Cách tái hiện kết quả

### Cấu hình

| Biến/cấu hình | Giá trị sử dụng |
|---|---|
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Corruption seed | 42 |
| Ragas | Chưa chạy; `RUN_RAGAS=1` để bật |

API key chỉ nằm trong `.env` local và không được đưa vào report/Git.

### Lệnh chạy

```bash
uv sync
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run streamlit run streamlit_app.py
```

### Kết quả tái hiện gần nhất

| Lệnh | Trạng thái | Thời điểm gần nhất | Bằng chứng |
|---|---|---|---|
| Baseline pipeline | Thành công | 2026-08-06 | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow | Thành công | 2026-08-06 | `data/results/corruption_log.json`, `data/reports/corruption_report.md` |
| Test suite | Thành công, 9 tests passed | 2026-08-06 | `uv run pytest -q` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
|---|---|
| Source | Crossref REST API |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `has-abstract:true` và from-pub-date theo freshness window 180 ngày |
| Số record nhận được | 24 |
| Retry/backoff | Retry lỗi `429` và `5xx` với exponential backoff |
| Chế độ lần chạy gần nhất | `loaded_snapshot` |

### Raw và clean schema

| Trường | Kiểu | Bắt buộc | Ý nghĩa/xử lý |
|---|---|---|---|
| `paper_id` | string | Có | DOI, chuẩn hóa lowercase, unique |
| `title` | string | Có | Tiêu đề; record thiếu title bị loại |
| `summary` | string | Không | Abstract; để rỗng nếu nguồn thiếu, quality sẽ cảnh báo |
| `published` | ISO date string | Không | Ngày xuất bản dùng cho freshness |
| `authors_joined` | string | Không | Danh sách authors đã nối |
| `categories_joined` | string | Không | Subject metadata đã nối; có thể rỗng nếu Crossref thiếu |
| `age_days` | integer | Có ở Clean Schema | Số ngày từ published đến thời điểm chạy |
| `text_for_embedding` | string | Có | Title, summary và metadata dùng để index |
| `abs_url` | string | Không | Link abstract/landing page |
| `pdf_url` | string | Không | Link PDF nếu Crossref cung cấp |

### Quy tắc cleaning

| Quy tắc | Dimension | Record baseline bị tác động | Xác minh |
|---|---|---:|---|
| Loại record thiếu DOI/title | Completeness/Validity | 0 sau parse | Raw records + clean validation |
| Deduplicate bằng `paper_id` | Uniqueness | 0 baseline | `paper_id_unique` |
| Chuẩn hóa HTML/JATS và whitespace | Validity | Các summary có markup | `cleaning.py` |
| Tính `age_days` và rebuild embedding text | Freshness/Index validity | 24 | Clean CSV + quality report |

`text_for_embedding` được dựng từ title, summary, authors, categories và published. Semantic retrieval metric dùng kết quả `index.search()`; exact title lookup được ghi riêng và không được dùng để bảo đảm retrieval hit.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
|---|---|
| Số câu hỏi | 12 |
| `question_type` | `summary`, `authors`, `date`, `categories` |
| Ground-truth IDs | Lấy từ Clean Schema, lưu trong `ground_truth_doc_ids` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB, cosine distance; baseline/corrupted/repaired collections |
| Retrieval `top_k` | 4 |
| LLM provider/model | OpenAI / `gpt-4o-mini` |
| Test set dùng chung | `data/eval/test_set.json`; hash `5899992d6c85c56c3913fa9bc316bcef4d1ae409b350ce337ca484ead2e81ed5` |

Test set được giữ nguyên để ba trạng thái có cùng câu hỏi, ground truth và document IDs. Mọi thay đổi metric do dữ liệu/index/answerer, không phải do đổi bộ đề.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn | Trạng thái |
|---|---|---|
| Raw response/records | `data/raw/` | Có |
| Cleaned dataset | `data/clean/papers_clean.csv/json` | Có |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có |
| Evaluation set | `data/eval/test_set.json` | Có |
| Baseline metrics/answers | `data/results/baseline_metrics.json`, `baseline_answers.json` | Có |
| Quality/freshness | `data/quality/` | Có |
| Baseline report | `data/reports/phase1_report.md` | Có |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
|---|---:|---|
| `retrieval_hit_rate` | 1.000 | 100% câu hỏi có ground-truth document trong semantic top-k |
| `mean_token_f1` | 0.214 | Answer có overlap từ vựng thấp hơn ground truth đầy đủ |
| `judge_accuracy` | 0.500 | 6/12 câu được judge xác nhận đúng |
| `mean_judge_score` | 3.000 | Điểm trung bình trên thang 1–5 |
| Ragas | N/A | Chưa bật `RUN_RAGAS=1` |

## 8. Data quality và freshness

Baseline quality có 10/10 checks PASS với 24 rows. Các check gồm row count, required schema, paper ID, duplicate rows, title, summary, embedding text, age và stale rows.

Baseline freshness:

| Thuộc tính | Giá trị |
|---|---|
| Latest published | 2026-08-01 |
| Oldest published | 2026-02-12 |
| Threshold | 180 ngày |
| Stale rows | 0 |
| Invalid published rows | 0 |
| Trạng thái | Fresh |

## 9. Corruption scenarios và repair

| Corruption | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế |
|---|---:|---|---|
| `drop_eval_record` | 1 | Giảm row count/retrieval | Xóa `10.1111/exsy.70341`; retrieval delta `-0.333` trong ablation |
| `blank_summary` | 1 | `summary_min_length` FAIL | Tác động `10.1007/s10278-026-02086-9` |
| `inject_embedding_noise` | 1 | Embedding content bị nhiễu | Tác động `10.1093/sleep/zsag091.0346` |
| `make_published_date_stale` | 1 | `stale_rows` và freshness FAIL | Đổi ngày thành `2000-01-01` |
| `add_duplicate_rows` | 1 | `paper_id_unique`, `duplicate_rows` FAIL | Giữ nguyên ID của tài liệu evaluation |

Corruption log `data/results/corruption_log.json` ghi seed 42, scenario, record IDs, affected evaluation IDs, parameters và overlap status.

Repair đọc `data/raw/crossref_records.json`, chạy lại `build_clean_dataframe`, validate, ghi repaired dataset, rebuild index và evaluate trên `data/eval/test_set.json`. Cách này phục hồi từ nguồn đầu vào đáng tin cậy thay vì che lỗi trong corrupted file.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Nhận xét |
|---|---:|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.000 | 0.667 | 1.000 | -0.333 | Ground-truth document bị mất khỏi index |
| `mean_token_f1` | 0.214 | 0.163 | 0.215 | -0.051 | Context/answer bị thiếu hoặc nhiễu |
| `judge_accuracy` | 0.500 | 0.250 | 0.500 | -0.250 | Chất lượng answer giảm |
| `mean_judge_score` | 3.000 | 2.167 | 3.000 | -0.833 | Judge score phục hồi về baseline |
| Quality | PASS | FAIL | PASS | 4 checks fail | Duplicate, summary và stale |
| Freshness | Fresh | Stale | Fresh | 1 stale row | Repair xóa dữ liệu stale |

Hai chuỗi quan hệ nhân quả:

1. Xóa ground-truth document → semantic retrieval miss → retrieval hit giảm 1.000 xuống 0.667 và Token F1 giảm.
2. Rebuild từ raw snapshot → Clean Schema/quality/freshness phục hồi → repaired retrieval hit trở lại 1.000.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Judge từng chấm đúng cho answer rỗng và exact title lookup làm retrieval metric bị lẫn với semantic retrieval.
- **Nguyên nhân:** LLM judge chưa có empty-answer guard; answerer đưa exact lookup document vào danh sách dùng để tính retrieval.
- **Cách xử lý:** Tách semantic retrieval trace khỏi exact lookup, thêm deterministic judge cho structured fields, empty-answer guard và provenance.
- **Cách xác minh:** `uv run pytest -q` cho 9 tests; baseline/corruption reports ghi `answerer_provenance` và `judge_provenance`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện |
|---|---|---|
| Ragas chưa chạy | Chưa có context precision/recall và faithfulness | Chạy với `RUN_RAGAS=1` khi có thời gian/API budget |
| Evaluation chỉ có 12 câu | Metric nhạy với một vài câu hỏi | Mở rộng frozen test set và thêm câu hỏi theo field |
| Summary judge dùng LLM | Có thể dao động giữa lần chạy | Cache verdict, pin model snapshot và lặp judge/majority vote |
| Crossref categories có thể thiếu | Category evaluation có ground truth “không được liệt kê” | Theo dõi source completeness và thêm fallback metadata source |
| Chưa có scheduler/alerting production | Chưa tự động giám sát theo thời gian | Thêm orchestration, alert và lưu metric history |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp module, artifact và kết quả thực tế.
- [x] Baseline và corruption flow đã chạy thành công.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp `data/quality/`.
- [x] Có `phase1_report.md`, `corruption_report.md` và Streamlit dashboard.
- [x] Có automated tests, kết quả gần nhất 9 passed.
- [x] Không đưa `.env`, API key hoặc secret vào report.
