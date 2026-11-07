"""Evaluation framework: runs the assignment's example questions against the sample data with the real LLM
and checks answers against ground truth computed independently in pandas.

Usage:  GROQ_API_KEY=... python scripts/evaluate.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from core.agent import DataAnalyst  # noqa: E402
from core.llm import GroqLLM  # noqa: E402
from core.loader import load_csv  # noqa: E402

sales = load_csv("sales.csv", (ROOT / "sample_data/sales.csv").read_bytes()).df
customers = load_csv("customers.csv", (ROOT / "sample_data/customers.csv").read_bytes()).df
tables = {"sales": sales, "customers": customers}

top_region = sales.groupby("region")["revenue"].sum().idxmax()
top5_customers = sales.groupby("customer_id")["revenue"].sum().nlargest(5).index.tolist()
monthly = sales.groupby(sales["order_date"].dt.to_period("M"))["revenue"].sum()
worst_month = monthly.pct_change().idxmin()
bottom_product = sales.groupby("product")["revenue"].sum().idxmin()

CASES = [
    ("Which region generated the highest revenue?", lambda a: a.result is not None and str(a.result.iloc[0, 0]) == top_region),
    ("Show monthly sales trends.", lambda a: a.result is not None and len(a.result) == 12 and a.figure is not None),
    ("Which products are underperforming?", lambda a: a.result is not None and bottom_product in a.result.astype(str).values),
    ("What are the top five customers?", lambda a: a.result is not None and set(a.result.iloc[:, 0].astype(str)) >= set(top5_customers)
        or (a.result is not None and set(top5_customers) <= set(a.result.astype(str).values.ravel()))),
    ("Generate SQL for this analysis.", lambda a: a.sql is not None and a.sql.lower().startswith(("select", "with"))),
    ("Detect anomalies in the dataset.", lambda a: a.anomalies is not None and "ORD-9001" in set(a.anomalies.rows["order_id"])),
    ("Why did revenue drop in March?", lambda a: a.result is not None and a.error is None and str(worst_month) == "2024-03"),
]


def main():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        sys.exit("Set GROQ_API_KEY to run the evaluation.")
    analyst = DataAnalyst(tables, GroqLLM(key))
    history, rows = [], []
    for q, check in CASES:
        a = analyst.ask(q, history)
        history.append(a)
        try:
            ok = bool(check(a))
        except Exception:
            ok = False
        rows.append({"question": q, "pass": "PASS" if ok else "FAIL", "attempts": a.attempts, "latency_s": round(a.elapsed_ms / 1000, 1)})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n{(df['pass'] == 'PASS').sum()}/{len(df)} passed")


if __name__ == "__main__":
    main()
