"""Explainable anomaly detection: z-score + IQR per column, Isolation Forest across columns."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.api import types as pdt
from sklearn.ensemble import IsolationForest

from .profiler import is_id_column


@dataclass
class AnomalyReport:
    table: str
    rows: pd.DataFrame
    total_rows: int
    flagged_count: int
    columns_checked: list[str]
    methods: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)

    @property
    def n_flagged(self) -> int:
        return self.flagged_count

    def summary(self) -> str:
        if self.n_flagged == 0:
            return f"No anomalies found in '{self.table}' with the current thresholds."
        pct = 100 * self.n_flagged / max(self.total_rows, 1)
        return (f"{self.n_flagged} of {self.total_rows} rows ({pct:.1f}%) in '{self.table}' were flagged "
                f"using {', '.join(f'{k} ({v})' for k, v in self.methods.items())}.")


def detect_anomalies(df: pd.DataFrame, table: str = "data", z_thresh: float = 3.0, iqr_k: float = 3.0,
                     contamination: float = 0.01, max_rows: int = 100) -> AnomalyReport:
    data = df.reset_index(drop=True)
    num_cols = [c for c in data.columns if pdt.is_numeric_dtype(data[c]) and not pdt.is_bool_dtype(data[c])
                and not is_id_column(data, c)]
    reasons: dict[int, list[str]] = defaultdict(list)
    severity: dict[int, float] = defaultdict(float)
    methods: Counter = Counter()
    checked = []

    for c in num_cols:
        s = data[c].astype("float64")
        valid = s.dropna()
        if len(valid) < 8 or valid.std(ddof=0) == 0:
            continue
        checked.append(c)
        mean, std = valid.mean(), valid.std(ddof=0)
        q1, q3 = valid.quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - iqr_k * iqr, q3 + iqr_k * iqr
        z = (s - mean) / std
        mask_z = (z.abs() > z_thresh) & s.notna()
        # IQR is an independent flag only when the value is also moderately far from the mean (avoids noise on skewed data)
        mask_iqr = (((s < lo) | (s > hi)) & (z.abs() > 2.5) & s.notna()) if iqr > 0 else pd.Series(False, index=s.index)
        mostly_non_negative = (valid >= 0).mean() >= 0.99
        mask_neg = (s < 0) & s.notna() if mostly_non_negative else pd.Series(False, index=s.index)
        for idx in s.index[mask_z | mask_iqr | mask_neg]:
            v, zz = s[idx], z[idx]
            parts = []
            if mask_z[idx]:
                parts.append(f"{abs(zz):.1f}σ {'above' if zz > 0 else 'below'} the mean ({mean:,.2f})")
                methods["z-score"] += 1
            if mask_iqr[idx]:
                parts.append(f"outside the IQR fence [{lo:,.2f}, {hi:,.2f}]")
                methods["IQR"] += 1
            text = f"{c} = {v:,.2f} is " + " and ".join(parts) if parts else f"{c} = {v:,.2f}"
            if mask_neg[idx]:
                text += ("; " if parts else " is ") + "negative in a column that is otherwise non-negative"
                methods["sign check"] += 1
            reasons[idx].append(text)
            severity[idx] = max(severity[idx], abs(zz), 3.0 if mask_neg[idx] else 0)

    if len(checked) >= 2 and len(data) >= 50:
        X = data[checked].astype("float64")
        X = X.fillna(X.median())
        iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
        pred = iso.fit_predict(X)
        score = -iso.score_samples(X)
        for idx in np.where(pred == -1)[0]:
            reasons[int(idx)].append(f"Isolation Forest: unusual combination of {', '.join(checked[:4])}"
                                     f"{'...' if len(checked) > 4 else ''} (anomaly score {score[idx]:.2f})")
            severity[int(idx)] = max(severity[int(idx)], 3.0)
            methods["Isolation Forest"] += 1

    idxs = sorted(reasons, key=lambda i: -severity[i])[:max_rows]
    out = data.loc[idxs].copy()
    out.insert(0, "row_number", [i + 1 for i in idxs])
    out["severity"] = [round(severity[i], 2) for i in idxs]
    out["why_flagged"] = [" | ".join(reasons[i]) for i in idxs]
    return AnomalyReport(
        table=table, rows=out, total_rows=len(data), flagged_count=len(reasons),
        columns_checked=checked, methods=dict(methods),
        thresholds={"z_score": z_thresh, "iqr_multiplier": iqr_k, "isolation_forest_contamination": contamination},
    )
