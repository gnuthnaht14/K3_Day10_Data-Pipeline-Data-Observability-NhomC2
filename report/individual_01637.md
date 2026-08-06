# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Lường Thị Hảo           |
| MSSV               | 2A202601637                    |
| Khóa/Lớp         | K3              |
| Tên nhóm         | NhomC2     |
| Vai trò chính    | Source Ingestion Owner                 |
| Repository         | https://github.com/gnuthnaht14/K3_Day10_Data-Pipeline-Data-Observability-NhomC2.git |
| Ngày hoàn thành | [2026/06/08]               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | -------------- |
| Gọi Crossref API và parse payload | `src/ingestion/crossref.py` — `parse_crossref_payload()` | JSON payload thô từ Crossref (`payload["message"]["items"]`) | `list[PaperRecord]` (11 field/bản ghi) | Hoàn thành |
| Retry/backoff khi API lỗi tạm thời | `src/ingestion/crossref.py` — `_request_with_retry()` | URL + params request | Response JSON hợp lệ, hoặc `RuntimeError` sau khi hết lượt retry | Hoàn thành |
| Điều phối fetch + lưu raw artifacts | `src/ingestion/crossref.py` — `fetch_source_records()` | `Settings` (từ `load_settings()`) | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàn thành |
| Đọc lại raw snapshot | `src/ingestion/crossref.py` — `load_raw_records()` | Đường dẫn file `crossref_records.json` | `list[PaperRecord]` (roundtrip đúng dữ liệu đã lưu) | Hoàn thành |

Ownership giới hạn ở `src/ingestion/crossref.py`. Output (`crossref_records.json`) là input trực tiếp cho `cleaning.py` (Thành viên 2) và cho bước repair-from-raw ở Pha 2 (Thành viên 4).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| ---------- | -------------------------------- | --------- |
| Chạy thử `build_clean_dataframe()` (`cleaning.py`) với 5 record thật lấy từ Crossref để kiểm tra tương thích schema giữa 2 file | Thành viên 2 — `cleaning.py` | Xác nhận `cleaning.py` xử lý đúng dữ liệu thật (bóc tag `<jats:p>` lồng nhau, tính `age_days`, dedup) không lỗi |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------- |
| Implement parse Crossref payload thành `PaperRecord` | `parse_crossref_payload()` | 24 record hợp lệ (sau lọc) từ 24 item thô | `pytest tests/test_crossref.py -v` — 18/18 test pass |
| Implement retry/backoff cho 429/503 | `_request_with_retry()` | Không treo pipeline khi Crossref rate-limit | Test mock 429→200 và mất mạng liên tục — cả 2 case pass |
| Lưu raw artifacts để audit | `fetch_source_records()` | `data/raw/crossref_response.json` (response gốc đầy đủ), `data/raw/crossref_records.json` (24 record phẳng) | Chạy `python script/debug_crossref.py` với API thật, kiểm tra file tồn tại và mở xem nội dung |

Output cụ thể: `data/raw/crossref_records.json` — 24 bản ghi `PaperRecord` (paper_id, title, summary chưa bóc tag, authors, categories, primary_category, published, updated, abs_url, pdf_url, comment), đã xác minh bằng cách chạy thật với query mặc định `"agentic retrieval augmented generation large language model"`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

`crossref.py` là điểm vào (entry point) của toàn bộ pipeline: chịu trách nhiệm lấy dữ liệu thô từ nguồn bên ngoài (Crossref REST API), đảm bảo dữ liệu lấy về đủ điều kiện tối thiểu để dùng ở bước sau (có DOI, title, abstract), và lưu lại raw artifact để có thể **truy vết và repair** khi Pha 2 chủ động tạo lỗi dữ liệu.

### Cách triển khai

- **Lọc thô, không làm sạch sâu:** Chỉ giữ item có đủ `DOI` + `title` + `abstract`. Không bóc tag XML/HTML (`<jats:p>`) khỏi text — việc này cố ý để lại cho `cleaning.py`, tránh 2 file cùng làm 1 việc.
- **Chuẩn hóa ngày xuất bản:** Crossref trả ngày dạng `date-parts` (`[[year, month, day]]`), có thể thiếu tháng/ngày. Dùng thứ tự ưu tiên `published-print` → `published-online` → `published` → `issued`, tự điền `01` cho phần thiếu.
- **Trường "updated" mượn từ field khác:** Crossref không có field `updated` như arXiv, nên lấy từ `indexed`/`deposited`/`created` (timestamp ISO).
- **Retry có phân loại:** Chỉ retry với `429`/`503` (backoff mũ + đọc header `Retry-After` nếu có), các lỗi HTTP khác (ví dụ `400`) raise ngay để không lãng phí thời gian retry cho lỗi không tự hết.

