import pytest

from core.sql_guard import SQLGuardError, validate_sql

T = ["sales", "customers"]


@pytest.mark.parametrize("sql", [
    "SELECT region, SUM(revenue) FROM sales GROUP BY 1",
    "WITH a AS (SELECT * FROM sales) SELECT * FROM a",
    "SELECT s.region FROM sales s JOIN customers c ON s.customer_id = c.customer_id;",
    "select 'drop table x' as note from sales",
    "SELECT date_trunc('month', order_date) m FROM sales -- trailing comment",
])
def test_allowed(sql):
    assert validate_sql(sql, T)


@pytest.mark.parametrize("sql", [
    "DROP TABLE sales", "DELETE FROM sales", "SELECT 1; DROP TABLE sales",
    "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM secrets", "",
    "COPY sales TO 'x.csv'", "ATTACH 'x.db'", "PRAGMA database_list",
    "/* hi */ INSERT INTO sales VALUES (1)", "SELECT getenv('HOME')",
])
def test_blocked(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql, T)
