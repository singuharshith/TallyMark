"""Pipeline tests with a scripted fake LLM (no network)."""
from core.agent import DataAnalyst


class FakeLLM:
    available = True

    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = []

    def json(self, system, user):
        self.calls.append((system, user))
        if "explanation layer" in system:
            first = user.split("rows total, showing up to 30):\n")[1].splitlines()[1].split(",")
            return {"answer": f"{first[0]} leads with {float(first[1]):,.0f} in revenue.", "insight": "Focus there.", "follow_ups": ["a", "b", "c"]}
        if "anomaly-detection" in system:
            return {"answer": "Flagged some rows.", "insight": "Check bulk orders.", "follow_ups": []}
        return self.plans.pop(0)


def plan(sql, **kw):
    return {"intent": "query", "sql": sql, "pandas": "result = sales.groupby('region').revenue.sum()",
            "chart": {"type": "bar", "x": "region", "y": "revenue", "title": "Revenue"}, "reasoning": "sum by region",
            "assumptions": [], **kw}


GOOD = "SELECT region, ROUND(SUM(revenue),2) AS revenue FROM sales WHERE region IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"


def test_happy_path(sales):
    a = DataAnalyst({"sales": sales}, FakeLLM([plan(GOOD)])).ask("Which region generated the highest revenue?")
    assert a.error is None and a.result.iloc[0]["region"] == sales.groupby("region")["revenue"].sum().idxmax()
    assert a.figure is not None and a.sql.startswith("SELECT") and "read_csv" in a.pandas_code
    assert a.follow_ups and a.grounding and a.grounding[0] == a.grounding[1] >= 1


def test_self_repair_after_bad_column(sales):
    llm = FakeLLM([plan("SELECT area, SUM(revenue) FROM sales GROUP BY 1"), plan(GOOD)])
    a = DataAnalyst({"sales": sales}, llm).ask("top region")
    assert a.attempts == 2 and a.error is None


def test_gives_up_gracefully(sales):
    bad = plan("DROP TABLE sales")
    a = DataAnalyst({"sales": sales}, FakeLLM([bad, bad, bad])).ask("x")
    assert a.error and "couldn't" in a.text and a.result is None


def test_context_carries_previous_sql(sales):
    llm = FakeLLM([plan(GOOD), plan(GOOD)])
    an = DataAnalyst({"sales": sales}, llm)
    first = an.ask("Which region generated the highest revenue?")
    an.ask("now break that down by month", [first])
    planner_user_prompt = llm.calls[-1][1] if "explanation layer" not in llm.calls[-1][0] else llm.calls[-2][1]
    assert GOOD in planner_user_prompt


def test_anomaly_intent_and_offline_mode(sales):
    a = DataAnalyst({"sales": sales}, FakeLLM([{"intent": "anomaly", "table": "sales"}])).ask("Detect anomalies in the dataset")
    assert a.anomalies and a.anomalies.n_flagged > 0 and a.figure is not None

    class NoKey(FakeLLM):
        available = False

    off = DataAnalyst({"sales": sales}, NoKey([])).ask("Detect anomalies in the dataset")
    assert off.anomalies is not None and off.error is None
    msg = DataAnalyst({"sales": sales}, NoKey([])).ask("Which region is best?")
    assert msg.error == "no_api_key"


def test_quality_intent(sales):
    a = DataAnalyst({"sales": sales}, FakeLLM([{"intent": "quality", "table": "sales"}])).ask("check data quality")
    assert "/100" in a.text and a.result is not None
