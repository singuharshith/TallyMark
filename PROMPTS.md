# Tallymark prompt design

The application prompts live in [`core/prompts.py`](core/prompts.py). This document records the runtime responsibilities and the guardrails that keep generated analyses tied to the uploaded data.

| Prompt | Used by | Responsibility |
|---|---|---|
| `PLANNER_SYSTEM` and `PLANNER_USER` | `core/agent.py` | Turn a question, available schema, and recent conversation into a structured analysis plan. |
| `REPAIR_USER` | `core/agent.py` | Correct a rejected or failed query using its error message and the known schema. |
| `NARRATOR_SYSTEM` and `NARRATOR_USER` | `core/agent.py` | Explain the executed query's result rows without introducing unsupported figures. |
| `ANOMALY_SYSTEM` | Analysis and data-quality views | Describe statistically flagged records and practical next steps. |
| `INSIGHT_SYSTEM` | Overview | Summarise precomputed measures and observations. |

## Grounding and execution

The language model proposes a query; it does not execute generated Python or calculate the answer. Tallymark validates each query as a read-only statement against the uploaded tables, executes it with DuckDB, and provides the resulting rows to the explanation prompt. The application also checks reported figures against those results.

## Example review questions

- Which region generated the highest revenue?
- Why did revenue decline in March?
- What query produced this result?
- Which records were flagged, and why?

Natural-language analysis requires a Groq API key. Data profiling, deterministic insights, charts, SQL workspace, and statistical anomaly checks work without one.
