# Member Role Report — Nhữ Trọng Thành

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nhữ Trọng Thành |
| MSSV | 2A202601977 |
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm C2 |
| Vai trò chính | Corruption & Integration Owner |
| Repository | https://github.com/gnuthnaht14/K3_Day10_Data-Pipeline-Data-Observability-NhomC2.git |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Baseline orchestration | `src/pipelines/phase1.py` | Raw records, settings, clean rules | Clean data, index, test set, baseline metrics/report | Hoàn thành |
| Controlled corruption | `src/ingestion/corruption.py` | Clean dataframe, frozen eval IDs | `data/clean/papers_corrupted.csv`, `corruption_log.json` | Hoàn thành |
| Corruption/repair integration | `src/pipelines/corruption_flow.py` | Clean artifact, raw snapshot, frozen test set | Corrupted/repaired metrics, quality và comparison report | Hoàn thành |
| RAG evaluation integration | `src/evaluation/metrics.py`, `src/retrieval/qa.py`, `src/retrieval/agent.py` | Index + evaluation set | Semantic retrieval trace, agent answers, judge provenance | Hoàn thành |
| Demo dashboard | `streamlit_app.py` | Existing data artifacts | Interactive Baseline/Corrupted/Repaired dashboard | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Tích hợp quality/freshness vào pipeline | Mai Hồng Sơn — `quality.py`, `reporting.py` | Report có đủ Baseline/Corrupted/Repaired |
| Kiểm tra data contract | Lường Thị Hảo, Lê Thị Linh | Raw/Clean/Evaluation artifacts được nối đúng contract |
| Bổ sung automated tests | Toàn nhóm | 9 tests pass, không cần network cho unit tests |

## 3. Kết quả theo vai trò

| Nhiệm vụ | File/hàm/artifact | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Nối raw snapshot → cleaning → index → evaluation | `phase1.py` | Baseline 24 records, 12 evaluation questions | `uv run python script/run_phase1.py` |
| Tạo corruption deterministic | `corruption.py` | 5 scenario, seed 42, overlap cả 3 frozen documents | `data/results/corruption_log.json` |
| Tạo corrupted artifact | `corruption_flow.py`, `config.py` | `data/clean/papers_corrupted.csv` được lưu và đọc lại trước khi index | `uv run python script/run_corruption_flow.py` |
| Repair từ raw snapshot | `repair_from_raw_snapshot()` | Repaired clean data 24 unique records | Repaired quality/freshness artifacts |
| Tách semantic retrieval khỏi exact lookup | `qa.py`, `metrics.py` | Retrieval metric không dùng title lookup oracle | `tests/test_evaluation.py` |
| Ổn định judge | `metrics.py` | Empty guard, deterministic fields, provider/mode provenance | `data/results/*metrics.json` |
| Tạo comparison report/dashboard | `reporting.py`, `streamlit_app.py` | Demo trực quan Baseline → Corrupted → Repaired | `corruption_report.md`, Streamlit AppTest |

Output cụ thể: corruption làm retrieval hit giảm từ `1.000` xuống `0.667`, quality chuyển PASS thành FAIL và freshness chuyển Fresh thành Stale; repair phục hồi retrieval về `1.000`, quality PASS và freshness Fresh.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Các module ingestion, cleaning, evaluation và observability phải chạy như một pipeline có data contract rõ ràng. Pha C4 cần chứng minh lỗi dữ liệu thật sự làm RAG giảm chất lượng và repair phải tái lập được từ raw snapshot.

### Cách triển khai

- `phase1.py` đọc raw snapshot nếu có, chạy cleaning, build ChromaDB, giữ frozen test set và xuất baseline artifacts.
- `corruption.py` áp dụng các scenario deterministic với seed 42, chọn trực tiếp document IDs từ frozen test set và ghi log chi tiết.
- `corruption_flow.py` lưu corrupted CSV rồi đọc lại bằng `keep_default_na=False`, build corrupted index, chạy ablation retrieval/F1, sau đó rebuild repaired data từ raw records.
- `qa.py` giữ semantic search results độc lập với exact lookup. Exact lookup chỉ hỗ trợ trả lời câu hỏi title-addressed, không được dùng để tính semantic retrieval hit.
- `metrics.py` dùng deterministic judge cho date/authors/categories, empty-answer guard và lưu judge/answerer provenance.
- `reporting.py` xuất bảng ba trạng thái cho metrics, quality, freshness và scenario ablation.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | `data/raw/crossref_records.json`, `data/clean/papers_clean.json`, `data/eval/test_set.json` |
| Output | Clean/corrupted/repaired CSV/JSON, ChromaDB collections, metrics, quality và reports |
| Module phụ thuộc | `crossref.py`, `cleaning.py`, `testset.py`, `quality.py`, `reporting.py`, `index.py` |
| Module sử dụng output | Evaluation, corruption flow, Streamlit dashboard |
| Điều kiện lỗi | Missing raw artifact, invalid schema, duplicate IDs, stale/invalid dates, missing evaluation IDs |

### Cách xác minh

```bash
uv run pytest -q
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run streamlit run streamlit_app.py
```

