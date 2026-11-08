"""Tallymark - Streamlit entry point."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from core.agent import Answer, DataAnalyst
from core.anomalies import detect_anomalies
from core.charts import anomaly_figure, build_figure, quality_gauge, style
from core.config import GROQ_MODEL
from core.executor import QueryError, QueryExecutor
from core.insights import build_overview, pick_date
from core.llm import GroqLLM, LLMError
from core import prompts
from core.loader import LoadError, load_csv
from core.logging_utils import read_events
from core.profiler import profile_table
from core.report import build_html, build_markdown
from core.sql_guard import SQLGuardError, validate_sql
from ui.components import inject_theme, kpi_row, render_answer, suggested_questions

ROOT = Path(__file__).parent
st.set_page_config(page_title="Tallymark | CSV Analysis", page_icon="TM", layout="wide")
inject_theme()

# ------------------------------------------------------------------ state
S = st.session_state
S.setdefault("tables", {})        # name -> LoadedTable
S.setdefault("history", [])       # list[Answer]
S.setdefault("seen_files", set())
S.setdefault("cache", {})
S.setdefault("pending_q", None)
S.setdefault("exec_summary", None)


def add_file(filename: str, raw: bytes) -> None:
    try:
        t = load_csv(filename, raw, S.tables.keys())
        S.tables[t.name] = t
        S.cache.clear()
        for w in t.warnings:
            st.toast(f"{t.name}: {w}")
    except LoadError as exc:
        st.sidebar.error(str(exc))


def dfs() -> dict[str, pd.DataFrame]:
    return {n: t.df for n, t in S.tables.items()}


def cached(key, fn):
    if key not in S.cache:
        S.cache[key] = fn()
    return S.cache[key]


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown(
        '<div class="brand-lockup"><span class="brand-mark">T</span>'
        '<div><p class="brand">Tallymark</p><p class="tagline">CSV analysis, with the numbers to check.</p></div></div>',
        unsafe_allow_html=True,
    )
    env_key = os.getenv("GROQ_API_KEY", "")
    with st.expander("Language model settings", expanded=False):
        key = env_key or st.text_input(
            "Groq API key", type="password",
            help="Used for natural-language analysis. The key is kept in this session only.",
        )
        model = st.text_input(
            "Model",
            value=GROQ_MODEL,
            key="groq_model",
            help="Use a model ID available to your Groq account. The default supports JSON responses.",
        )
    llm = GroqLLM(key, model)
    if llm.available:
        st.caption(
            "Questions send the schema, recent conversation and query results to Groq. "
            "Question text and SQL are logged locally."
        )
    else:
        st.caption("Add a Groq API key to ask questions in plain language.")
    st.divider()
    files = st.file_uploader("Upload CSV files", type=["csv", "tsv", "txt"], accept_multiple_files=True)
    for f in files or []:
        k = f"{f.name}:{f.size}"
        if k not in S.seen_files:
            S.seen_files.add(k)
            add_file(f.name, f.getvalue())
    if st.button("Load sample datasets", width="stretch"):
        for p in sorted((ROOT / "sample_data").glob("*.csv")):
            if p.stem not in S.tables:
                add_file(p.name, p.read_bytes())
        st.rerun()
    st.caption("Included example data is synthetic.")
    if S.tables:
        st.markdown("**Datasets**")
        for name, t in list(S.tables.items()):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"`{name}` · {len(t.df):,} × {t.df.shape[1]}")
            if c2.button("Remove", key=f"rm_{name}"):
                del S.tables[name]
                S.cache.clear()
                S.history.clear()
                st.rerun()
        if st.button("Clear analysis history", width="stretch"):
            S.history.clear()
            st.rerun()

# ------------------------------------------------------------------ landing
if not S.tables:
    st.markdown(
        '<div class="hero"><span class="eyebrow">CSV ANALYSIS</span>'
        '<h1>Upload a file. Follow the numbers.</h1>'
        '<p>Review key measures, trends and unusual records, then ask a question in plain language. '
        'Each answer includes the SQL and result rows used to calculate it.</p></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Load a file**\n\nUpload a CSV. Columns, dates and values are checked on import.")
    c2.markdown("**Review the data**\n\nStart with totals, trends, missing values and unusual records.")
    c3.markdown("**Check an answer**\n\nAsk a question, then inspect the SQL and rows behind the result.")
    st.info("Upload CSV files in the sidebar, or load the sample datasets to explore the workspace.")
    st.stop()

tables = dfs()
names = list(tables)
dataset_overviews = {
    name: cached(("ov", name, tables[name].shape), lambda name=name: build_overview(tables[name], name))
    for name in names
}
primary_name = max(
    names,
    key=lambda name: (
        dataset_overviews[name].metric is not None,
        dataset_overviews[name].date_col is not None,
        len(dataset_overviews[name].dims),
        len(tables[name]),
    ),
)
primary_overview = dataset_overviews[primary_name]
t_overview, t_analyst, t_detect, t_lab, t_report = st.tabs(
    ["Overview", "Analysis", "Data quality", "SQL workspace", "Reports"])

# ------------------------------------------------------------------ overview
with t_overview:
    st.markdown(
        '<div class="page-heading"><span class="eyebrow">WORKSPACE / OVERVIEW</span>'
        '<h1>Business overview</h1>'
        '<p>Performance measures, trends, and data quality at a glance.</p></div>',
        unsafe_allow_html=True,
    )
    sel = st.selectbox("Dataset", names, index=names.index(primary_name), key="tallymark_ov_dataset") if len(names) > 1 else names[0]
    df = tables[sel]
    ov = cached(("ov", sel, df.shape), lambda: build_overview(df, sel))
    prof = cached(("prof", sel, df.shape), lambda: profile_table(df, sel))
    kpi_row(ov.kpis[:5])
    st.write("")
    left, right = st.columns([2, 1])
    with left:
        for i, (title, d, spec) in enumerate(ov.charts):
            fig = build_figure(d, {**spec, "title": title})
            if fig is not None:
                st.plotly_chart(fig, width="stretch", key=f"ovc_{sel}_{i}")
    with right:
        st.plotly_chart(quality_gauge(prof.quality["score"]), width="stretch", key=f"gauge_{sel}")
        st.markdown("**Key observations**")
        for f in ov.facts:
            st.markdown(f'<div class="fact">{f}</div>', unsafe_allow_html=True)
    if llm.available and st.button("Generate executive summary"):
        with st.spinner("Writing summary from computed facts..."):
            try:
                S.exec_summary = llm.json(prompts.INSIGHT_SYSTEM, f"Dataset {sel}\nKPIs: {ov.kpis}\nFacts:\n" + "\n".join(ov.facts))
            except LLMError as exc:
                st.error(str(exc))
    if S.exec_summary:
        st.markdown(f'<div class="insight"><b>Executive summary</b><br>{S.exec_summary.get("summary", "")}</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.markdown("**Key findings**\n" + "\n".join(f"- {x}" for x in S.exec_summary.get("key_findings", [])))
        c2.markdown("**Recommendations**\n" + "\n".join(f"- {x}" for x in S.exec_summary.get("recommendations", [])))
    with st.expander("Preview & column profile"):
        st.dataframe(df.head(100), width="stretch", hide_index=True)
        st.dataframe(pd.DataFrame([vars(c) | {"sample": ", ".join(c.sample)} for c in prof.columns]).drop(columns=["stats"]),
                     width="stretch", hide_index=True)
    for w in S.tables[sel].warnings:
        st.caption(w)

# ------------------------------------------------------------------ analyst
with t_analyst:
    st.markdown(
        '<div class="page-heading"><span class="eyebrow">WORKSPACE / ANALYSIS</span>'
        '<h1>Ask a question</h1>'
        '<p>Get a clear answer, inspect the result, and review how it was calculated.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**Suggested questions**")
    sq = suggested_questions(primary_overview)
    cols = st.columns(3)
    for i, q in enumerate(sq):
        if cols[i % 3].button(q, key=f"sq_{i}", width="stretch"):
            S.pending_q = q
    if not llm.available:
        st.warning("Add a Groq API key under Language model settings to ask questions in plain language.")
    for i, a in enumerate(S.history):
        with st.chat_message("user"):
            st.write(a.question)
        with st.chat_message("assistant"):
            fu = render_answer(a, i, is_last=(i == len(S.history) - 1))
            if fu:
                S.pending_q = fu
    typed = st.chat_input("Ask about your data, e.g. “Why did revenue drop in March?”")
    question = typed or S.pending_q
    S.pending_q = None
    if question:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Analysing your question..."):
                S.history.append(DataAnalyst(tables, llm).ask(question, S.history))
        st.rerun()

# ------------------------------------------------------------------ detective
with t_detect:
    st.markdown(
        '<div class="page-heading"><span class="eyebrow">WORKSPACE / DATA QUALITY</span>'
        '<h1>Data quality</h1>'
        '<p>Review completeness, duplicates, and statistically unusual records.</p></div>',
        unsafe_allow_html=True,
    )
    sel = st.selectbox("Dataset", names, index=names.index(primary_name), key="tallymark_quality_dataset")
    df = tables[sel]
    c1, c2, c3 = st.columns(3)
    z = c1.slider("Z-score threshold (σ)", 2.0, 6.0, 3.0, 0.5)
    k = c2.slider("IQR multiplier", 1.5, 5.0, 3.0, 0.5)
    cont = c3.slider("Isolation Forest contamination", 0.001, 0.05, 0.01, 0.001, format="%.3f")
    rep = detect_anomalies(df, sel, z_thresh=z, iqr_k=k, contamination=cont)
    prof = profile_table(df, sel)
    q = prof.quality
    kpi_row([{"label": "Flagged rows", "value": f"{rep.n_flagged}"}, {"label": "Missing cells", "value": f"{q['missing_cells']:,}"},
             {"label": "Duplicate rows", "value": f"{q['duplicate_rows']:,}"}, {"label": "Health score", "value": f"{q['score']}/100"}])
    st.write("")
    st.caption(rep.summary() + " Methods: " + ", ".join(f"{m}" for m in rep.methods))
    if rep.n_flagged:
        st.markdown("**Unusual records and reasons**")
        id_columns = [c for c in rep.rows if c.lower() == "id" or c.lower().endswith("_id")]
        visible_columns = ["row_number", *id_columns[:1], "severity", "why_flagged"]
        st.dataframe(
            rep.rows[visible_columns],
            width="stretch",
            hide_index=True,
            column_config={
                "row_number": st.column_config.NumberColumn("Row", format="%d"),
                "severity": st.column_config.NumberColumn("Severity", format="%.2f"),
                "why_flagged": st.column_config.TextColumn("Why flagged", width="large"),
            },
        )
        with st.expander("Full flagged row details"):
            st.dataframe(rep.rows, width="stretch", hide_index=True)
        col = st.selectbox("Visualise column", rep.columns_checked)
        st.plotly_chart(anomaly_figure(df, rep.rows["row_number"] - 1, col, pick_date(df)), width="stretch")
        if llm.available and st.button("Explain unusual records"):
            with st.spinner("Preparing explanation..."):
                try:
                    top = rep.rows.head(8)[["row_number", "severity", "why_flagged"]].to_csv(index=False)
                    n = llm.json(prompts.ANOMALY_SYSTEM, f"{rep.summary()}\nColumns: {rep.columns_checked}\n{top}")
                    st.markdown(n.get("answer", ""))
                    st.markdown(f'<div class="insight">{n.get("insight", "")}</div>', unsafe_allow_html=True)
                except LLMError as exc:
                    st.error(str(exc))
    else:
        st.success("No anomalies at these thresholds.")
    st.markdown("**Data quality by column**")
    qdf = pd.DataFrame([{"column": c.name, "type": c.dtype, "missing_pct": c.null_pct, "unique": c.unique} for c in prof.columns])
    st.dataframe(qdf, width="stretch", hide_index=True)

# ------------------------------------------------------------------ query lab
with t_lab:
    st.markdown(
        '<div class="page-heading"><span class="eyebrow">WORKSPACE / SQL</span>'
        '<h1>SQL workspace</h1>'
        '<p>Run a read-only query against your loaded datasets and inspect the results.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("Run a **read-only** SQL query on your datasets (DuckDB dialect). Queries from the Analysis workspace are listed here.")
    with st.expander("Schema"):
        for n, d in tables.items():
            st.markdown(f"**{n}** — " + ", ".join(f"`{c}` ({str(d[c].dtype)})" for c in d.columns))
    last_sql = next((a.sql for a in reversed(S.history) if a.sql), f"SELECT * FROM {primary_name} LIMIT 20")
    sql = st.text_area("SQL", value=last_sql, height=140, key=f"lab_sql_{hash(last_sql)}")
    if st.button("Run query"):
        try:
            clean = validate_sql(sql, tables.keys())
            res = QueryExecutor(tables).run(clean)
            st.caption(f"{len(res.df):,} rows in {res.elapsed_ms} ms")
            st.dataframe(res.df, width="stretch", hide_index=True)
            fig = build_figure(res.df, None)
            if fig is not None:
                st.plotly_chart(fig, width="stretch")
        except (SQLGuardError, QueryError) as exc:
            st.error(f"{exc}")
    st.markdown("**Query history (this session)**")
    for a in [a for a in S.history if a.sql][::-1]:
        with st.expander(a.question):
            st.code(a.sql, language="sql")
    with st.expander("Recent analysis activity"):
        ev = read_events(30)
        if ev:
            st.dataframe(pd.DataFrame(ev)[["ts", "question", "intent", "attempts", "latency_ms", "rows", "error"]], width="stretch", hide_index=True)
        else:
            st.caption("No requests logged yet.")

# ------------------------------------------------------------------ reports
with t_report:
    st.markdown(
        '<div class="page-heading"><span class="eyebrow">WORKSPACE / REPORTS</span>'
        '<h1>Reports</h1>'
        '<p>Export key measures, data-quality findings, and analysis history.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("Export a shareable report with KPIs, computed insights, data quality and the conversation log.")
    ovs = {n: cached(("ov", n, tables[n].shape), lambda n=n: build_overview(tables[n], n)) for n in names}
    qs = {n: cached(("prof", n, tables[n].shape), lambda n=n: profile_table(tables[n], n)).quality for n in names}
    md_text = build_markdown(ovs, qs, S.history, S.exec_summary)
    figs = [build_figure(d, {**sp, "title": t}) for ov in ovs.values() for (t, d, sp) in ov.charts]
    figs += [a.figure for a in S.history if a.figure is not None]
    figs = [f for f in figs if f is not None]
    c1, c2 = st.columns(2)
    c1.download_button("Download Markdown", md_text, "tallymark_report.md", "text/markdown", width="stretch")
    c2.download_button("Download HTML (with charts)", build_html(md_text, figs), "tallymark_report.html", "text/html", width="stretch")
    with st.expander("Preview"):
        st.markdown(md_text)
