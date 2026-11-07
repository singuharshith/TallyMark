import pytest

from core.executor import QueryError, QueryExecutor


def test_runs_aggregation(sales):
    r = QueryExecutor({"sales": sales}).run("SELECT region, SUM(revenue) AS rev FROM sales WHERE region IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
    expected = sales.groupby("region")["revenue"].sum().idxmax()
    assert r.df.iloc[0]["region"] == expected


def test_bad_column_raises_query_error(sales):
    with pytest.raises(QueryError):
        QueryExecutor({"sales": sales}).run("SELECT nope FROM sales")


def test_file_access_blocked_even_without_guard(sales):
    with pytest.raises(QueryError):
        QueryExecutor({"sales": sales}).run("SELECT * FROM read_csv('/etc/passwd')")
