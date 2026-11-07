"""Automatic KPIs, facts and chart specs computed with pandas (no LLM)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pandas.api import types as pdt

from .profiler import column_kind, is_id_column, quality_score

METRIC_HINTS = ("revenue", "sales", "amount", "total", "profit", "income", "cost", "price", "value")


def fmt(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e4:
        return f"{v / 1e3:.1f}K"
    return f"{v:,.2f}" if v != int(v) else f"{int(v):,}"


def pick_metric(df: pd.DataFrame) -> str | None:
    nums = [c for c in df.columns if column_kind(df, c) == "numeric" and not is_id_column(df, c)]
    for hint in METRIC_HINTS:
        for c in nums:
            if hint in c.lower():
                return c
    return nums[0] if nums else None


def pick_date(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if pdt.is_datetime64_any_dtype(df[c]):
            return c
    return None


def pick_dims(df: pd.DataFrame, limit: int = 3) -> list[str]:
    dims = [c for c in df.columns if column_kind(df, c) == "categorical" and 2 <= df[c].nunique() <= 30
            and not is_id_column(df, c)]
    return dims[:limit]


@dataclass
class Overview:
    table: str
    metric: str | None
    date_col: str | None
    dims: list[str]
    kpis: list[dict] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    charts: list[tuple[str, pd.DataFrame, dict]] = field(default_factory=list)
    worst_month: str | None = None


def build_overview(df: pd.DataFrame, table: str) -> Overview:
    metric, date_col, dims = pick_metric(df), pick_date(df), pick_dims(df)
    ov = Overview(table=table, metric=metric, date_col=date_col, dims=dims)
    q = quality_score(df)
    ov.kpis = [
        {"label": "Records", "value": f"{len(df):,}"},
        {"label": "Columns", "value": f"{df.shape[1]}"},
        {"label": "Data health", "value": f"{q['score']}/100"},
    ]
    if metric:
        total = float(df[metric].sum())
        ov.kpis.append({"label": f"Total {metric}", "value": fmt(total)})
        ov.kpis.append({"label": f"Avg {metric}", "value": fmt(float(df[metric].mean()))})

        if date_col:
            m = (df.dropna(subset=[date_col]).assign(month=lambda d: d[date_col].dt.to_period("M").dt.to_timestamp())
                 .groupby("month", as_index=False)[metric].sum())
            if len(m) >= 3:
                m["mom_pct"] = m[metric].pct_change() * 100
                ov.charts.append((f"Monthly {metric}", m[["month", metric]], {"type": "line", "x": "month", "y": metric}))
                worst = m.loc[m["mom_pct"].idxmin()]
                best = m.loc[m["mom_pct"].idxmax()]
                ov.worst_month = worst["month"].strftime("%B %Y")
                ov.facts.append(f"Largest month-over-month drop: {worst['month']:%B %Y} ({worst['mom_pct']:.1f}% vs previous month).")
                ov.facts.append(f"Strongest month-over-month growth: {best['month']:%B %Y} (+{best['mom_pct']:.1f}%).")
                slope = (m[metric].iloc[-1] - m[metric].iloc[0]) / max(len(m) - 1, 1)
                ov.facts.append(f"Overall trend across {len(m)} months is {'upward' if slope > 0 else 'downward'} "
                                f"({fmt(slope)} per month on average).")
                last, prev = m.iloc[-1], m.iloc[-2]
                ov.kpis.append({"label": "Latest month vs prior", "value": f"{last['mom_pct']:+.1f}%"})
        for i, d in enumerate(dims):
            g = df.groupby(d, as_index=False)[metric].sum().sort_values(metric, ascending=False)
            if g.empty or total == 0:
                continue
            top, bot = g.iloc[0], g.iloc[-1]
            ov.facts.append(f"By {d}: '{top[d]}' leads with {fmt(top[metric])} ({100 * top[metric] / total:.1f}% of total {metric}); "
                            f"'{bot[d]}' is lowest with {fmt(bot[metric])} ({100 * bot[metric] / total:.1f}%).")
            if i < 2:
                kind = "pie" if len(g) <= 6 and i == 0 else "bar"
                ov.charts.append((f"{metric} by {d}", g.head(12), {"type": kind, "x": d, "y": metric}))
    else:
        ov.facts.append("No numeric measure column was detected, so only structure and quality statistics are shown.")
    if q["missing_cells"]:
        ov.facts.append(f"{q['missing_cells']:,} cells are missing and {q['duplicate_rows']:,} rows are exact duplicates.")
    return ov
