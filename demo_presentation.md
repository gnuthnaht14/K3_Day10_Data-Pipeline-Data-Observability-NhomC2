# Kịch bản thuyết trình và demo

## Chủ đề

**Data Pipeline, Data Observability và tác động của dữ liệu xấu đến RAG**

## Thành viên và phạm vi trình bày

| Thành viên | Phụ trách | Nội dung demo |
|---|---|---|
| **Lường Thị Hảo** | Source ingestion — `crossref.py` | Crossref, raw snapshot và Raw Schema |
| **Lê Thị Linh** | Data model/evaluation — `cleaning.py`, `testset.py` | Cleaning, Clean Schema và frozen evaluation set |
| **Mai Hồng Sơn** | Data observability — `quality.py`, `reporting.py` | Quality checks, freshness và report |
| **Nhữ Trọng Thành** | Corruption/integration — `corruption.py`, `phase1.py`, `corruption_flow.py` | Baseline, corruption, repair và so sánh |

---

## 1. Mục tiêu demo

Sau phần demo, người xem cần thấy được:

1. Dữ liệu được lấy và xử lý như thế nào trước khi đưa vào RAG.
2. Baseline trên dữ liệu sạch có chất lượng ra sao.
3. Dữ liệu xấu làm quality checks và RAG metrics thay đổi như thế nào.
4. Pipeline phục hồi dữ liệu xấu từ raw snapshot ra sao.

---

## 2. Chuẩn bị trước khi demo

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run streamlit run streamlit_app.py
```

Mở `http://localhost:8501`.

Artifact nên mở sẵn:

- `data/reports/phase1_report.md`
- `data/reports/corruption_report.md`
- `data/results/corruption_log.json`

---

## 3. Luồng xử lý tổng thể

```text
Crossref API/raw snapshot
        ↓
Parse Raw Schema
        ↓
Cleaning → Clean Schema
        ↓
Quality + Freshness checks
        ↓
ChromaDB vector index
        ↓
Frozen test set + RAG agent evaluation
        ↓
Baseline metrics
        ↓
Controlled corruption
        ↓
Corrupted metrics và quality FAIL
        ↓
Repair từ raw snapshot
        ↓
Re-index + re-evaluate
        ↓
Repaired metrics
```

---

## 4. Thành viên 1 — Lường Thị Hảo

### Phần cần trình bày

`crossref.py` thực hiện:

- Gọi Crossref REST API với query và filter cấu hình.
- Parse response thành danh sách `PaperRecord`.
- Chuẩn hóa DOI, title, abstract, authors, categories và ngày xuất bản.
- Lưu raw API response và raw record snapshot.
- Retry khi gặp lỗi tạm thời như `429`, `500`, `502`, `503`, `504`.

### Artifact cần show

```text
data/raw/crossref_response.json
data/raw/crossref_records.json
```

### Điểm cần nhấn mạnh

Raw snapshot là đầu vào cố định cho cleaning, evaluation và repair. Nếu Crossref không trả `subject/category`, đó có thể là thiếu metadata từ nguồn chứ không phải lỗi parser.

**Câu chuyển tiếp:** “Sau Raw Schema, chúng ta chuẩn hóa thành Clean Schema để index và đánh giá.”

---

## 5. Thành viên 2 — Lê Thị Linh

### Phần cần trình bày

`cleaning.py`:

- Giữ `paper_id` unique và non-null.
- Chuẩn hóa title, summary, authors và categories.
- Tính `age_days`.
- Tạo `text_for_embedding`.
- Xuất Clean Schema CSV/JSON.

Clean Schema:

```text
paper_id, title, summary, published,
authors_joined, categories_joined, age_days,
text_for_embedding, abs_url, pdf_url
```

`testset.py` tạo frozen evaluation set:

```text
id, question_type, question,
ground_truth, ground_truth_doc_ids
```

### Artifact cần show

```text
data/clean/papers_clean.csv
data/clean/papers_clean.json
data/eval/test_set.json
```

### Điểm cần nhấn mạnh

Frozen test set được tạo một lần và dùng lại cho Baseline, Corrupted và Repaired. Nhờ vậy ba trạng thái được so sánh trên cùng câu hỏi và ground truth.

**Câu chuyển tiếp:** “Dữ liệu sạch và test set đã cố định; tiếp theo là kiểm tra dữ liệu có đủ tin cậy hay chưa.”

---

## 6. Thành viên 3 — Mai Hồng Sơn

### Phần cần trình bày

`quality.py` kiểm tra:

- Row count và required schema.
- `paper_id` non-null, unique và duplicate rows.
- Title, summary và `text_for_embedding`.
- `age_days` hợp lệ và stale rows.

Freshness report phân biệt:

```text
fresh   — dữ liệu hợp lệ và không stale
stale   — có bản ghi quá cũ
invalid — published date không parse được
empty   — dataset rỗng
```

### Artifact cần show

```text
data/quality/baseline.json
data/quality/corrupted.json
data/quality/repaired.json
data/quality/freshness_report.json
data/quality/freshness_corrupted.json
data/quality/freshness_repaired.json
```

### Hai câu hỏi cần giải thích

**`retrieval_hit_rate` đo cái gì?**

Nó đo khả năng semantic retriever đưa tài liệu chứa ground truth vào top-k. Metric này đánh giá retriever/index, chưa đánh giá đầy đủ câu trả lời cuối.

**Vì sao Token F1 không luôn bằng 1 dù retrieve đúng?**

Retrieval đúng chỉ có nghĩa là lấy được tài liệu liên quan. Agent có thể tóm tắt, diễn đạt lại hoặc chỉ dùng một phần ground truth. Token F1 đo lexical overlap, không đo hoàn toàn semantic equivalence.

