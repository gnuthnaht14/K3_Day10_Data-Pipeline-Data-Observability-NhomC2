# TV1 — Lường Thị Hảo

**Vai trò:** Source Ingestion Owner  
**Phạm vi:** `src/ingestion/crossref.py`

## Mục tiêu

Tạo nguồn dữ liệu raw ổn định từ Crossref và bàn giao `list[PaperRecord]` cho bước cleaning.

## Coding plan

1. Implement `parse_crossref_payload(payload)`:
   - Đọc `payload["message"]["items"]` an toàn.
   - Map DOI, title, abstract, author, subject, published/updated và URL vào `PaperRecord`.
   - Chuẩn hóa khoảng trắng; bỏ record thiếu DOI hoặc title; trả về `list[PaperRecord]`.
2. Implement `fetch_source_records(settings)`:
   - Gọi `https://api.crossref.org/works` với query/filter/rows từ `Settings`.
   - Thêm timeout và retry/backoff cho `429`, `500`, `502`, `503`, `504`.
   - Lưu response gốc vào `settings.paths.raw_api_response`.
   - Parse và lưu records vào `settings.paths.raw_records_json`.
3. Implement `load_raw_records(path)`:
   - Đọc JSON snapshot, validate cấu trúc và khởi tạo lại `PaperRecord`.

## Contract bàn giao

- Output: JSON array và `list[PaperRecord]` đúng các field trong dataclass.
- `paper_id` dùng DOI, không rỗng; list field luôn là `list[str]`; field text không dùng `None`.
- TV2 có thể chạy cleaning từ file raw mà không cần gọi lại API.

## Done khi

- Parse được payload hợp lệ và chịu được field thiếu.
- Raw response/raw records được tạo đúng path và đọc lại không mất dữ liệu.
- Không commit API key hoặc dữ liệu lỗi chưa được log.
