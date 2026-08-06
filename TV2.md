# TV2 — Lê Thị Linh

**Vai trò:** Data Model & Evaluation Set Owner  
**Phạm vi:** `src/ingestion/cleaning.py`, `src/evaluation/testset.py`

## Mục tiêu

Chuyển Raw Schema thành Clean Schema dùng được cho indexing và tạo evaluation set ổn định cho cả ba lần đánh giá.

## Coding plan

1. Implement `build_clean_dataframe(records, run_date)`:
   - Chuẩn hóa whitespace cho title/summary; làm sạch authors/categories.
   - Parse `published`; tính `age_days = run_date - published`.
   - Tạo `authors_joined`, `categories_joined`, `text_for_embedding`.
   - Loại record thiếu `paper_id`/title, duplicate theo `paper_id`; sort deterministically.
   - Trả DataFrame đúng thứ tự cột contract.
2. Implement `build_test_set(df, output_path)`:
   - Validate đủ document và các cột bắt buộc.
   - Chọn sample deterministically, tạo câu hỏi `summary`, `authors`, `date`, `categories`.
   - Sinh `id` unique; `ground_truth_doc_ids` chứa `paper_id` tồn tại trong clean data.
   - Ghi JSON bằng utility dùng chung.

## Contract bàn giao

- Clean columns: `paper_id`, `title`, `summary`, `published`, `authors_joined`, `categories_joined`, `age_days`, `text_for_embedding`, `abs_url`, `pdf_url`.
- `paper_id` unique/non-null; `age_days` là số nguyên không âm; `text_for_embedding` không rỗng.
- Eval item có: `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids`.

## Done khi

- `LocalEmbeddingIndex.build()` nhận DataFrame mà không lỗi schema.
- Eval set tái tạo cho kết quả ổn định và mọi doc ID đều đối chiếu được.
- Cùng một eval JSON được dùng cho baseline, corrupted và repaired.
