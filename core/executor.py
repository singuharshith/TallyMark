"""Sandboxed DuckDB execution over in-memory DataFrames."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import duckdb
import pandas as pd

from .config import MAX_RESULT_ROWS, QUERY_TIMEOUT_S


class QueryError(Exception):
    pass


@dataclass
class ExecResult:
    df: pd.DataFrame
    elapsed_ms: float
    truncated: bool = False


class QueryExecutor:
    def __init__(self, tables: dict[str, pd.DataFrame]):
        self.tables = tables

    def run(self, sql: str) -> ExecResult:
        con = duckdb.connect(":memory:")
        timer = None
        try:
            for name, df in self.tables.items():
                con.register(name, df)
            try:  # block file/network access from inside SQL
                con.execute("SET enable_external_access=false")
                con.execute("SET lock_configuration=true")
            except duckdb.Error:
                pass
            timer = threading.Timer(QUERY_TIMEOUT_S, con.interrupt)
            timer.start()
            start = time.perf_counter()
            out = con.execute(sql).fetchdf()
            elapsed = (time.perf_counter() - start) * 1000
        except duckdb.Error as exc:
            raise QueryError(str(exc).split("\n")[0][:300])
        finally:
            if timer:
                timer.cancel()
            con.close()
        truncated = len(out) > MAX_RESULT_ROWS
        return ExecResult(out.head(MAX_RESULT_ROWS), round(elapsed, 1), truncated)
