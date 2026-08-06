# Extra Plan — Hoàn thiện Checkpoint C3 và C4

## Mục tiêu

Hoàn thiện pipeline để metrics phản ánh đúng RAG retrieval/answering, corruption tác động có kiểm soát lên frozen test set, repair có thể tái lập và report cung cấp đủ bằng chứng cho ba trạng thái Baseline — Corrupted — Repaired.

## P0 — Sửa tính đúng của evaluation

### 1. Tách semantic retrieval khỏi exact lookup

**Files:** `src/retrieval/qa.py`, `src/evaluation/metrics.py`

- Tính `retrieval_hit_rate` từ kết quả `LocalEmbeddingIndex.search()` nguyên bản.
- Không đưa tài liệu từ `lookup(title)` vào danh sách dùng để tính semantic retrieval hit.
- Nếu vẫn cần exact lookup để trả lời, ghi thành trace/metric riêng như `exact_lookup_hit`.
- Mỗi answer artifact phải lưu rõ `retrieved_doc_ids` dùng để tính metric.

**Done khi:** Baseline retrieval hit không bị bảo đảm bằng cách lấy trực tiếp title/ID từ câu hỏi; metric đo đúng khả năng top-k retrieval của ChromaDB.

### 2. Chuẩn hóa answerer/agent và intent câu hỏi

**Files:** `src/retrieval/qa.py`, `src/retrieval/agent.py`, `src/evaluation/metrics.py`, `src/pipelines/phase1.py`

- Dùng một answerer thống nhất cho baseline, corrupted và repaired.
- Nếu checkpoint yêu cầu agent, build agent một lần cho mỗi index và thu thập được answer, retrieved document IDs và contexts.
- Sửa nhận diện câu hỏi để khớp các mẫu `Who are the authors...` và `What subject categories...`.
- Không được trả summary cho câu hỏi authors/categories.

**Done khi:** Câu hỏi authors/date/categories trả đúng field tương ứng; cả ba trạng thái dùng cùng một logic trả lời.

### 3. Làm ổn định LLM judge

**Files:** `src/evaluation/metrics.py`, `src/retrieval/llm.py`

- Answer rỗng phải được chấm deterministic: `correct=false`, `score=1`, không gọi LLM.
- Ghi `judge_mode`, provider, model và trạng thái fallback vào answer/metrics artifact.
- Không âm thầm chuyển sang fallback; phải ghi lỗi hoặc số mẫu dùng fallback trong report.
- Pin model/seed nếu provider hỗ trợ; cân nhắc cache verdict theo hash của question/reference/prediction.
- Dùng so sánh deterministic cho date/authors/categories; chỉ dùng LLM judge cho câu hỏi summary nếu phù hợp.

**Done khi:** Answer rỗng không thể nhận `score=5`; chạy lặp lại trên cùng input cho kết quả judge có thể giải thích và không trộn evaluator mà không báo cáo.

## P1 — Hoàn thiện controlled corruption và repair

### 4. Bảo đảm corruption overlap frozen test set

**Files:** `src/ingestion/corruption.py`, `src/pipelines/corruption_flow.py`

- Đọc `ground_truth_doc_ids` từ `data/eval/test_set.json`.
- Bảo đảm ít nhất một kịch bản chính (blank summary, stale date, duplicate hoặc noise) tác động một frozen document.
- Giữ seed cố định và không thay đổi frozen test set trong corruption flow.
- Bổ sung vào log: `overlap_with_eval`, `affected_eval_doc_ids` và danh sách scenario tác động từng ID.
- Noise phải xuất hiện thực tế trong `text_for_embedding` được index.

**Done khi:** `corruption_log.json` chứng minh được overlap; corrupted retrieval/Token F1 có thay đổi quan sát được và quality report có check FAIL.

### 5. Chuẩn hóa artifact corrupted và luồng đọc file

**Files:** `src/core/config.py`, `src/ingestion/corruption.py`, `src/pipelines/corruption_flow.py`

- Đổi output bắt buộc thành `data/clean/papers_corrupted.csv` (có thể giữ JSON cùng tên gốc).
- Luồng C4 phải: tạo corruption → lưu CSV → đọc lại CSV → validate schema → build corrupted index.
- Khi đọc CSV, bảo toàn chuỗi rỗng thay vì tự chuyển thành `NaN`.
- Repair chỉ được đọc `data/raw/crossref_records.json` và chạy lại cleaning; không fetch Crossref API.