**Câu chuyển tiếp:** “Baseline đã có số liệu làm mốc; bây giờ chúng ta tạo dữ liệu xấu để đo tác động lên RAG.”

---

## 7. Thành viên 4 — Nhữ Trọng Thành

### 7.1. Baseline pipeline

File chính: `src/pipelines/phase1.py`.

Luồng baseline:

1. Đọc raw snapshot hoặc fetch Crossref nếu chưa có.
2. Chạy cleaning.
3. Build ChromaDB index.
4. Dùng frozen test set.
5. Gọi LangChain tool-calling agent.
6. Tính retrieval hit, Token F1 và judge metrics.
7. Chạy quality/freshness checks.
8. Xuất `phase1_report.md` và metrics artifacts.

Baseline hiện tại:

| Metric | Giá trị |
|---|---:|
| Records | 24 |
| Quality | PASS 10/10 |
| Freshness | Fresh |
| Retrieval hit rate | 1.000 |
| Mean Token F1 | 0.214 |
| Judge accuracy | 0.500 |

### 7.2. Controlled corruption

File chính: `src/ingestion/corruption.py`.

Các scenario:

- `drop_eval_record`: xóa tài liệu thuộc frozen test set.
- `blank_summary`: làm rỗng summary.
- `inject_embedding_noise`: chèn nội dung không liên quan vào text được index.
- `make_published_date_stale`: đổi published date về `2000-01-01`.
- `add_duplicate_rows`: nhân đôi bản ghi và giữ nguyên ID.

Artifact cần show:

```text
data/clean/papers_corrupted.csv
data/results/corruption_log.json
```

Các scenario đều overlap với tài liệu trong frozen evaluation set nên tác động được quan sát bằng RAG metrics.

### 7.3. So sánh ba trạng thái

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Retrieval hit rate | 1.000 | 0.667 | 1.000 |
| Mean Token F1 | 0.214 | 0.163 | 0.215 |
| Judge accuracy | 0.500 | 0.250 | 0.500 |
| Data quality | PASS | FAIL | PASS |
| Freshness | Fresh | Stale | Fresh |

Corrupted fail ở 4 checks:

```text
paper_id_unique
duplicate_rows
summary_min_length
stale_rows
```

### Scenario nghiêm trọng nhất

`drop_eval_record` gây ảnh hưởng retrieval lớn nhất:

- Xóa ground-truth document `10.1111/exsy.70341`.
- Ảnh hưởng bốn câu hỏi của paper đó.
- Retrieval hit giảm `-0.333` trong ablation.
- Token F1 giảm khoảng `-0.195` trong ablation deterministic.

### 7.4. Phương án repair

File chính: `src/pipelines/corruption_flow.py`.

```text
data/raw/crossref_records.json
        ↓
Chạy lại cleaning chuẩn
        ↓
Validate Clean Schema
        ↓
Build repaired ChromaDB index
        ↓
Evaluate trên frozen test set
```

Repair không sửa trực tiếp file corrupted và không fetch API lại. Crossref có thể thay đổi metadata, thứ tự kết quả hoặc danh sách record; raw snapshot giúp cô lập tác động của corruption và giữ thí nghiệm tái lập.

---

## 8. Kịch bản thao tác trên dashboard

Mở:

```bash
uv run streamlit run streamlit_app.py
```

### Bước 1 — Baseline

1. Chọn `Baseline` ở sidebar.
2. Chỉ ra flow Raw snapshot → Cleaning → Quality → ChromaDB → Evaluation.
3. Show 24 records, quality PASS và freshness Fresh.
4. Chọn từng metric trên biểu đồ.

### Bước 2 — Dữ liệu xấu

1. Chọn `Corrupted`.
2. Chỉ ra retrieval hit giảm còn 66,7%.
3. Chỉ ra Token F1 và judge accuracy giảm.
4. Show quality FAIL với 4 checks.
5. Show freshness STALE và corruption log.

### Bước 3 — Repair

1. Chọn `Repaired`.
2. Chỉ ra quality PASS và freshness Fresh.
3. Chỉ ra retrieval hit phục hồi về 100%.
4. Giải thích repair bắt đầu từ raw snapshot, không fetch API lại.

---

## 9. Kết luận chung

> Dữ liệu sạch là điều kiện đầu vào của RAG, nhưng quality checks mới cho biết dữ liệu có đủ tin cậy hay không. Controlled corruption chứng minh lỗi dữ liệu làm giảm retrieval và answer quality. Repair từ raw snapshot giúp khôi phục pipeline một cách tái lập và kiểm chứng được.

## 10. Câu hỏi có thể được hỏi

### Vì sao quality PASS nhưng Judge accuracy chỉ 50%?

Quality checks đo tính hợp lệ của dữ liệu, không đo khả năng trả lời đúng mọi câu hỏi. RAG có thể nhận dữ liệu sạch nhưng agent vẫn tóm tắt thiếu hoặc diễn đạt khác ground truth.

### Vì sao corrupted rows vẫn là 24?

Một record bị xóa nhưng một record khác được nhân đôi. Số lượng không đổi, nhưng uniqueness và nội dung dữ liệu đã bị phá vỡ.

### Vì sao repaired Token F1 là 0.215 thay vì đúng 0.214?

Agent/LLM có thể tạo câu trả lời hơi khác giữa các lần gọi. Retrieval và quality đã phục hồi; answer metrics cần được đọc cùng provenance trong report.

### Nếu Crossref thiếu categories thì có phải pipeline lỗi không?

Không nhất thiết. Đây có thể là metadata không được Crossref cung cấp. Pipeline cần giữ giá trị thiếu minh bạch và phân biệt thiếu metadata nguồn với lỗi schema.
