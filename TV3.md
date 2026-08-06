# TV3 — Mai Hồng Sơn

**Vai trò:** Data Observability Owner  
**Phạm vi:** `src/observability/quality.py`, `src/observability/reporting.py`

## Mục tiêu

Phát hiện sai lệch dữ liệu và xuất báo cáo có thể so sánh giữa baseline, corrupted và repaired.

## Coding plan

1. Implement `run_data_quality_checks(df, settings, report_name)`:
   - Check row count, schema bắt buộc, null/unique của `paper_id`, title rỗng, summary ngắn/rỗng, duplicate và stale rows.
   - Mỗi check trả `name`, `value`, `threshold`, `passed`; thêm trạng thái tổng hợp.
   - Ghi JSON riêng theo `report_name` trong `settings.paths.quality_dir`.
2. Implement `build_freshness_report(df, settings, report_path)`:
   - Tính latest/oldest published, stale rows, total rows và `is_fresh` theo `freshness_threshold_days`.
   - Xử lý rõ DataFrame rỗng hoặc ngày không parse được; ghi JSON artifact.
3. Implement reporting:
   - `generate_phase1_report`: source summary + metrics + quality + freshness.
   - `generate_corruption_report`: bảng baseline/corrupted/repaired và delta/phục hồi của metrics.
   - Dùng Markdown dễ kiểm tra, không hard-code kết quả.

## Contract bàn giao

- Các report JSON phải serializable, giữ cùng key giữa các trạng thái.
- Hàm observability chỉ đo và báo cáo, không mutate DataFrame đầu vào.
- TV4 truyền trực tiếp payload trả về vào `reporting.py`.

## Done khi

- Baseline sạch cho kết quả hợp lý; corruption tạo ra check fail quan sát được.
- Report thể hiện đúng artifact/metrics đầu vào, kể cả khi một metric thiếu.
- Freshness report phân biệt được `fresh`, `stale` và dữ liệu không hợp lệ.
