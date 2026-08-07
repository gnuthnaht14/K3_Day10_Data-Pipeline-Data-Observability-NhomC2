# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Mai Hồng Sơn |
| MSSV | 2A202601921 |
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm C2 |
| Vai trò chính | Observability owner |
| Repository | `https://github.com/gnuthnaht14/K3_Day10_Data-Pipeline-Data-Observability-NhomC2.git` |
| Ngày hoàn thành | 2026-08-07 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data quality checks | `src/observability/quality.py` — `run_data_quality_checks` | Cleaned `DataFrame`, `Settings`, report name | Quality JSON tại `data/quality/<state>.json` | Hoàn thành |
| Freshness monitoring | `src/observability/quality.py` — `build_freshness_report` | Cleaned `DataFrame`, `Settings`, output path | Freshness JSON cho baseline/corrupted/repaired | Hoàn thành |
| Baseline reporting | `src/observability/reporting.py` — `generate_phase1_report` | Source summary, evaluation metrics, quality, freshness | `data/reports/phase1_report.md` | Hoàn thành |
| Comparison reporting | `src/observability/reporting.py` — `generate_corruption_report` | Ba bộ metrics, quality, freshness, corruption log, ablation | `data/reports/corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Rà soát data contract | `src/ingestion/cleaning.py`, `src/pipelines/phase1.py` | Thống nhất quality check dùng Clean Schema gồm `paper_id`, title, summary, ngày publish, `age_days` và `text_for_embedding`. |
| Đối chiếu artifact sau integration | `src/pipelines/corruption_flow.py` | Xác nhận report khớp metrics, quality/freshness JSON và corruption log của ba trạng thái. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Kiểm tra chất lượng Clean Schema | `quality.py`; `data/quality/baseline.json`, `corrupted.json`, `repaired.json` | Baseline và repaired pass 10/10 checks; corrupted fail 4 checks | Đọc các quality JSON và comparison report |
| Theo dõi độ mới corpus | `quality.py`; `freshness_report.json`, `freshness_corrupted.json`, `freshness_repaired.json` | Phát hiện 1 record stale khi corrupted; repaired trở lại fresh | Đối chiếu `stale_rows`, date range và `is_fresh` |
| Tạo báo cáo baseline | `reporting.py`; `data/reports/phase1_report.md` | Tổng hợp nguồn Crossref, 24 records, 12 samples, evaluation, quality và freshness | Mở Markdown report và đối chiếu JSON nguồn |
| Tạo báo cáo corruption/repair | `reporting.py`; `data/reports/corruption_report.md` | Bảng Baseline/Corrupted/Repaired, delta, recovery ratio, provenance và ablation từng scenario | Đối chiếu metrics JSON, corruption log và report |

Output cụ thể: khi dữ liệu bị corrupt, quality chuyển từ `pass` sang `fail` với 4 check fail (`paper_id_unique`, `duplicate_rows`, `summary_min_length`, `stale_rows`); freshness chuyển từ `fresh` sang `stale`. Sau repair từ raw snapshot, cả quality và freshness đều quay lại trạng thái pass/fresh.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

RAG có thể suy giảm vì dữ liệu rỗng, duplicate, ngắn hoặc cũ. Chỉ xem metric cuối của agent không đủ để xác định nguyên nhân. Phần observability phải phát hiện lỗi ở dataset, lưu artifact có thể truy vết và liên hệ các data signal với metrics của baseline, corrupted và repaired.

### Cách triển khai

`run_data_quality_checks` kiểm tra Clean Schema theo các rule độc lập: row count, required schema, `paper_id` không rỗng/không trùng, title không rỗng, summary tối thiểu 20 ký tự, `text_for_embedding` không rỗng, `age_days` hợp lệ và số record stale không vượt ngưỡng. Mỗi rule chứa `value`, `threshold` và `passed`; report tổng có danh sách failed-check names. Cách này cho phép pipeline vẫn ghi được diagnostic artifact thay vì chỉ trả một boolean chung.

`build_freshness_report` parse cột `published` ở UTC, tính date mới nhất/cũ nhất, số stale rows và invalid dates. Status là `fresh`, `stale`, `invalid` hoặc `empty`. Ngưỡng hiện dùng là 180 ngày từ `Settings`.

`generate_phase1_report` đưa source, evaluation metrics, quality và freshness vào bảng Markdown. `generate_corruption_report` đặt ba trạng thái cạnh nhau, tính `corruption delta`, `recovery delta` và `recovery ratio = (repaired - corrupted) / (baseline - corrupted)`. Report cũng ghi provenance của answerer/judge, frozen-test overlap IDs và ablation từng corruption scenario để tránh kết luận chỉ dựa vào một metric tổng.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Cleaned `DataFrame` theo Clean Schema, `Settings`, metrics từ evaluation và corruption log. |
| Output | JSON quality/freshness trong `data/quality/`; baseline/comparison Markdown trong `data/reports/`. |
| Module phụ thuộc | `core.config.Settings`, `core.utils.write_json`, `core.utils.write_text`, `pandas`. |
| Module sử dụng output | `pipelines.phase1`, `pipelines.corruption_flow` và người vận hành đọc artifact/report. |
| Điều kiện lỗi xử lý | Dataset rỗng, thiếu cột, DOI null/duplicate, summary/text rỗng, age không hợp lệ, stale date, published date không parse được và metric bị thiếu. |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run pytest -q
```

