"""Cross-check numbers in the LLM's narration against the real query result."""
from __future__ import annotations

import re

import pandas as pd

NUM = re.compile(r"(?<![\w.])(-?\d[\d,]*\.?\d*)\s*([kKmMbB](?![a-zA-Z]))?")
MULT = {"k": 1e3, "m": 1e6, "b": 1e9}


def extract_numbers(text: str) -> list[float]:
    out = []
    for raw, suffix in NUM.findall(text or ""):
        try:
            v = float(raw.replace(",", "").rstrip("."))
        except ValueError:
            continue
        if suffix:
            v *= MULT[suffix.lower()]
        out.append(v)
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.011, 0.01 * abs(b))


def check_grounding(answer: str, df: pd.DataFrame, question: str = "") -> tuple[int, int]:
    """Return (matched, total) figures from `answer` found in `df` (ignoring years, small ranks, question numbers)."""
    pool: set[float] = set()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            pool.update(float(v) for v in s.dropna().head(200))
        else:
            for v in s.dropna().head(200):
                pool.update(extract_numbers(str(v)))
    pool |= {v * 100 for v in list(pool)} | {abs(v) for v in list(pool)}
    q_nums = set(extract_numbers(question))
    total = matched = 0
    for n in extract_numbers(answer):
        if n in q_nums or (1900 <= n <= 2100 and n == int(n)) or (0 <= n <= 10 and n == int(n)):
            continue
        total += 1
        if any(_close(n, p) for p in pool):
            matched += 1
    return matched, total
