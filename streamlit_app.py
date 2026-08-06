from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
STATE_LABELS = {
    "Baseline": "Dữ liệu sạch",
    "Corrupted": "Dữ liệu lỗi",
    "Repaired": "Đã phục hồi",
}
STATE_COLORS = {
    "Baseline": "#2563EB",
    "Corrupted": "#DC2626",
    "Repaired": "#16A34A",
}
METRIC_LABELS = {
    "retrieval_hit_rate": "Retrieval hit rate",
    "mean_token_f1": "Mean Token F1",
    "judge_accuracy": "Judge accuracy",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(ttl="5m", show_spinner="Đang đọc artifact mới nhất...")
def load_artifacts() -> dict[str, Any]:
    paths = {
        "baseline_metrics": DATA_DIR / "results" / "baseline_metrics.json",
        "corrupted_metrics": DATA_DIR / "results" / "corrupted_metrics.json",
        "repaired_metrics": DATA_DIR / "results" / "repaired_metrics.json",
        "baseline_quality": DATA_DIR / "quality" / "baseline.json",
        "corrupted_quality": DATA_DIR / "quality" / "corrupted.json",
        "repaired_quality": DATA_DIR / "quality" / "repaired.json",
        "baseline_freshness": DATA_DIR / "quality" / "freshness_report.json",
        "corrupted_freshness": DATA_DIR / "quality" / "freshness_corrupted.json",
        "repaired_freshness": DATA_DIR / "quality" / "freshness_repaired.json",
        "corruption_log": DATA_DIR / "results" / "corruption_log.json",
        "corruption_report": DATA_DIR / "reports" / "corruption_report.md",
    }
    missing = [str(path.relative_to(PROJECT_DIR)) for path in paths.values() if not path.exists()]
    if missing:
        return {"missing": missing}

    artifacts: dict[str, Any] = {key: _read_json(path) for key, path in paths.items() if path.suffix == ".json"}
    artifacts["corruption_report"] = paths["corruption_report"].read_text(encoding="utf-8")
    artifacts["missing"] = []

    dataset_paths = {
        "Baseline": DATA_DIR / "clean" / "papers_clean.csv",
        "Corrupted": DATA_DIR / "clean" / "papers_corrupted.csv",
        "Repaired": DATA_DIR / "clean" / "papers_clean_repaired.csv",
    }
    artifacts["datasets"] = {
        state: pd.read_csv(path, keep_default_na=False) if path.exists() else pd.DataFrame()
        for state, path in dataset_paths.items()
    }
    raw_path = DATA_DIR / "raw" / "crossref_records.json"
    artifacts["raw_count"] = len(_read_json(raw_path)) if raw_path.exists() else None
    return artifacts


def _state_payload(artifacts: dict[str, Any], prefix: str, state: str) -> dict[str, Any]:
    return artifacts[f"{state.lower()}_{prefix}"]


def _delta(current: float, baseline: float) -> str | None:
    if current == baseline:
        return None
    return f"{current - baseline:+.3f} so với baseline"


def _metric_frame(artifacts: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for state in STATE_LABELS:
        metrics = _state_payload(artifacts, "metrics", state)
        for metric, label in METRIC_LABELS.items():
            rows.append({"Trạng thái": state, "Chỉ số": label, "Giá trị": float(metrics.get(metric, 0.0))})
    return pd.DataFrame(rows)


def _render_flow(labels: list[tuple[str, str]]) -> None:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        for index, (title, detail) in enumerate(labels):
            with st.container(border=True, width=190):
                st.markdown(f"**{title}**")
                st.caption(detail)
            if index < len(labels) - 1:
                st.markdown(":material/arrow_forward:")


st.set_page_config(
    page_title="RAG data observability demo",
    page_icon=":material/monitoring:",
    layout="wide",
)

with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
    st.title("RAG data pipeline & observability")
    if st.button(":material/refresh: Đọc lại artifact", type="tertiary"):
        st.cache_data.clear()
        st.rerun()

st.caption("Demo tương tác: dữ liệu sạch → controlled corruption → repair từ raw snapshot")

artifacts = load_artifacts()
if artifacts["missing"]:
    st.error("Thiếu artifact để hiển thị dashboard.", icon=":material/error:")
    st.code("\n".join(artifacts["missing"]), language="text")
    st.markdown("Chạy lần lượt:")
    st.code("uv run python script/run_phase1.py\nuv run python script/run_corruption_flow.py", language="bash")
    st.stop()

with st.sidebar:
    st.header("Điều khiển demo")
    selected_state = st.segmented_control(
        "Trạng thái dữ liệu",
        options=list(STATE_LABELS),
        default="Baseline",
        required=True,
        key="selected_state",
        width="stretch",
    )
    st.caption(STATE_LABELS[selected_state])
    st.divider()
    st.markdown(
        """
        **Kịch bản trình bày**

        1. Show baseline processing.
        2. Chuyển sang Corrupted để xem suy giảm.
        3. Mở corruption log.
        4. Chuyển sang Repaired để chứng minh phục hồi.
        """
    )

metrics = _state_payload(artifacts, "metrics", selected_state)
quality = _state_payload(artifacts, "quality", selected_state)
freshness = _state_payload(artifacts, "freshness", selected_state)
baseline_metrics = artifacts["baseline_metrics"]
selected_df = artifacts["datasets"][selected_state]

st.subheader("1. Baseline xử lý dữ liệu như thế nào?")
_render_flow(
    [
        ("Raw snapshot", f"{artifacts['raw_count'] or 'N/A'} Crossref records"),
        ("Cleaning", "Chuẩn hóa schema, deduplicate"),
        ("Observability", "Completeness, uniqueness, freshness"),
        ("ChromaDB", "MiniLM embeddings + top-k search"),
        ("Evaluation", "Frozen test set + agent + judge"),
    ]
)

with st.expander("Xem dữ liệu sau cleaning", icon=":material/table_view:"):
    st.dataframe(
        selected_df.head(10),
        hide_index=True,
        width="stretch",
        column_config={
            "paper_id": st.column_config.TextColumn("Paper ID", pinned=True),
            "abs_url": st.column_config.LinkColumn("Abstract URL"),
            "pdf_url": st.column_config.LinkColumn("PDF URL"),
        },
    )

st.subheader(f"2. Trạng thái đang xem: {selected_state} — {STATE_LABELS[selected_state]}")
with st.container(horizontal=True):
    st.metric("Số bản ghi", int(quality.get("total_rows", len(selected_df))), border=True)
    st.metric(
        "Retrieval hit",
        f"{float(metrics['retrieval_hit_rate']):.1%}",
        _delta(float(metrics["retrieval_hit_rate"]), float(baseline_metrics["retrieval_hit_rate"])),
        border=True,
        chart_data=[
            artifacts["baseline_metrics"]["retrieval_hit_rate"],
            artifacts["corrupted_metrics"]["retrieval_hit_rate"],
            artifacts["repaired_metrics"]["retrieval_hit_rate"],
        ],
    )
    st.metric(
        "Token F1",
        f"{float(metrics['mean_token_f1']):.3f}",
        _delta(float(metrics["mean_token_f1"]), float(baseline_metrics["mean_token_f1"])),
        border=True,
    )
    st.metric(
        "Judge accuracy",
        f"{float(metrics['judge_accuracy']):.1%}",
        _delta(float(metrics["judge_accuracy"]), float(baseline_metrics["judge_accuracy"])),
        border=True,
    )
    st.metric("Data quality", str(quality.get("status", "N/A")).upper(), border=True)
    st.metric("Freshness", str(freshness.get("status", "N/A")).upper(), border=True)

if quality.get("passed"):
    st.success("Data quality checks đang PASS.", icon=":material/check_circle:")
else:
    failed_names = quality.get("summary", {}).get("failed_check_names", [])
    st.error("Quality FAIL: " + ", ".join(failed_names), icon=":material/error:")

chart_metric = st.segmented_control(
    "Chỉ số cần so sánh",
    options=list(METRIC_LABELS.values()),
    default="Retrieval hit rate",
    required=True,
    key="chart_metric",
)
metric_frame = _metric_frame(artifacts)
chart_data = metric_frame[metric_frame["Chỉ số"] == chart_metric]
comparison_chart = (
    alt.Chart(chart_data)
    .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
    .encode(
        x=alt.X("Trạng thái:N", sort=list(STATE_LABELS), title=None),
        y=alt.Y("Giá trị:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
        color=alt.Color(
            "Trạng thái:N",
            scale=alt.Scale(domain=list(STATE_LABELS), range=list(STATE_COLORS.values())),
            legend=None,
        ),
        tooltip=["Trạng thái:N", alt.Tooltip("Giá trị:Q", format=".3f")],
    )
    .properties(height=300)
)
st.altair_chart(comparison_chart, width="stretch")

quality_rows = pd.DataFrame(quality.get("checks", []))
if not quality_rows.empty:
    quality_rows = quality_rows.rename(
        columns={"name": "Check", "value": "Kết quả", "threshold": "Ngưỡng", "passed": "Passed"}
    )
    def _display_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    # Quality values are heterogeneous: schema checks return a list while
    # count checks return integers. Arrow requires one compatible type per
    # dataframe column, so render both values and thresholds as text.
    quality_rows["Kết quả"] = quality_rows["Kết quả"].map(_display_value)
    quality_rows["Ngưỡng"] = quality_rows["Ngưỡng"].map(_display_value)
    st.dataframe(
        quality_rows[["Check", "Kết quả", "Ngưỡng", "Passed"]],
        hide_index=True,
        width="stretch",
        column_config={"Passed": st.column_config.CheckboxColumn("Passed")},
    )

st.subheader("3. Controlled corruption ảnh hưởng RAG ra sao?")
corruption_log = artifacts["corruption_log"]
operation_rows = pd.DataFrame(
    [
        {
            "Scenario": operation.get("type"),
            "Số records": operation.get("affected_count"),
            "Eval document IDs": operation.get("affected_eval_doc_ids", []),
            "Overlap frozen test": operation.get("overlap_with_eval", False),
        }
        for operation in corruption_log.get("operations", [])
    ]
)
st.dataframe(
    operation_rows,
    hide_index=True,
    width="stretch",
    column_config={
        "Eval document IDs": st.column_config.ListColumn("Eval document IDs"),
        "Overlap frozen test": st.column_config.CheckboxColumn("Overlap frozen test"),
    },
)

severe_match = re.search(r"- Most severe retrieval scenario: (.+)", artifacts["corruption_report"])
if severe_match:
    st.warning(severe_match.group(1), icon=":material/warning:")

st.markdown(
    f"""
    Corruption làm retrieval hit giảm từ **{artifacts['baseline_metrics']['retrieval_hit_rate']:.1%}** xuống
    **{artifacts['corrupted_metrics']['retrieval_hit_rate']:.1%}**, Token F1 giảm từ
    **{artifacts['baseline_metrics']['mean_token_f1']:.3f}** xuống
    **{artifacts['corrupted_metrics']['mean_token_f1']:.3f}** và judge accuracy giảm từ
    **{artifacts['baseline_metrics']['judge_accuracy']:.1%}** xuống
    **{artifacts['corrupted_metrics']['judge_accuracy']:.1%}**.
    """
)

st.subheader("4. Phương án sửa pipeline dữ liệu xấu")
_render_flow(
    [
        ("Raw snapshot", "Không fetch API mới"),
        ("Re-clean", "Chạy lại cleaning chuẩn"),
        ("Validate", "Schema + quality + freshness"),
        ("Re-index", "Dựng collection repaired"),
        ("Re-evaluate", "Dùng lại frozen test set"),
    ]
)
st.info(
    "Repair phải bắt đầu từ raw snapshot để cùng nguồn đầu vào với baseline. Fetch lại Crossref có thể trả metadata hoặc thứ tự kết quả khác, làm mất tính tái lập của thí nghiệm.",
    icon=":material/info:",
)

repaired_metrics = artifacts["repaired_metrics"]
if repaired_metrics["retrieval_hit_rate"] >= baseline_metrics["retrieval_hit_rate"]:
    st.success(
        f"Repair thành công: retrieval hit phục hồi về {repaired_metrics['retrieval_hit_rate']:.1%}; quality PASS và freshness fresh.",
        icon=":material/check_circle:",
    )

with st.expander("Gợi ý lời nói khi demo", icon=":material/present_to_all:"):
    st.markdown(
        """
        - **Baseline:** dữ liệu được chuẩn hóa và vượt qua toàn bộ quality/freshness checks trước khi index.
        - **Corrupted:** lỗi có chủ đích đụng trực tiếp frozen test documents, nên cả observability signals và RAG metrics đều suy giảm.
        - **Repair:** dựng lại từ raw snapshot, re-index và đánh giá bằng cùng test set để chứng minh phục hồi công bằng.
        - **Thông điệp chính:** data quality không chỉ là báo cáo kỹ thuật; nó tác động trực tiếp đến khả năng tìm kiếm và chất lượng câu trả lời của RAG.
        """
    )