- **Kết quả mong đợi:** Baseline pass/fresh; corruption tạo failure có chủ đích và làm metric suy giảm; repair khôi phục data signal và metric.
- **Kết quả thực tế từ artifact:** 24 clean records, 12 evaluation samples; quality `pass → fail → pass`; freshness `fresh → stale → fresh`; retrieval hit `1.000 → 0.667 → 1.000`.
- **Artifact/log:** `data/results/*_metrics.json`, `data/results/corruption_log.json`, `data/quality/*.json`, `data/reports/*.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Corrupted dataset vẫn có 24 dòng vì flow vừa drop một record vừa thêm một duplicate. Nếu chỉ kiểm tra row count, lỗi có thể bị bỏ sót.
- **Các phương án đã cân nhắc:** (1) Chỉ kiểm tra row count; (2) chỉ trả status pass/fail tổng; (3) kiểm tra nhiều rule độc lập và lưu tên rule fail.
- **Phương án đã chọn:** Phương án 3.
- **Lý do:** Row count không thể phát hiện duplicate, summary bị blank hoặc publication date bị đổi thành 2000-01-01. Rule độc lập làm rõ loại lỗi và hỗ trợ repair/triage.
- **Bằng chứng quyết định phù hợp:** `data/quality/corrupted.json` có `total_rows = 24` nhưng vẫn fail 4 rule; baseline và repaired cùng 24 rows nhưng pass 10/10 rule.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Chỉ số row count của corrupted bằng baseline (`24`), trong khi dataset đã bị corruption.
- **Bước tái hiện:** Đối chiếu `data/quality/baseline.json`, `data/quality/corrupted.json` và `data/results/corruption_log.json`.
- **Nguyên nhân gốc:** `drop_eval_record` giảm một dòng, nhưng `add_duplicate_rows` tăng một dòng; tổng row count không đổi. Đồng thời các lỗi summary/date không làm thay đổi số record.
- **Cách xử lý:** Không dùng row count như signal duy nhất; bổ sung uniqueness, duplicate, summary minimum length, embedding text, age validity và stale-row checks trong cùng quality report.
- **Cách xác minh sau khi sửa:** Corrupted report fail đúng `paper_id_unique`, `duplicate_rows`, `summary_min_length`, `stale_rows`; repaired report không còn failed check.
- **Điều học được:** Quan sát chất lượng cần nhiều chiều và phải gắn rule với nguyên nhân có thể hành động, không chỉ đo volume dữ liệu.

## 7. Hiểu biết về luồng end-to-end

1. Crossref được lưu thành raw snapshot và parse thành `PaperRecord`. Cleaning chuẩn hóa thành Clean Schema, tạo `text_for_embedding`; MiniLM embedding đưa text vào ChromaDB.
2. Evaluation set lưu question, ground truth và ground-truth DOI. Retrieval hit kiểm tra DOI đúng có trong semantic top-k; Token F1 và judge đánh giá câu trả lời cuối.
3. Quality kiểm tra tính đầy đủ, uniqueness, nội dung và tính hợp lệ của record. Freshness chỉ tập trung vào published date, tuổi dữ liệu và stale status.
4. Cùng một frozen test set phải được dùng ở baseline/corrupted/repaired để metric delta phản ánh thay đổi dữ liệu/index, không phải thay đổi câu hỏi. Artifact baseline ghi SHA-256 test set `5899992d6c85c56c3913fa9bc316bcef4d1ae409b350ce337ca484ead2e81ed5`.
5. Repair thành công khi repair từ raw snapshot tạo lại cleaned/index, xóa các quality/freshness failure và đưa metric về gần baseline trên cùng test set.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `samples` | 12 | 12 | 12 | Cùng kích thước test set nên phép so sánh hợp lệ. |
| `retrieval_hit_rate` | 1.0000 | 0.6667 | 1.0000 | Giảm 33.33 percentage points sau corruption và phục hồi hoàn toàn. |
| `exact_lookup_hit_rate` | 1.0000 | 0.6667 | 1.0000 | Cùng xu hướng; metric này được báo riêng, không thay semantic retrieval hit. |
| `mean_token_f1` | 0.2137 | 0.1632 | 0.2145 | Giảm 0.0505 khi corrupted; repaired cao hơn baseline 0.0008, một chênh lệch rất nhỏ. |
| `judge_accuracy` | 0.5000 | 0.2500 | 0.5000 | Giảm 25 percentage points rồi phục hồi về baseline. |
| `mean_judge_score` | 3.0000 | 2.1667 | 3.0000 | Giảm 0.8333 điểm; repaired khôi phục hoàn toàn. |
| Quality checks | pass, 10/10 | fail, 6/10 | pass, 10/10 | Corrupted phát hiện 4 lỗi data quality. |
| Freshness status | fresh, 0 stale | stale, 1 stale | fresh, 0 stale | Date bị đổi thành 2000-01-01 được phát hiện và phục hồi. |

### Kết luận từ số liệu

1. `drop_eval_record`, blank summary, embedding noise, stale date và duplicate row → quality fail 4 rule, freshness stale → retrieval hit giảm `1.0000 → 0.6667`, Token F1 giảm `0.2137 → 0.1632`, judge accuracy giảm `0.5000 → 0.2500`.
2. Repair từ `data/raw/crossref_records.json` → rebuilt clean dataset pass 10/10 checks, freshness fresh → retrieval hit và judge metrics quay về baseline; Token F1 đạt `0.2145`, gần bằng baseline `0.2137`.

Scenario ảnh hưởng retrieval rõ nhất là `drop_eval_record`: ablation ghi retrieval delta `-0.3333` và Token F1 delta `-0.1947`. Các scenario blank summary, embedding noise, stale date và duplicate row không làm retrieval hit giảm trong ablation đơn lẻ, nhưng vẫn tạo data-quality hoặc freshness signal quan trọng. Do main evaluation dùng tool-calling agent còn ablation dùng deterministic answerer, report không so sánh trực tiếp hai Token F1 này.

Kết quả đáng chú ý là repaired `mean_token_f1` cao hơn baseline khoảng `0.0008` thay vì bằng tuyệt đối. Đây là mức chênh lệch rất nhỏ của câu trả lời/diễn đạt; các provenance cho thấy cả ba run dùng `gpt-4o-mini`, 12 `langchain_tool_agent` answers, không có answerer/judge fallback. Vì vậy không nên diễn giải chênh lệch này như một cải thiện đáng kể.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot, Clean Schema và frozen test set tạo điều kiện để kết quả corruption/repair có thể tái lập và truy vết.
2. Data observability cần nhiều rule: row count không đủ để phát hiện duplicate, content loss hoặc stale data.
3. Quality/freshness signal chỉ thuyết phục khi được đối chiếu với retrieval và answer metrics trên cùng evaluation set.

### Nếu có thêm thời gian

Bật `RUN_RAGAS=1` để bổ sung context precision, context recall, answer relevancy và faithfulness; đồng thời lưu lịch sử quality/freshness theo từng lần chạy để tạo alert khi stale rows, duplicate rate hoặc metric delta vượt ngưỡng.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu đã thực hiện.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module observability.
- [x] Mọi kết luận về metrics, quality và freshness đều có artifact để đối chiếu.
- [x] Tôi không ghi kết quả chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này được viết theo vai trò cá nhân, không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Mai Hồng Sơn

**Ngày xác nhận:** 2026-08-07
