# TV4 — Nhữ Trọng Thành

**Vai trò:** Corruption & Integration Owner  
**Phạm vi:** `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`

## Mục tiêu

Ghép pipeline end-to-end, tạo corruption có thể tái hiện và chứng minh repair khôi phục chất lượng.

## Coding plan

1. Implement `corrupt_clean_dataframe(df, output_log_path)`:
   - Copy DataFrame trước khi sửa; dùng random seed cố định.
   - Tạo các lỗi: drop latest rows, blank summary, inject noise, truncate title, làm cũ published, thêm duplicate.
   - Recompute `age_days`/`text_for_embedding` khi field nguồn thay đổi.
   - Ghi log loại lỗi, record ID, tham số và số lượng bị tác động.
2. Implement `phase1.main()`:
   - Load settings → fetch/load raw → clean → lưu CSV/JSON.
   - Build baseline Chroma index → build/load eval set → evaluate.
   - Chạy quality/freshness → tạo phase-1 report.
   - Tôn trọng `refresh_source` và `refresh_test_set`.
3. Implement `corruption_flow.main()`:
   - Require baseline artifacts; load clean baseline và eval set cũ.
   - Corrupt → save → rebuild isolated index → evaluate → quality/freshness.
   - Repair bằng cách load raw và chạy lại cleaning, không sửa trực tiếp corrupted data.
   - Save repaired artifacts → rebuild index → evaluate → comparison report.

## Contract tích hợp

- Validate required columns trước indexing/evaluation; fail-fast với lỗi có ngữ cảnh.
- Dùng ba collection/manifest/path riêng từ `Settings`; không ghi đè baseline.
- Giữ nguyên evaluation set để phép so sánh có ý nghĩa.

## Done khi

- `script/run_phase1.py` và `script/run_corruption_flow.py` chạy đúng thứ tự.
- Sinh đủ clean, embeddings, eval, metrics, answers, quality, freshness và reports.
- Metrics/report chứng minh được chuỗi baseline → suy giảm do corruption → phục hồi sau repair.