**Done khi:** Corruption flow thực sự tiêu thụ `papers_corrupted.csv`; repaired data có 24 unique records và được dựng từ raw snapshot.

### 6. Đo ảnh hưởng riêng của từng corruption

**Files:** `src/ingestion/corruption.py`, `src/pipelines/corruption_flow.py`, `src/observability/reporting.py`

- Tách scenario thành các hàm độc lập hoặc cấu hình bật/tắt.
- Chạy ablation tối thiểu cho các scenario ảnh hưởng retrieval và ghi delta theo scenario.
- Xác định scenario nghiêm trọng nhất bằng metric thay vì chỉ suy luận từ log.

**Done khi:** Report có bảng scenario → affected eval IDs → retrieval delta/Token F1 delta và nêu được scenario gây ảnh hưởng lớn nhất.

## P1 — Hoàn thiện báo cáo checkpoint

### 7. Bổ sung diễn giải C3

**File:** `src/observability/reporting.py`

Thêm phần `Metric interpretation` vào `phase1_report.md`:

- `retrieval_hit_rate` đo khả năng retriever đưa ground-truth document vào top-k, không đo độ đúng của câu trả lời cuối.
- Token F1 có thể nhỏ hơn 1 dù retrieval đúng do câu trả lời tóm tắt, diễn đạt lại hoặc chỉ sử dụng một phần ground truth.
- Hiển thị judge provider/mode và trạng thái Ragas rõ ràng.

**Done khi:** Report tự chứa câu trả lời cho hai câu hỏi giải thích của C3.

### 8. Bổ sung đủ ba trạng thái cho observability C4

**Files:** `src/pipelines/corruption_flow.py`, `src/observability/reporting.py`

- Đọc hoặc tính baseline quality và baseline freshness.
- Các bảng RAG metrics, Data quality và Freshness đều phải có ba cột `Baseline`, `Corrupted`, `Repaired`.
- Liệt kê tên check fail thay vì chỉ hiển thị số lượng.
- Thêm phần giải thích scenario nghiêm trọng nhất và lý do repair từ raw snapshot thay vì fetch lại API.
- Chỉ hiển thị recovery ratio như phục hồi thành công khi metric có hướng cải thiện hợp lệ.

**Done khi:** `corruption_report.md` cung cấp đầy đủ bằng chứng C4 và không diễn giải metric judge tăng do lỗi như một cải thiện thật.

## P2 — Kiểm thử và khả năng tái lập

### 9. Thêm automated tests

**Files:** thư mục `tests/`

- Test frozen test set không bị ghi đè khi không bật refresh.
- Test semantic retrieval metric không dùng exact lookup oracle.
- Test answer rỗng luôn bị judge fail.
- Test mỗi corruption deterministic với seed cố định và có overlap.
- Test corrupted quality FAIL; baseline/repaired quality PASS.
- Test repair dùng raw snapshot và không gọi network.
- Test report có đủ ba trạng thái và vẫn render khi một metric bị thiếu.

**Done khi:** Test suite chạy pass và không cần network/API key cho các unit test.

## Trình tự thực hiện đề xuất

1. Sửa retrieval/answerer và intent câu hỏi.
2. Làm ổn định judge và bổ sung provenance.
3. Chuẩn hóa tên file và data contract của corrupted artifact.
4. Bảo đảm overlap, sau đó bổ sung ablation theo scenario.
5. Nâng cấp hai report.
6. Viết test và chạy lại toàn bộ pipeline.

## Lệnh nghiệm thu

```bash
uv run pytest
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

Kiểm tra cuối:

- `data/results/baseline_metrics.json` và `baseline_answers.json` tồn tại.
- Baseline quality/freshness đều PASS/fresh.
- `data/clean/papers_corrupted.csv` và `corruption_log.json` tồn tại.
- Corrupted quality có FAIL và metric retrieval/Token F1 giảm quan sát được.
- Repaired được dựng từ raw snapshot và phục hồi gần hoặc bằng baseline.
- `corruption_report.md` có đủ Baseline — Corrupted — Repaired cho RAG metrics, quality và freshness.
