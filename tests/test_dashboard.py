from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_from_current_artifacts():
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "RAG data pipeline & observability"
    assert len(app.metric) >= 6