### Input, output và contract

| Thành phần | Mô tả |
| ------------ | ------- |
| Input | `Settings` object từ `load_settings()` — dùng `source_query`, `source_filter`, `max_results`, `paths.raw_api_response`, `paths.raw_records_json` |
| Output | `list[PaperRecord]` (11 field), đồng thời ghi 2 file JSON: response thô và records đã parse |
| Module phụ thuộc | `core.config.Settings`/`load_settings` |
| Module sử dụng output | `ingestion.cleaning.build_clean_dataframe()` (đọc `list[PaperRecord]`); `pipelines.corruption_flow` (đọc lại `crossref_records.json` qua `load_raw_records()` khi cần repair) |
| Điều kiện lỗi cần xử lý | Rate limit (429), lỗi server tạm thời (503), mất kết nối mạng, item thiếu title/abstract/DOI, author không có tên (tổ chức hoặc entry rỗng), ngày xuất bản thiếu một phần |

### Cách xác minh

```bash
# Unit test có mock (khong can mang)
pytest tests/test_crossref.py -v

# Test that voi API Crossref that
python script/debug_crossref.py
```

- **Kết quả mong đợi:** 18/18 unit test pass; script debug in ra danh sách record thật kèm field, lưu 2 file raw, `load_raw_records()` đọc lại đúng số lượng.
- **Kết quả thực tế:** 18/18 test pass. Chạy thật với `max_results=5` trả về đúng 5/5 record hợp lệ (title, authors, published, updated đều đúng, kể cả tên tác giả tiếng Nga không bị lỗi encoding); sau đó bỏ giới hạn debug, chạy lại với `max_results=24` mặc định để lấy đủ dữ liệu baseline.
- **Artifact/log:** `data/raw/crossref_response.json`, `data/raw/crossref_records.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần quyết định làm sạch text (bóc tag `<jats:p>`) ngay trong `crossref.py`, hay để nguyên và chuyển việc đó sang `cleaning.py`.
- **Các phương án đã cân nhắc:**
  1. Bóc tag ngay trong `parse_crossref_payload()` để `PaperRecord` luôn chứa text sạch.
  2. Giữ nguyên tag trong `PaperRecord`, để `cleaning.py` xử lý.
- **Phương án đã chọn:** Phương án 2 — giữ nguyên raw text (kể cả tag XML) trong output của `crossref.py`.
- **Lý do:** Đúng theo phân công vai trò trong nhóm (`crossref.py` = ingestion, `cleaning.py` = data model), tránh 2 module cùng chịu trách nhiệm 1 loại biến đổi dữ liệu (single responsibility). Đồng thời giữ raw artifact "thô đúng nghĩa" — nếu sau này phát hiện logic bóc tag có lỗi, có thể sửa lại `cleaning.py` mà không cần fetch lại dữ liệu từ Crossref.
- **Bằng chứng quyết định phù hợp:** Test `test_valid_item_parsed_correctly` xác nhận `summary` trong `PaperRecord` vẫn còn `<jats:p>`; chạy tiếp qua `build_clean_dataframe()` xác nhận tag được bóc sạch đúng ở bước sau, kể cả trường hợp 2 khối `<jats:p>` nối tiếp có xuống dòng/thụt lề trong dữ liệu thật.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  ```
  TypeError: Paths.__init__() missing 26 required positional arguments: 'project_dir', 'workspace_dir', ...
  ```
- **Lệnh hoặc bước tái hiện:** Tự khởi tạo `Settings(paths=Paths(raw_api_response=..., raw_records_json=...))` bằng tay trong script debug, thay vì dùng hàm factory có sẵn của project.
- **Nguyên nhân gốc:** Giả định sai cấu trúc `Settings`/`Paths` thật của project (nghĩ chỉ có vài field liên quan Crossref), trong khi `Paths` thật có 27 field (bao gồm cả đường dẫn cho corrupted, repaired, eval, reports — dùng chung cho toàn bộ pipeline, không riêng bước ingestion).
- **Cách xử lý:** Đổi sang dùng đúng hàm `load_settings()` có sẵn trong `core/config.py`, hàm này tự tính toàn bộ đường dẫn dựa trên vị trí project. Khi cần đổi tham số (ví dụ giảm `max_results` để debug nhanh), dùng `dataclasses.replace(settings, max_results=5)` vì `Settings`/`Paths` là `frozen=True` (immutable), không gán trực tiếp được.
- **Cách xác minh sau khi sửa:** Chạy lại script debug và `pytest tests/test_crossref.py -v` — không còn lỗi `TypeError`, 18/18 test pass.
- **Điều học được:** Không nên tự đoán/tự dựng lại cấu hình của project khi có sẵn factory function chính thức — dễ tạo ra 2 "phiên bản sự thật" khác nhau (config giả trong test vs config thật trong pipeline) và che giấu lỗi thật cho tới khi tích hợp.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Từ Crossref đến vector index:** `crossref.py` gọi API Crossref → lọc thô (đủ DOI/title/abstract) → lưu raw. `cleaning.py` đọc raw, bóc tag XML, tính `age_days`, gộp authors/categories, tạo cột `text_for_embedding`, lưu ra `papers_clean.csv/json`. Bước tiếp theo (thuộc module `retrieval/`, ngoài phạm vi của mình) đọc `text_for_embedding` từ file clean này, sinh embedding, và nạp vào ChromaDB.

2. **Evaluation set và ground-truth:** `testset.py` (Thành viên 2) tạo bộ câu hỏi dựa trên `papers_clean.csv/json`, mỗi câu hỏi gắn với `paper_id` làm ground-truth document ID. Khi đánh giá, hệ thống so sánh document mà retrieval trả về với `paper_id` ground-truth để tính `retrieval_hit_rate`, và so sánh câu trả lời sinh ra với đáp án kỳ vọng để tính `mean_token_f1`/`judge_accuracy`.

3. **Quality checks khác freshness monitoring:** Quality check (trong `quality.py`) kiểm tra tính toàn vẹn cấu trúc của dữ liệu tại một thời điểm — bản ghi có thiếu field không, summary có rỗng/quá ngắn không, có duplicate không. Freshness monitoring kiểm tra khía cạnh thời gian — dữ liệu có bị "cũ" so với ngưỡng `freshness_threshold_days` (180 ngày, theo `config.py`) hay không, dựa trên `age_days` tính từ `cleaning.py`.

4. **Vì sao dùng cùng test set cho cả 3 trạng thái:** Để đảm bảo mọi khác biệt về metric (`retrieval_hit_rate`, `mean_token_f1`...) giữa baseline/corrupted/repaired chỉ phản ánh **thay đổi của dữ liệu**, không phải do câu hỏi eval khác nhau. Nếu đổi test set giữa các lần đo, không thể tách bạch được nguyên nhân là do corruption hay do câu hỏi đánh giá khác nhau.

5. **Repair thành công khi:** metrics ở trạng thái repaired quay trở lại gần với baseline (không nhất thiết bằng 100%, nhưng phục hồi rõ rệt so với corrupted), đồng thời quality/freshness report ở trạng thái repaired không còn báo lỗi giống như ở trạng thái corrupted — cả 2 tín hiệu (metric agent + report quality) phải đồng thuận thì mới coi là repair thành công.

## 8. Phân tích kết quả

Kết quả Pha 2 cho thấy corruption gây ảnh hưởng rõ rệt đến cả hiệu năng retrieval/answering và các tín hiệu chất lượng dữ liệu. Sau khi repair từ raw snapshot, các metric chính phục hồi về mức baseline, đồng thời Quality và Freshness cũng trở lại trạng thái đạt.

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Nhận xét của cá nhân |
| -------------- | -------: | --------: | -------: | ---------------------: | --------------------- |
| `retrieval_hit_rate` | 1.000 | 0.667 | 1.000 | -0.333 | Ground-truth document bị mất khỏi index, làm semantic retrieval miss một số query |
| `mean_token_f1` | 0.214 | 0.163 | 0.215 | -0.051 | Context/answer bị thiếu hoặc nhiễu nên chất lượng câu trả lời giảm |
| `judge_accuracy` | 0.500 | 0.250 | 0.500 | -0.250 | Chất lượng answer giảm rõ rệt khi dữ liệu bị corruption |
| `mean_judge_score` | 3.000 | 2.167 | 3.000 | -0.833 | Judge score phục hồi hoàn toàn về baseline sau repair |
| Quality checks | PASS | FAIL | PASS | 4 checks fail | Corruption làm phát sinh lỗi duplicate, summary và stale data; repair đã khôi phục trạng thái PASS |
| Freshness status | Fresh | Stale | Fresh | 1 stale row | Repair đã xóa/khôi phục dữ liệu stale, đưa freshness trở lại trạng thái Fresh |

### Kết luận từ số liệu

Kết quả cho thấy corruption dữ liệu có tác động trực tiếp đến chất lượng của pipeline retrieval-augmented generation. Khi ground-truth document bị xóa khỏi index, `retrieval_hit_rate` giảm từ 1.000 xuống 0.667, tức một phần query không còn retrieve được đúng document mục tiêu. Đồng thời, `mean_token_f1` giảm từ 0.214 xuống 0.163 và `judge_accuracy` giảm từ 0.500 xuống 0.250, cho thấy việc mất dữ liệu retrieval không chỉ ảnh hưởng đến bước tìm kiếm mà còn làm giảm chất lượng answer cuối cùng.

Sau khi rebuild từ raw snapshot, `retrieval_hit_rate` phục hồi từ 0.667 lên 1.000, `judge_accuracy` phục hồi từ 0.250 lên 0.500 và `mean_judge_score` phục hồi từ 2.167 lên 3.000. `mean_token_f1` đạt 0.215, cao hơn baseline 0.214 một lượng rất nhỏ. Điều này cho thấy repair đã khôi phục được chất lượng pipeline về tương đương baseline.

Hai chuỗi quan hệ nhân quả chính quan sát được là:

1. Xóa ground-truth document → semantic retrieval miss → `retrieval_hit_rate` giảm từ 1.000 xuống 0.667 và Token F1 giảm.
2. Rebuild từ raw snapshot → Clean Schema/Quality/Freshness phục hồi → repaired retrieval hit trở lại 1.000.

### Corruption nào ảnh hưởng rõ nhất và vì sao?

Corruption ảnh hưởng rõ nhất đến pipeline là việc làm mất ground-truth document khỏi index. Bằng chứng trực tiếp là `retrieval_hit_rate` giảm 0.333, từ 1.000 xuống 0.667. Khi document mục tiêu không còn trong index, semantic retrieval không thể trả về đúng document cho một số query, kéo theo chất lượng answer giảm (`mean_token_f1` giảm 0.051, `judge_accuracy` giảm 0.250 và `mean_judge_score` giảm 0.833).

Ngoài tác động lên metric của agent, corruption còn làm Quality chuyển từ PASS sang FAIL với 4 checks fail và Freshness chuyển từ Fresh sang Stale với 1 stale row. Điều này cho thấy corruption có thể được phát hiện đồng thời qua cả metric của agent và data observability signals.

### Kết quả nào khác với kỳ vọng ban đầu?

Kết quả nhìn chung phù hợp với kỳ vọng: khi dữ liệu bị corruption thì retrieval và chất lượng answer giảm, còn khi rebuild từ raw snapshot thì các metric phục hồi. Một điểm đáng chú ý là `mean_token_f1` sau repair đạt 0.215, cao hơn baseline 0.214 một lượng rất nhỏ, thay vì bằng đúng baseline. Tuy nhiên, mức chênh lệch chỉ 0.001 và không làm thay đổi kết luận chung rằng repair đã phục hồi thành công pipeline.

Đồng thời, Quality và Freshness đều chuyển trở lại PASS/Fresh sau repair, phù hợp với tiêu chí repair thành công đã đặt ra: cả metric của agent và các tín hiệu data quality/observability đều phải đồng thuận.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw artifact phải giữ nguyên trạng thái thô (kể cả phần "xấu" như tag XML) để các bước sau có thể tự quyết định cách xử lý, và để có thể repair lại từ đầu khi cần — không nên làm sạch quá sớm ở bước ingestion.
2. Dữ liệu thật từ nguồn ngoài (Crossref) luôn có nhiễu tồn tại sẵn (ví dụ `categories` rỗng ở phần lớn bản ghi, một số abstract có lỗi ngữ pháp gốc từ tác giả) — cần phân biệt rõ đây là đặc điểm nguồn dữ liệu, không phải lỗi do corruption cố ý ở Pha 2, nếu không sẽ gây nhiễu khi phân tích kết quả.
3. Không nên tự đoán cấu hình/interface của phần code người khác viết (ví dụ `Settings`) — nên dùng đúng factory function có sẵn, kiểm tra bằng test thật càng sớm càng tốt để tránh tích hợp lỗi vào phút cuối.

### Nếu có thêm thời gian

Thêm tham số `mailto` vào request Crossref (theo khuyến nghị "polite pool" của Crossref) để được ưu tiên rate limit tốt hơn, giảm khả năng gặp lỗi 429 khi cả nhóm cùng chạy pipeline nhiều lần trong thời gian ngắn — đo bằng cách so sánh số lần bị 429 trước/sau khi thêm.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Lường Thị Hảo]
**Ngày xác nhận:** [2026-08-06]