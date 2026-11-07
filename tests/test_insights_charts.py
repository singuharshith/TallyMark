import pandas as pd

from core.charts import auto_spec, build_figure
from core.grounding import check_grounding, extract_numbers
from core.insights import build_overview
from core.profiler import profile_table, schema_for_llm
from core.pandas_codegen import prepare_pandas
from core.report import build_html, build_markdown


def test_overview_finds_march_dip(sales):
    ov = build_overview(sales, "sales")
    assert ov.metric == "revenue" and ov.date_col == "order_date"
    assert ov.worst_month == "March 2024"
    assert any("region" in f for f in ov.facts)


def test_quality_and_schema(sales):
    p = profile_table(sales, "sales")
    assert p.duplicates >= 6 and p.quality["missing_cells"] >= 12
    s = schema_for_llm({"sales": sales})
    assert "TABLE sales" in s and "region" in s and "North" in s


def test_chart_spec_validation_and_fallback():
    df = pd.DataFrame({"region": ["A", "B", "C"], "rev": [3, 2, 1]})
    assert build_figure(df, {"type": "bar", "x": "region", "y": "rev"}) is not None
    assert build_figure(df, {"type": "bar", "x": "bogus", "y": "rev"}) is not None  # falls back to auto
    assert build_figure(df, {"type": "none"}) is None
    assert auto_spec(df)["type"] == "bar"
    assert build_figure(pd.DataFrame({"v": [1]}), None) is None


def test_grounding():
    df = pd.DataFrame({"region": ["West"], "revenue": [935800.0]})
    assert extract_numbers("West made 935.8K or $1,234.50") == [935800.0, 1234.5]
    m, t = check_grounding("West leads with 935.8K revenue, 999 orders", df)
    assert (m, t) == (1, 2)


def test_pandas_snippet():
    assert prepare_pandas("result = sales.groupby('region').revenue.sum()", {"sales": None}).count("read_csv") == 1
    assert prepare_pandas("result = = broken", {"sales": None}) is None


def test_grounding_handles_missing_values():
    df = pd.DataFrame({"region": ["West", None], "revenue": [10.0, None]})
    assert check_grounding("West made 10", df)[1] >= 0


def test_report_uses_tallymark_brand(sales):
    overview = build_overview(sales, "sales")
    markdown = build_markdown({"sales": overview}, {"sales": profile_table(sales).quality}, [])
    html = build_html(markdown, [])

    assert markdown.startswith("# Tallymark - Business Data Report")
    assert "<title>Tallymark Business Data Report</title>" in html
