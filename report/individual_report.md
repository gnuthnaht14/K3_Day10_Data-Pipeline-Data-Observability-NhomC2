# Member Role Report — Lê Thị Linh

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                                            |
| --------------- | ----------------------------------------------------------------------------------- |
| Họ và tên       | Lê Thị Linh                                                                         |
| MSSV            | [2A202601441]                                                                       |
| Khóa/Lớp        | K3                                                                                  |
| Tên nhóm        | Nhóm C2                                                                             |
| Vai trò chính   | Cleaning và Evaluation Set Owner                                                    |
| Repository      | https://github.com/gnuthnaht14/K3_Day10_Data-Pipeline-Data-Observability-NhomC2.git |
| Ngày hoàn thành | 2026-08-06                                                                          |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable        | File/hàm phụ trách                                    | Input                            | Output bàn giao                                               | Trạng thái |
| ------------------------- | ----------------------------------------------------- | -------------------------------- | ------------------------------------------------------------- | ---------- |
| Data cleaning và modeling | `src/ingestion/cleaning.py` — `build_clean_dataframe` | `data/raw/crossref_records.json` | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` | Hoàn thành |
| Evaluation set            | `src/evaluation/testset.py` — `build_test_set`        | Clean dataframe                  | `data/eval/test_set.json`                                     | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động              | Thành viên/module được hỗ trợ                 | Kết quả                                                              |
| ---------------------- | --------------------------------------------- | -------------------------------------------------------------------- |
| Kiểm tra data contract | `retrieval/index.py`, `evaluation/metrics.py` | Xác nhận clean schema và `ground_truth_doc_ids` dùng đúng `paper_id` |

## 3. Kết quả theo vai trò

| Nhiệm vụ                     | File/hàm/artifact                                      | Kết quả bàn giao                      | Cách xác minh                                         |
| ---------------------------- | ------------------------------------------------------ | ------------------------------------- | ----------------------------------------------------- |
| Chuẩn hóa và lọc raw records | `src/ingestion/cleaning.py`                            | 24 clean records, đúng 10 cột         | Kiểm tra schema, missing, duplicate, HTML/XML và date |
| Tạo test set từ clean data   | `src/evaluation/testset.py`, `data/eval/test_set.json` | 10 câu hỏi với ground truth trực tiếp | Đối chiếu toàn bộ IDs với clean `paper_id`            |

Output cụ thể: `papers_clean.csv/json` có 24 record; `test_set.json` có 10 sample, không có evaluation document ID không tồn tại.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Raw Crossref có thể chứa HTML/XML, text không đồng nhất, missing values, duplicate, ngày sai format và danh sách authors/categories chưa phù hợp cho indexing. Evaluation set cần có câu hỏi thực tế và câu trả lời lấy trực tiếp từ clean data.

### Cách triển khai

- Loại HTML/XML, decode entities, chuẩn hóa Unicode NFC, bỏ control characters và collapse whitespace.
- Drop record thiếu `paper_id`, title, summary dưới 100 ký tự hoặc ngày `published` không hợp lệ.
- Nối authors/categories bằng dấu phẩy; missing optional values dùng `unknown`.
- Deduplicate theo `paper_id` và hash của `title + summary`.
- Chuẩn hóa `published` thành `YYYY-MM-DD` và tính `age_days = run_date - published`.
- Tạo `text_for_embedding` theo mẫu `Title: ... | Authors: ... | Summary: ...`.
- Tạo 10 câu hỏi từ 5 clean documents; dùng các loại `factual`, `authors`, `date`.

### Input, output và contract

| Thành phần            | Mô tả                                                                       |
| --------------------- | --------------------------------------------------------------------------- |
| Input                 | `data/raw/crossref_records.json`, clean dataframe                           |
| Output                | Clean schema 10 cột và evaluation schema 5 trường                           |
| Module phụ thuộc      | `src/ingestion/crossref.py`                                                 |
| Module sử dụng output | `src/retrieval/index.py`, `src/evaluation/metrics.py`                       |
| Điều kiện lỗi         | Missing bắt buộc, summary ngắn, date sai, duplicate, missing evaluation IDs |

### Cách xác minh

```bash
$env:PYTHONPATH="src"
\.venv\Scripts\python.exe -m compileall -q src/ingestion/cleaning.py src/evaluation/testset.py
```

- **Kết quả mong đợi:** Clean data hợp lệ và test set có 5–10 sample với IDs tồn tại.
- **Kết quả thực tế:** 24 clean records, 10 evaluation samples; các kiểm tra đều PASS.
- **Artifact/log:** `data/clean/`, `data/eval/test_set.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Một số record Crossref thiếu `categories` hoặc `pdf_url`.
- **Phương án 1:** Drop toàn bộ record thiếu field tùy chọn.
- **Phương án 2:** Giữ record và biểu diễn missingness bằng `unknown`.
- **Phương án đã chọn:** Phương án 2; dùng `primary_category` nếu có, nếu không dùng `unknown`.
- **Lý do:** Các field này không bắt buộc cho embedding/indexing; giữ record giúp không mất dữ liệu hợp lệ.
- **Bằng chứng:** 24 record vẫn được giữ, không còn chuỗi rỗng hoặc NULL ở clean output.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** `categories_joined` và `pdf_url` rỗng ở raw data mới; một số text có tag XML.
- **Nguyên nhân gốc:** Crossref không cung cấp `subject` hoặc PDF link cho mọi record; abstract chứa markup.
- **Cách xử lý:** HTML stripping, text normalization và explicit missing-value handling bằng `unknown`.
- **Cách xác minh:** Clean validation cho kết quả 24 rows, 0 NULL, 0 duplicate, 0 HTML/XML, category/PDF không rỗng.
- **Điều học được:** Không nên tự tạo metadata không có trong nguồn; cần phân biệt giá trị thiếu với giá trị thật.

