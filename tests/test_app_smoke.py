from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


def test_app_boots_and_loads_sample():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    # Load both bundled datasets.
    next(b for b in at.sidebar.button if "sample" in b.label.lower()).click()
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 5
    assert at.session_state["tallymark_ov_dataset"] == "sales"
    compact_anomalies = next(
        frame.value
        for frame in at.dataframe
        if list(frame.value.columns) == ["row_number", "order_id", "severity", "why_flagged"]
    )
    assert compact_anomalies["why_flagged"].str.len().gt(0).all()


def _loaded_app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    next(b for b in at.sidebar.button if "sample" in b.label.lower()).click()
    return at.run()


def test_chat_anomaly_offline(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    at = _loaded_app()
    at.chat_input[0].set_value("Detect anomalies in the dataset").run()
    assert not at.exception, at.exception
    ans = at.session_state["history"][-1]
    assert ans.anomalies is not None and ans.anomalies.n_flagged > 0


def test_chat_query_with_fake_llm(monkeypatch):
    import core.llm as llm_mod

    class Fake:
        available = True

        def __init__(self, *a, **k):
            pass

        def json(self, system, user):
            if "explanation layer" in system:
                return {"answer": "Done.", "insight": "ok", "follow_ups": ["next?"]}
            return {"intent": "query", "sql": "SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY 1 ORDER BY 2 DESC",
                    "chart": {"type": "bar", "x": "region", "y": "revenue"}, "reasoning": "r", "assumptions": []}

    monkeypatch.setattr(llm_mod, "GroqLLM", Fake)
    at = _loaded_app()
    at.chat_input[0].set_value("Which region generated the highest revenue?").run()
    assert not at.exception, at.exception
    assert at.session_state["history"][-1].figure is not None
