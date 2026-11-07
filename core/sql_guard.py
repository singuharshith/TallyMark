"""Validate LLM-generated SQL: a single read-only SELECT over known tables only."""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SQLGuardError(Exception):
    pass


FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|install|load|export|import|call|set|"
    r"truncate|grant|revoke|vacuum|checkpoint|replace\s+into|read_\w+|glob|parquet_scan|sniff_csv|duckdb_\w+|pragma_\w+|"
    r"httpfs|http_get|getenv|current_setting)\b",
    re.I,
)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _strip_literals(sql: str) -> str:
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return re.sub(r'"(?:[^"]|"")*"', '""', sql)


def validate_sql(sql: str | None, allowed_tables) -> str:
    """Return cleaned SQL or raise SQLGuardError with a message safe to show/feed back to the LLM."""
    if not sql or not str(sql).strip():
        raise SQLGuardError("No SQL was provided.")
    s = _strip_comments(str(sql)).strip().rstrip(";").strip()
    bare = _strip_literals(s)
    if ";" in bare:
        raise SQLGuardError("Only a single SQL statement is allowed.")
    if not re.match(r"^\s*(\(\s*)*(select|with)\b", bare, re.I):
        raise SQLGuardError("Only SELECT queries are allowed.")
    bad = FORBIDDEN.search(bare)
    if bad:
        raise SQLGuardError(f"The keyword/function '{bad.group(0)}' is not allowed (read-only SELECT queries only).")
    try:
        trees = sqlglot.parse(s, read="duckdb")
    except ParseError as exc:
        raise SQLGuardError(f"SQL could not be parsed: {str(exc)[:200]}")
    if len(trees) != 1 or trees[0] is None:
        raise SQLGuardError("Exactly one SQL statement is required.")
    tree = trees[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        raise SQLGuardError("Only SELECT queries are allowed.")
    allowed = {t.lower() for t in allowed_tables}
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = (t.name or "").lower()
        if not name:
            raise SQLGuardError("Table functions are not allowed.")
        if name not in allowed and name not in ctes:
            raise SQLGuardError(f"Unknown table '{t.name}'. Available tables: {', '.join(sorted(allowed))}.")
    return s