## 7. Hiểu biết về luồng end-to-end

1. Crossref response được parse thành `PaperRecord`, cleaning tạo clean schema và `text_for_embedding`, sau đó index dùng embedding để lưu vào vector store.
2. Evaluation set lưu câu hỏi, `ground_truth` và `ground_truth_doc_ids`; evaluator dùng chúng để đo retrieval hit và answer quality.
3. Quality checks kiểm tra schema, completeness, uniqueness và validity; freshness tập trung vào ngày xuất bản và `age_days`.
4. Baseline, corrupted và repaired phải dùng cùng test set để metrics chỉ phản ánh thay đổi của dữ liệu/pipeline.
5. Repair thành công khi clean artifact hợp lệ, quality/freshness phục hồi và metric RAG cải thiện theo kỳ vọng.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal        | Baseline | Corrupted | Repaired | Nhận xét                                                     |
| -------------------- | -------: | --------: | -------: | ------------------------------------------------------------ |
| `retrieval_hit_rate` |    1.000 |     0.667 |    1.000 | Mất một ground-truth document làm retrieval giảm 33.3 điểm % |
| `mean_token_f1`      |    0.214 |     0.163 |    0.215 | Context thiếu/nhiễu làm lexical overlap giảm                 |
| `judge_accuracy`     |    0.500 |     0.250 |    0.500 | Answer quality giảm rồi phục hồi                             |
| `mean_judge_score`   |    3.000 |     2.167 |    3.000 | Repair phục hồi score về baseline                            |
| Quality checks       |     PASS |        [] |       [] | Clean data: 24 records, 0 duplicate, 0 NULL                  |
| Freshness            |     PASS |        [] |       [] | `published` và `age_days` hợp lệ                             |

### Kết luận từ số liệu

Phần corruption/repaired metrics chưa được chạy trong phạm vi ownership của báo cáo này nên chưa kết luận thay đổi retrieval hoặc judge metrics.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Data contract giúp các module dùng cùng schema và xử lý missing nhất quán.
2. Text normalization trước embedding ảnh hưởng trực tiếp đến semantic retrieval.
3. Evaluation set phải lấy ground truth từ clean data và được đóng băng trước khi đánh giá.

### Nếu có thêm thời gian

Bổ sung language detection, URL validation và freshness labels `fresh/stale`; đo thêm context precision, context recall và faithfulness.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end.
- [x] Kết luận về cleaning/test set có artifact để đối chiếu.
- [x] Không ghi kết quả evaluator/corruption chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Lê Thị Linh  
**Ngày xác nhận:** [2026-08-06]
