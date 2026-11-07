"""Chart selection and Plotly rendering (dark theme)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pandas.api import types as pdt

PALETTE = ["#E8874A", "#A4B64B", "#38A99B", "#E1B64A", "#D77A68", "#769B9A", "#C29A6B", "#8B9271"]


def style(fig: go.Figure, title: str | None = None, height: int = 380) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=PALETTE, height=height, margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        title=dict(text=title or "", font=dict(size=15, color="#F0EFE9"), x=0, xanchor="left"),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#C8C7BE", size=12),
        legend=dict(orientation="h", y=-0.2, font=dict(color="#AAA99F")),
        hoverlabel=dict(bgcolor="#30312F", bordercolor="rgba(245,240,230,.12)", font=dict(color="#F0EFE9")),
    )
    fig.update_xaxes(gridcolor="rgba(245,240,230,0.07)", zerolinecolor="rgba(245,240,230,0.1)", tickfont=dict(color="#AAA99F"))
    fig.update_yaxes(gridcolor="rgba(245,240,230,0.07)", zerolinecolor="rgba(245,240,230,0.1)", tickfont=dict(color="#AAA99F"))
    return fig


def _numeric_cols(df):
    return [c for c in df.columns if pdt.is_numeric_dtype(df[c]) and not pdt.is_bool_dtype(df[c])]


def _date_cols(df):
    return [c for c in df.columns if pdt.is_datetime64_any_dtype(df[c])]


def auto_spec(df: pd.DataFrame) -> dict | None:
    """Choose a chart from the result shape."""
    if df is None or df.empty or len(df) < 2 and df.shape[1] < 2:
        return None
    nums, dates = _numeric_cols(df), _date_cols(df)
    cats = [c for c in df.columns if c not in nums and c not in dates]
    if dates and nums:
        return {"type": "line", "x": dates[0], "y": nums[0]}
    if cats and nums and len(df) >= 2:
        return {"type": "bar", "x": cats[0], "y": nums[0]}
    if len(nums) >= 2:
        return {"type": "scatter", "x": nums[0], "y": nums[1]}
    if len(nums) == 1 and len(df) > 5:
        return {"type": "histogram", "x": nums[0]}
    return None


def build_figure(df: pd.DataFrame, spec: dict | None) -> go.Figure | None:
    """Render a Plotly figure from the planner's chart spec; falls back to auto-selection if the spec is invalid."""
    if df is None or df.empty:
        return None
    spec = dict(spec or {})
    ctype = str(spec.get("type") or "").lower()
    if ctype == "none":
        return None

    def col(name):
        if isinstance(name, list):
            name = name[0] if name else None
        return name if name in df.columns else None

    x, y, color = col(spec.get("x")), col(spec.get("y")), col(spec.get("color"))
    valid = ctype in {"bar", "line", "pie", "scatter", "histogram"} and x is not None and (y is not None or ctype == "histogram")
    if valid and ctype != "histogram" and not pdt.is_numeric_dtype(df[y]):
        valid = False
    if not valid:
        auto = auto_spec(df)
        if not auto:
            return None
        ctype, x, y, color = auto["type"], auto["x"], auto.get("y"), None
        spec = {"title": spec.get("title")}
    title = spec.get("title")
    d = df.copy()
    if ctype == "bar":
        d = d.head(30)
        fig = px.bar(d, x=x, y=y, color=color, text_auto=".3s", barmode="group")
    elif ctype == "line":
        d = d.sort_values(x)
        fig = px.line(d, x=x, y=y, color=color, markers=True)
    elif ctype == "pie":
        fig = px.pie(d.head(8), names=x, values=y, hole=0.5)
    elif ctype == "scatter":
        fig = px.scatter(d, x=x, y=y, color=color)
    else:
        fig = px.histogram(d, x=x, nbins=30)
    return style(fig, title)


def anomaly_figure(df: pd.DataFrame, flagged_index, column: str, date_col: str | None = None) -> go.Figure:
    d = df.reset_index(drop=True).copy()
    d["_flag"] = d.index.isin(list(flagged_index))
    d["status"] = d["_flag"].map({True: "Anomaly", False: "Normal"})
    x = date_col if date_col and date_col in d.columns else d.index
    fig = px.scatter(d, x=x, y=column, color="status", color_discrete_map={"Normal": "#769B9A", "Anomaly": "#E8874A"},
                     opacity=0.8, hover_data=d.columns[:6].tolist())
    fig.update_traces(marker=dict(size=7))
    return style(fig, f"{column}: normal vs flagged records")


def quality_gauge(score: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score, number={"suffix": "/100"},
        gauge={"axis": {"range": [0, 100], "tickcolor": "#AAA99F"},
               "bar": {"color": "#A4B64B", "thickness": .22},
               "steps": [{"range": [0, 60], "color": "rgba(215,122,104,.25)"}, {"range": [60, 85], "color": "rgba(225,182,74,.25)"},
                         {"range": [85, 100], "color": "rgba(164,182,75,.25)"}],
               "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0},
    ))
    return style(fig, "Data health score", height=250)