- **Kết quả mong đợi:** Baseline PASS, corrupted FAIL/degrade, repaired PASS/recover.
- **Kết quả thực tế:** 9 tests passed; retrieval `1.000 → 0.667 → 1.000`; quality `PASS → FAIL → PASS`; freshness `Fresh → Stale → Fresh`.
- **Artifact/log:** `data/results/`, `data/quality/`, `data/reports/`, không chứa secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Exact title lookup có thể đưa ground-truth document vào kết quả và làm retrieval hit bị đánh giá quá cao.
- **Phương án 1:** Bỏ hoàn toàn exact lookup khỏi answerer.
- **Phương án 2:** Giữ exact lookup để hỗ trợ answer nhưng tách semantic search trace dùng cho metric.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Giữ được khả năng trả lời các câu hỏi title-addressed, đồng thời retrieval metric vẫn phản ánh ChromaDB semantic search. Exact lookup được lưu thành metric riêng.
- **Bằng chứng:** Baseline metrics lưu cả `retrieval_hit_rate` và `exact_lookup_hit_rate`; test kiểm tra semantic IDs không bị thay thế bởi exact ID.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** LLM judge từng chấm `correct=true`, `score=5` cho answer rỗng; corruption report có metric judge dao động giữa các lần chạy.
- **Nguyên nhân gốc:** Prompt judge không có empty-answer guard; LLM judge không bảo đảm deterministic tuyệt đối; evaluation trước đó trộn exact lookup với semantic retrieval.
- **Cách xử lý:** Thêm empty-answer guard, deterministic judge cho fields có cấu trúc, structured prompt, provider/mode provenance và semantic retrieval trace độc lập.
- **Cách xác minh:** `tests/test_evaluation.py`, `data/results/*metrics.json`; corrupted answer rỗng không còn được chấm đúng.
- **Điều học được:** Cần kiểm soát cả evaluator và provenance; data metric không thể chỉ dựa vào một LLM judge không có trace.

## 7. Hiểu biết về luồng end-to-end

1. **Crossref đến vector index:** Crossref/raw snapshot được parse thành `PaperRecord`, cleaning tạo Clean Schema và `text_for_embedding`, sau đó MiniLM tạo embeddings để lưu trong ChromaDB.
2. **Evaluation set:** Mỗi câu hỏi có `ground_truth` và `ground_truth_doc_ids`; retrieval hit kiểm tra ground-truth ID có nằm trong semantic top-k hay không, còn Token F1/judge đánh giá answer.
3. **Quality khác freshness:** Quality kiểm tra schema, completeness, uniqueness, validity và duplicate; freshness tập trung vào tuổi và khả năng parse của published date.
4. **Dùng cùng test set:** Để mọi thay đổi metric đến từ dữ liệu/index/repair, không phải do đổi câu hỏi hoặc ground truth.
5. **Repair thành công:** Dựa trên repaired quality PASS, freshness Fresh, retrieval phục hồi 1.0 và metrics answer trở về gần baseline.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.000 | 0.667 | 1.000 | Mất một ground-truth document làm retrieval giảm 33.3 điểm % |
| `mean_token_f1` | 0.214 | 0.163 | 0.215 | Context thiếu/nhiễu làm lexical overlap giảm |
| `judge_accuracy` | 0.500 | 0.250 | 0.500 | Answer quality giảm rồi phục hồi |
| `mean_judge_score` | 3.000 | 2.167 | 3.000 | Repair phục hồi score về baseline |
| Quality checks | PASS 10/10 | FAIL 4 checks | PASS 10/10 | Duplicate, summary và stale bị phát hiện |
| Freshness | Fresh | Stale | Fresh | Ngày 2000 bị loại sau repair |

Chuỗi nguyên nhân–bằng chứng:

1. `drop_eval_record` → ground-truth document không có trong index → retrieval hit `1.000 → 0.667`, Token F1 giảm.
2. Raw-based repair → cleaning/index được dựng lại → quality/freshness phục hồi và retrieval hit trở lại `1.000`.

Corruption ảnh hưởng rõ nhất là `drop_eval_record`; ablation cho retrieval delta `-0.333` và Token F1 delta khoảng `-0.195`. Kết quả repaired Token F1 `0.215` cao hơn baseline `0.214` rất nhỏ do agent/LLM có thể tạo câu trả lời khác giữa các lần gọi; provenance đã được lưu để giải thích khác biệt này.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot và data contract giúp pipeline tái lập, truy vết và repair đáng tin cậy.
2. Quality/freshness checks phải đo nhiều chiều; row count riêng lẻ không phát hiện được duplicate hoặc stale data.
3. Data corruption có thể làm giảm trực tiếp retrieval và answer quality của RAG, nên observability cần gắn với evaluation metrics.

### Nếu có thêm thời gian

Mở rộng frozen test set và bật Ragas để đo context precision, context recall và faithfulness; đồng thời thêm metric history/alerting để theo dõi data drift theo thời gian.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh phần việc và mức hiểu đã thực hiện.
- [x] Có thể giải thích luồng end-to-end, không chỉ module chính.
- [x] Kết luận đều có artifact hoặc metric đối chiếu.
- [x] Không ghi nhận kết quả chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo được viết theo vai trò cá nhân, không sao chép nguyên báo cáo nhóm.

**Họ và tên:** Nhữ Trọng Thành
**Ngày xác nhận:** 2026-08-06
