# Tallymark

### Business data, in context.

A browser-based business analysis workspace for exploring CSVs, understanding performance, and investigating unusual records. Every analytical answer is backed by a query you can inspect.

Built for the *Digital Back Office - AI Engineer Assignment*.

| | |
|---|---|
| **GitHub repository** | [singuharshith/TallyMark](https://github.com/singuharshith/TallyMark) |
| **Demo video** | _Add the 10–30 second recording here or save it as `docs/demo.mp4`_ |
| **Local website** | Run the setup below; no online deployment is required |

![Tallymark application architecture](docs/architecture.png)

The deliverable is a **web application**, as requested in the assignment. Streamlit serves the website and connects its interface directly to the Python analysis modules; a separate frontend or backend service is not required. Deployment is optional when submitting the requested demo video.

## How an analysis works

1. **Plan** — The language model receives the uploaded data schema and recent conversation, then returns a structured query plan.
2. **Validate** — `core/sql_guard.py` parses the query and restricts it to a single read-only `SELECT` over uploaded tables.
3. **Calculate** — DuckDB executes the validated query on in-memory data with external access disabled and a query timeout. Failed queries can be repaired up to two times.
4. **Explain** — The language model receives the actual result rows and is instructed not to invent figures.
5. **Check** — `core/grounding.py` checks figures in the explanation against the query result.
6. **Present** — The site displays the answer, a chart when appropriate, results, reasoning, assumptions, SQL, and illustrative Pandas.

Arbitrary AI-generated Python is **never executed**.

## Requirement coverage

| Assignment requirement | Where |
|---|---|
| Upload & validate one or more CSVs | `core/loader.py` - encoding + delimiter sniffing, empty/size/type checks, column normalisation, currency/date coercion, per-file error messages |
| Natural-language questions | `core/agent.py` + `core/prompts.py` (optional Groq API key) |
| Business insights & summaries | `core/insights.py` (computed KPIs/facts) + optional AI executive summary |
| Charts (bar, line, pie, scatter, histogram) | `core/charts.py` - spec validation with auto-selection fallback |
| SQL and/or Pandas code | Shown with answers; “Generate SQL for this analysis” reuses the last query; the **SQL workspace** runs user-edited read-only queries |
| Anomaly detection with explanations | `core/anomalies.py` - z-score, IQR, sign check, Isolation Forest; every row has a plain-English `why_flagged` |
| Explain reasoning | reasoning + assumptions + grounding badge in each answer |
| Conversation context | last 4 turns + previous SQL passed to the planner ("now break that down by month") |
| **Bonus** | multi-file joins · data-quality score · dashboard · report export (MD/HTML) · logging/observability · evaluation script · Docker · tests |

## Quick start

### Option A - Python

#### Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Open .env and set GROQ_API_KEY (free at console.groq.com)
.\.venv\Scripts\streamlit.exe run app.py
```

#### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GROQ_API_KEY (free at console.groq.com)
streamlit run app.py
```
Open http://localhost:8501 → click **Load sample datasets** → try the suggested questions.

### Option B - Docker
```bash
docker compose up --build
```
Create `.env` from `.env.example` first (PowerShell: `Copy-Item .env.example .env`) and set `GROQ_API_KEY`.

> No API key? The app still runs: dataset overview, data-quality checks and anomaly detection are deterministic. Natural-language Q&A needs the key (you can also paste it in the sidebar).

## Try these questions (sample data)

- Which region generated the highest revenue?
- Show monthly sales trends.
- Which products are underperforming?
- What are the top five customers?  *(joins `sales` with `customers`)*
- Why did revenue drop in March? *(the sample data has a deliberate March dip, concentrated in the East region)*
- Now break that down by product. *(follow-up using context)*
- Generate SQL for this analysis.
- Detect anomalies in the dataset. *(4 planted anomalies: ORD-9001…9004)*

## Project structure
```
app.py                 Tallymark website (Overview · Analysis · Data quality · SQL workspace · Reports)
core/                  UI-independent analysis engine, called by the website
  loader.py profiler.py sql_guard.py executor.py llm.py prompts.py
  agent.py             plan → validate → execute/repair → explain → verify
  anomalies.py charts.py insights.py grounding.py pandas_codegen.py report.py logging_utils.py
ui/                    theme.css + components
tests/                 43 passing tests (loader, SQL guard, executor, anomalies, agent w/ fake LLM, UI smoke test)
scripts/               generate_sample_data.py · evaluate.py · make_architecture.py
sample_data/           sales.csv, customers.csv
docs/                  architecture.png, screenshots, demo video
```

## Testing & evaluation
```bash
pytest -q                          # unit + pipeline tests (no network needed)
GROQ_API_KEY=... python scripts/evaluate.py   # runs the assignment's example questions with the real LLM
```
Ground truth for the evaluation is computed independently in pandas.

## Security & reliability decisions
- Read-only, single-statement SQL, AST-validated against an allow-list of tables; DuckDB external access disabled.
- API key comes from env or sidebar; never written to disk or logs.
- Friendly errors for bad CSVs, missing key, bad SQL, empty results, LLM outages; unexpected exceptions are logged, not shown.
- Every request is logged to `logs/tallymark_activity.jsonl` (question, intent, SQL, attempts, latency).

## Assumptions & notes
- Column names are normalised to snake_case so the LLM and SQL stay consistent.
- "Underperforming" = lowest by the main metric; the definition is shown under *Assumptions* for each answer.
- Anomalies use statistical thresholds (default 3σ / 3×IQR / Isolation Forest 1%) adjustable in **Data quality**; a flagged value is a lead to investigate, not proof of an error.
- The Pandas snippet is generated by the LLM for readability and is **not executed**; the SQL is the source of truth.
- Data and conversation history are held in the Streamlit session and are not persisted between sessions.

## Screenshots
Captured with the bundled sample datasets. The data-quality screenshot shows flagged records without an API key.

### Overview
![Tallymark business overview](docs/screenshots/overview.png)

### Data quality
![Tallymark data quality review](docs/screenshots/detective.png)
