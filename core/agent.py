"""Controlled analysis pipeline: plan -> validate -> execute (retry) -> narrate -> verify."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd
import plotly.graph_objects as go

from . import prompts
from .anomalies import AnomalyReport, detect_anomalies
from .charts import anomaly_figure, build_figure
from .config import HISTORY_TURNS, MAX_RETRIES
from .executor import QueryError, QueryExecutor
from .grounding import check_grounding
from .insights import pick_date
from .llm import LLMError
from .logging_utils import log_event, logger
from .pandas_codegen import prepare_pandas
from .profiler import is_id_column, profile_table, schema_for_llm
from .sql_guard import SQLGuardError, validate_sql


@dataclass
class Answer:
    question: str
    intent: str = "query"
    text: str = ""
    insight: str = ""
    follow_ups: list[str] = field(default_factory=list)
    sql: str | None = None
    pandas_code: str | None = None
    reasoning: str = ""
    assumptions: list[str] = field(default_factory=list)
    result: pd.DataFrame | None = None
    figure: go.Figure | None = None
    anomalies: AnomalyReport | None = None
    grounding: tuple[int, int] | None = None
    attempts: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None


class DataAnalyst:
    def __init__(self, tables: dict[str, pd.DataFrame], llm):
        self.tables = tables
        self.llm = llm
        self.executor = QueryExecutor(tables)
        self.schema = schema_for_llm(tables)

    # ---------- public ----------
    def ask(self, question: str, history: list[Answer] | None = None) -> Answer:
        history = history or []
        start = time.perf_counter()
        try:
            ans = self._ask(question, history)
        except LLMError as exc:
            ans = Answer(question=question, intent="error", error=str(exc), text=f"⚠️ {exc}")
        except Exception as exc:  # last-resort guard: never show a stack trace to the user
            logger.exception("unexpected failure")
            ans = Answer(question=question, intent="error", error=str(exc),
                         text="⚠️ Something went wrong while analysing that. Try rephrasing the question.")
        ans.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        log_event(question=question, intent=ans.intent, sql=ans.sql, attempts=ans.attempts,
                  latency_ms=ans.elapsed_ms, error=ans.error, rows=None if ans.result is None else len(ans.result))
        return ans

    # ---------- internals ----------
    def _context(self, history: list[Answer]) -> tuple[str, str]:
        recent = [h for h in history if h.intent != "error"][-HISTORY_TURNS:]
        lines = [f"Q: {h.question}\nA: {h.text[:300]}" + (f"\nSQL: {h.sql}" if h.sql else "") for h in recent]
        last_sql = next((h.sql for h in reversed(recent) if h.sql), None)
        return ("\n\n".join(lines) or "(none)"), (last_sql or "(none)")

    def _pick_table(self, requested: str | None) -> str:
        """Use the table the planner named; otherwise the one with the most numeric measure columns."""
        if requested in self.tables:
            return requested
        def n_measures(df):
            return sum(1 for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not is_id_column(df, c))
        return max(self.tables, key=lambda n: (n_measures(self.tables[n]), len(self.tables[n])))

    def _offline_intent(self, q: str) -> str | None:
        ql = q.lower()
        if "anomal" in ql or "outlier" in ql or "unusual" in ql:
            return "anomaly"
        if "quality" in ql or "missing" in ql or "duplicate" in ql:
            return "quality"
        return None

    def _ask(self, question: str, history: list[Answer]) -> Answer:
        if not self.llm.available:
            intent = self._offline_intent(question)
            if intent is None:
                return Answer(question=question, intent="error", error="no_api_key",
                              text="⚠️ Add your Groq API key in the sidebar to ask questions in natural language. "
                                   "Anomaly detection and data-quality checks work without it (try “Detect anomalies in the dataset”).")
            plan = {"intent": intent, "table": None}
        else:
            context, last_sql = self._context(history)
            plan = self.llm.json(prompts.PLANNER_SYSTEM, prompts.PLANNER_USER.format(
                schema=self.schema, context=context, last_sql=last_sql, question=question))
        intent = str(plan.get("intent") or "query").lower()
        ans = Answer(question=question, intent=intent, reasoning=plan.get("reasoning") or "",
                     assumptions=[str(a) for a in (plan.get("assumptions") or [])])

        if intent == "chat":
            ans.text = plan.get("reply") or "I can analyse your uploaded data - try asking about revenue, trends or anomalies."
            return ans
        if intent == "anomaly":
            return self._anomaly(ans, plan)
        if intent == "quality":
            return self._quality(ans, plan)
        if intent == "sql_request":
            prev = next((h.sql for h in reversed(history) if h.sql), None)
            plan["sql"] = plan.get("sql") or prev
            if not plan["sql"]:
                ans.text = "There is no previous analysis yet - ask a question first and I'll show you its SQL."
                return ans
        return self._query(ans, plan)

    def _query(self, ans: Answer, plan: dict) -> Answer:
        sql, err, res = plan.get("sql"), None, None
        for attempt in range(1, MAX_RETRIES + 2):
            ans.attempts = attempt
            try:
                clean = validate_sql(sql, self.tables.keys())
                res = self.executor.run(clean)
                ans.sql = clean
                break
            except (SQLGuardError, QueryError) as exc:
                err = str(exc)
                logger.info("SQL attempt %s failed: %s", attempt, err)
                if attempt > MAX_RETRIES:
                    ans.sql = sql
                    ans.error = err
                    ans.text = ("⚠️ I couldn't produce a valid query for that after several attempts "
                                f"({err}). Try rephrasing or naming the columns you care about.")
                    return ans
                fix = self.llm.json(prompts.PLANNER_SYSTEM, prompts.REPAIR_USER.format(
                    sql=sql, error=err, schema=self.schema, question=ans.question))
                sql = fix.get("sql") or sql
                for k in ("pandas", "chart", "reasoning"):
                    if fix.get(k):
                        plan[k] = fix[k]
        df = res.df
        ans.result = df
        ans.pandas_code = prepare_pandas(plan.get("pandas"), self.tables)
        if df.empty:
            ans.text = "The query ran successfully but returned no rows - no data matched that question."
            return ans
        ans.figure = build_figure(df, plan.get("chart"))
        try:
            n = self.llm.json(prompts.NARRATOR_SYSTEM, prompts.NARRATOR_USER.format(
                question=ans.question, sql=ans.sql, n_rows=len(df), result_csv=df.head(30).to_csv(index=False)))
            ans.text, ans.insight = str(n.get("answer", "")), str(n.get("insight", ""))
            ans.follow_ups = [str(x) for x in (n.get("follow_ups") or [])][:3]
        except LLMError:
            ans.text = f"The query returned {len(df)} rows (see the table below)."
        if ans.text:
            try:
                ans.grounding = check_grounding(ans.text + " " + ans.insight, df, ans.question)
            except Exception:  # verification is best-effort and must never break an answer
                logger.exception("grounding check failed")
        return ans

    def _anomaly(self, ans: Answer, plan: dict) -> Answer:
        table = self._pick_table(plan.get("table"))
        df = self.tables[table]
        rep = detect_anomalies(df, table)
        ans.anomalies, ans.result = rep, rep.rows
        ans.reasoning = ans.reasoning or (
            f"Checked {len(rep.columns_checked)} numeric columns with z-score (>|{rep.thresholds['z_score']}|σ), "
            f"IQR fences (k={rep.thresholds['iqr_multiplier']}) and an Isolation Forest across all of them.")
        if rep.n_flagged:
            col = rep.columns_checked[0] if rep.columns_checked else None
            top_col = next((c for c in rep.columns_checked if rep.rows["why_flagged"].str.contains(f"{c} =").any()), col)
            if top_col:
                ans.figure = anomaly_figure(df, rep.rows["row_number"] - 1, top_col, pick_date(df))
        ans.text = rep.summary()
        if self.llm.available and rep.n_flagged:
            try:
                top = rep.rows.head(8)[["row_number", "severity", "why_flagged"]].to_csv(index=False)
                n = self.llm.json(prompts.ANOMALY_SYSTEM, f"{rep.summary()}\nColumns checked: {rep.columns_checked}\nTop flagged rows:\n{top}")
                ans.text, ans.insight = str(n.get("answer", ans.text)), str(n.get("insight", ""))
                ans.follow_ups = [str(x) for x in (n.get("follow_ups") or [])][:3]
            except LLMError:
                pass
        return ans

    def _quality(self, ans: Answer, plan: dict) -> Answer:
        table = self._pick_table(plan.get("table"))
        p = profile_table(self.tables[table], table)
        q = p.quality
        worst = sorted(p.columns, key=lambda c: -c.null_pct)[:5]
        ans.result = pd.DataFrame([{"column": c.name, "type": c.dtype, "missing": c.nulls, "missing_pct": c.null_pct,
                                    "unique": c.unique} for c in p.columns])
        ans.text = (f"**Data health for `{table}`: {q['score']}/100.** Completeness {q['completeness']}%, uniqueness {q['uniqueness']}%, "
                    f"validity {q['validity']}%. {q['missing_cells']:,} missing cells, {q['duplicate_rows']:,} duplicate rows, "
                    f"{q['outlier_cells']:,} extreme outlier cells.")
        if worst and worst[0].nulls:
            ans.insight = "Most incomplete columns: " + ", ".join(f"{c.name} ({c.null_pct}%)" for c in worst if c.nulls)
        ans.reasoning = "Quality score = 50% completeness + 25% uniqueness + 25% validity (share of non-extreme numeric values)."
        return ans
