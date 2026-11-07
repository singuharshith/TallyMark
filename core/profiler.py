"""Dataset profiling, data-quality scoring and LLM schema description."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.api import types as pdt


def is_id_column(df: pd.DataFrame, col: str) -> bool:
    s = df[col]
    name = col.lower()
    if name == "id" or name.endswith("_id") or name.endswith("id") and len(name) <= 12 and pdt.is_integer_dtype(s):
        return True
    return pdt.is_integer_dtype(s) and len(s) > 20 and s.nunique() / max(len(s), 1) > 0.95


def column_kind(df: pd.DataFrame, col: str) -> str:
    s = df[col]
    if pdt.is_bool_dtype(s):
        return "boolean"
    if pdt.is_datetime64_any_dtype(s):
        return "datetime"
    if pdt.is_numeric_dtype(s):
        return "numeric"
    n = s.nunique(dropna=True)
    if n <= max(30, 0.05 * len(s)):
        return "categorical"
    return "text"


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    kind: str
    nulls: int
    null_pct: float
    unique: int
    is_id: bool
    sample: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class TableProfile:
    name: str
    rows: int
    cols: int
    columns: list[ColumnProfile]
    duplicates: int
    quality: dict


def _outlier_cells(df: pd.DataFrame) -> tuple[int, int]:
    bad = total = 0
    for c in df.columns:
        if column_kind(df, c) != "numeric" or is_id_column(df, c):
            continue
        s = df[c].dropna().astype(float)
        if len(s) < 8:
            continue
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        total += len(s)
        if iqr > 0:
            bad += int(((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum())
    return bad, total


def quality_score(df: pd.DataFrame) -> dict:
    cells = max(df.size, 1)
    missing = int(df.isna().sum().sum())
    dups = int(df.duplicated().sum())
    out_bad, out_total = _outlier_cells(df)
    completeness = 1 - missing / cells
    uniqueness = 1 - dups / max(len(df), 1)
    validity = 1 - (out_bad / out_total if out_total else 0)
    score = 100 * (0.5 * completeness + 0.25 * uniqueness + 0.25 * validity)
    return {
        "score": round(score, 1),
        "completeness": round(completeness * 100, 1),
        "uniqueness": round(uniqueness * 100, 1),
        "validity": round(validity * 100, 1),
        "missing_cells": missing,
        "duplicate_rows": dups,
        "outlier_cells": out_bad,
    }


def profile_table(df: pd.DataFrame, name: str = "data") -> TableProfile:
    cols = []
    for c in df.columns:
        s = df[c]
        kind = column_kind(df, c)
        stats: dict = {}
        if kind == "numeric":
            stats = {"min": float(s.min()), "max": float(s.max()), "mean": float(s.mean()), "median": float(s.median())} if s.notna().any() else {}
        elif kind == "datetime" and s.notna().any():
            stats = {"min": str(s.min().date()), "max": str(s.max().date())}
        cols.append(
            ColumnProfile(
                name=c, dtype=str(s.dtype), kind=kind, nulls=int(s.isna().sum()),
                null_pct=round(100 * s.isna().mean(), 2), unique=int(s.nunique(dropna=True)),
                is_id=is_id_column(df, c), sample=s.dropna().astype(str).head(3).tolist(), stats=stats,
            )
        )
    q = quality_score(df)
    return TableProfile(name=name, rows=len(df), cols=df.shape[1], columns=cols, duplicates=q["duplicate_rows"], quality=q)


def _duck_type(kind: str, s: pd.Series) -> str:
    if kind == "datetime":
        return "TIMESTAMP"
    if kind == "boolean":
        return "BOOLEAN"
    if kind == "numeric":
        return "BIGINT" if pdt.is_integer_dtype(s) else "DOUBLE"
    return "VARCHAR"


def schema_for_llm(tables: dict[str, pd.DataFrame]) -> str:
    """Compact schema description (names, types, example values) for the planner prompt."""
    lines = []
    for name, df in tables.items():
        lines.append(f"TABLE {name} ({len(df)} rows)")
        for c in df.columns:
            kind = column_kind(df, c)
            s = df[c]
            detail = ""
            if kind == "categorical":
                vals = s.dropna().unique().tolist()
                detail = "values: " + ", ".join(map(str, vals[:15])) + (" ..." if len(vals) > 15 else "")
            elif kind == "numeric" and s.notna().any():
                detail = f"range {s.min():,.4g} to {s.max():,.4g}"
            elif kind == "datetime" and s.notna().any():
                detail = f"range {s.min().date()} to {s.max().date()}"
            else:
                detail = "e.g. " + ", ".join(s.dropna().astype(str).head(3).tolist())
            lines.append(f"  - {c} {_duck_type(kind, s)}  [{kind}] {detail}")
        lines.append("")
    return "\n".join(lines)
