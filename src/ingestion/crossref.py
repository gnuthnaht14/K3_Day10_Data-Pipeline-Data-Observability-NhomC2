# _request_with_retry: retry với backoff mũ (1.5^attempt), 
#     ưu tiên đọc header Retry-After nếu Crossref trả về, xử lý cả 429/503 lẫn lỗi network tạm thời.
# parse_crossref_payload: chỉ lọc thô — giữ lại record khi có đủ DOI + title + abstract,
#     KHÔNG bóc tag XML (<jats:p> vẫn còn nguyên trong summary) vì đó là việc của cleaning.py.
# fetch_source_records: lưu đúng 2 dạng raw artifact như yêu cầu — crossref_response.json
#     (response HTTP gốc, chưa qua parse) và crossref_records.json (đã parse thành PaperRecord phẳng,
#                                                          dùng để repair sau này ở Pha 2).
# _extract_updated: Crossref không có field updated như arXiv, nên dùng
#     indexed/deposited/created timestamp thay thế — cần lưu ý điểm này khi giải thích với nhóm.
from __future__ import annotations

 
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
 
import requests
 
from core.config import Settings
 
CROSSREF_URL = "https://api.crossref.org/works"
 
# HTTP status codes coi la tam thoi (retry-able)
RETRYABLE_STATUS_CODES = {429, 503}
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 30

@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str

def _format_authors(author_list: list[dict] | None) -> list[str]:
    """Crossref tra author dang list[{"given": ..., "family": ...}] (co the co "name" cho org)."""
    authors: list[str] = []
    for a in author_list or []:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if given or family:
            authors.append(f"{given} {family}".strip())
        elif a.get("name"):
            authors.append(str(a["name"]).strip())
    return authors
 
 
def _date_parts_to_str(date_field: dict | None) -> str:
    """Crossref tra date dang {"date-parts": [[year, month, day]]}, month/day co the thieu."""
    if not date_field:
        return ""
    parts_list = date_field.get("date-parts")
    if not parts_list or not parts_list[0]:
        return ""
    parts = list(parts_list[0]) + [1, 1]
    year, month, day = parts[0], parts[1], parts[2]
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except (TypeError, ValueError):
        return str(year) if year else ""
 
 
def _extract_published(item: dict) -> str:
    """Uu tien published-print > published-online > published > issued."""
    for key in ("published-print", "published-online", "published", "issued"):
        date_str = _date_parts_to_str(item.get(key))
        if date_str:
            return date_str
    return ""
 
 
def _extract_updated(item: dict) -> str:
    """Crossref khong co field 'updated' truc tiep, dung indexed/deposited date-time."""
    for key in ("indexed", "deposited", "created"):
        date_time = item.get(key, {}).get("date-time")
        if date_time:
            return date_time
    return ""
 
 
def _extract_pdf_url(item: dict) -> str:
    for link in item.get("link", []) or []:
        if link.get("content-type") == "application/pdf":
            return link.get("URL", "")
    return ""
 

def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """TODO(student): parse Crossref payload thanh list PaperRecord.

    Pseudo-code:
    1. Duyet `payload["message"]["items"]`.
    2. Lay DOI, title, abstract, authors, subject, dates, URLs.
    3. Chuan hoa text va bo record khong hop le.
    4. Tra ve list `PaperRecord`.
    """
    items = payload.get("message", {}).get("items", [])
    records: list[PaperRecord] = []
 
    for item in items:
        paper_id = item.get("DOI", "").strip()
        title_list = item.get("title") or []
        title = title_list[0].strip() if title_list and title_list[0] else ""
        summary = (item.get("abstract") or "").strip()
        if not paper_id or not title or not summary:
            continue
 
        authors = _format_authors(item.get("author"))
        categories = [c.strip() for c in (item.get("subject") or []) if c and c.strip()]
        primary_category = categories[0] if categories else ""
        published = _extract_published(item)
        updated = _extract_updated(item)
        abs_url = item.get("URL", "")
        pdf_url = _extract_pdf_url(item)
        container_titles = item.get("container-title") or []
        comment = container_titles[0].strip() if container_titles and container_titles[0] else ""
 
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )
 
    return records



def _request_with_retry(url: str, params: dict) -> dict:
    """Goi GET voi retry/backoff cho 429/503 va loi network tam thoi."""
    last_exc: Exception | None = None
 
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(BACKOFF_BASE_SECONDS ** attempt)
            continue
 
        if response.status_code in RETRYABLE_STATUS_CODES:
            # Uu tien header Retry-After neu Crossref co tra ve
            retry_after = response.headers.get("Retry-After")
            wait_seconds = float(retry_after) if retry_after else BACKOFF_BASE_SECONDS ** attempt
            time.sleep(wait_seconds)
            continue
 
        response.raise_for_status()
        return response.json()
 
    raise RuntimeError(
        f"Crossref request that bai sau {MAX_RETRIES} lan retry (url={url}, params={params})"
    ) from last_exc
 
    


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """TODO(student): goi source API, luu raw response, parse thanh records.

    Pseudo-code:
    1. Tao params tu `settings.source_query`, `settings.source_filter`, `settings.max_results`.
    2. Goi API voi retry cho cac status code nhu 429/503.
    3. Luu raw response vao `settings.paths.raw_api_response`.
    4. Parse payload bang `parse_crossref_payload`.
    5. Luu records vao `settings.paths.raw_records_json`.
    """
    query = getattr(settings, "source_query", "machine learning")
    source_filter = getattr(settings, "source_filter", None)
    max_results = getattr(settings, "max_results", 50)
 
    params: dict = {"query": query, "rows": max_results}
    if source_filter:
        params["filter"] = source_filter
 
    payload = _request_with_retry(CROSSREF_URL, params)
 
    # 1. Luu raw response nguyen ban de audit nguon
    raw_response_path = Path(
        getattr(settings.paths, "raw_api_response", "data/raw/crossref_response.json")
    )
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
 
    # 2. Parse thanh PaperRecord
    records = parse_crossref_payload(payload)
 
    # 3. Luu records da parse (dang flat) de co the load lai / repair sau nay
    raw_records_path = Path(
        getattr(settings.paths, "raw_records_json", "data/raw/crossref_records.json")
    )
    raw_records_path.parent.mkdir(parents=True, exist_ok=True)
    raw_records_path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
 
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """TODO(student): doc JSON snapshot va map thanh `PaperRecord`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [PaperRecord(**item) for item in data]
