"""Reusable Streamlit UI pieces."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.agent import Answer


def inject_theme() -> None:
    css = (Path(__file__).parent / "theme.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def kpi_row(kpis: list[dict]) -> None:
    cols = st.columns(len(kpis))
    for col, k in zip(cols, kpis):
        col.markdown(f'<div class="kpi"><div class="l">{k["label"]}</div><div class="v">{k["value"]}</div></div>', unsafe_allow_html=True)


def render_answer(ans: Answer, idx: int, is_last: bool) -> str | None:
    """Render one assistant answer. Returns a follow-up question if the user clicked one."""
    clicked = None
    st.markdown(ans.text)
    if ans.insight:
        st.markdown(f'<div class="insight">{ans.insight}</div>', unsafe_allow_html=True)
    if ans.figure is not None:
        st.plotly_chart(ans.figure, width="stretch", key=f"fig_{idx}")
    if ans.anomalies is not None and ans.anomalies.n_flagged:
        show = ans.anomalies.rows.head(10)
        st.dataframe(show, width="stretch", hide_index=True)
    pills = []
    if ans.grounding and ans.grounding[1]:
        m, t = ans.grounding
        pills.append(f'<span class="pill {"ok" if m == t else "warn"}">{m}/{t} figures matched to query results</span>')
    if ans.attempts > 1:
        pills.append(f'<span class="pill warn">query corrected after {ans.attempts} attempts</span>')
    if ans.elapsed_ms:
        pills.append(f'<span class="pill">{ans.elapsed_ms / 1000:.1f}s</span>')
    if pills and not ans.error:
        st.markdown("".join(pills), unsafe_allow_html=True)
    if ans.sql or ans.reasoning or ans.assumptions:
        with st.expander("How this was calculated"):
            if ans.reasoning:
                st.markdown(f"**Approach:** {ans.reasoning}")
            if ans.assumptions:
                st.markdown("**Assumptions:**\n" + "\n".join(f"- {a}" for a in ans.assumptions))
            if ans.sql:
                st.markdown("**SQL (executed in DuckDB):**")
                st.code(ans.sql, language="sql")
            if ans.pandas_code:
                st.markdown("**Equivalent Pandas (illustrative):**")
                st.code(ans.pandas_code, language="python")
    if ans.result is not None and not ans.result.empty and ans.anomalies is None:
        with st.expander(f"Result table ({len(ans.result):,} rows)"):
            st.dataframe(ans.result, width="stretch", hide_index=True)
    if is_last and ans.follow_ups:
        cols = st.columns(len(ans.follow_ups))
        for i, (c, q) in enumerate(zip(cols, ans.follow_ups)):
            if c.button(q, key=f"fu_{idx}_{i}", width="stretch"):
                clicked = q
    return clicked


def suggested_questions(overview) -> list[str]:
    m, d, dims = overview.metric, overview.date_col, overview.dims
    qs = []
    if m and dims:
        qs.append(f"Which {dims[0]} generated the highest {m}?")
    if m and d:
        qs.append(f"Show monthly {m} trends.")
    if dims:
        qs.append(f"Which {dims[min(1, len(dims) - 1)]} are underperforming?")
    if m and d and overview.worst_month:
        qs.append(f"Why did {m} drop in {overview.worst_month.split()[0]}?")
    qs += ["Detect anomalies in the dataset.", "Generate SQL for this analysis."]
    return qs[:6]
