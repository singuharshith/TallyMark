"""CSV upload, validation and cleaning."""
from __future__ import annotations

import csv
import io
import re
import warnings
from dataclasses import dataclass, field

import pandas as pd

from .config import MAX_UPLOAD_MB

NO_NUMERIC_COERCE = ("id", "zip", "postal", "phone", "code", "sku")
DATE_HINTS = ("date", "time", "month", "day", "created", "updated", "timestamp", "_at")
DATE_LIKE = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}([ T]\d{1,2}:\d{2}(:\d{2})?)?\s*$")


class LoadError(Exception):
    """Raised with a user-friendly message when a file cannot be used."""


@dataclass
class LoadedTable:
    name: str
    filename: str
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    renamed_columns: dict[str, str] = field(default_factory=dict)


def table_name_from_filename(filename: str, existing=()) -> str:
    stem = re.sub(r"\.[^.]+$", "", filename)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", stem).strip("_").lower() or "table"
    if name[0].isdigit():
        name = "t_" + name
    base, i = name, 2
    while name in existing:
        name, i = f"{base}_{i}", i + 1
    return name


def clean_columns(cols) -> list[str]:
    out, seen = [], {}
    for c in cols:
        s = re.sub(r"[^0-9a-zA-Z]+", "_", str(c).strip()).strip("_").lower() or "column"
        if s[0].isdigit():
            s = "c_" + s
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 1
        out.append(s)
    return out


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _sniff_delimiter(text: str) -> str:
    sample = text[:20000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _coerce_types(df: pd.DataFrame, notes: list[str]) -> pd.DataFrame:
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_bool_dtype(s):
            continue
        stripped = s.astype("string").str.strip()
        non_null = stripped.dropna()
        non_null = non_null[non_null != ""]
        if non_null.empty:
            continue
        # numbers with currency symbols / thousands separators / percent
        if not any(h in col for h in NO_NUMERIC_COERCE):
            cleaned = non_null.str.replace(r"[$€£₹,\s]", "", regex=True).str.replace(r"%$", "", regex=True)
            if pd.to_numeric(cleaned, errors="coerce").notna().mean() >= 0.95:
                full = stripped.str.replace(r"[$€£₹,\s]", "", regex=True).str.replace(r"%$", "", regex=True)
                num = pd.to_numeric(full, errors="coerce").astype("float64")
                if num.notna().all() and (num % 1 == 0).all():
                    num = num.astype("int64")
                df[col] = num
                notes.append(f"Column '{col}' was converted to numeric.")
                continue
        # dates
        sample = non_null.head(200)
        looks_like_date = sample.str.match(DATE_LIKE).mean() >= 0.95
        hinted = any(h in col for h in DATE_HINTS)
        if looks_like_date or hinted:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(stripped, errors="coerce", format="mixed")
            if parsed.notna().sum() >= 0.9 * len(non_null):
                df[col] = parsed
                notes.append(f"Column '{col}' was parsed as dates.")
                continue
        df[col] = stripped.astype(object).where(stripped.notna(), None)
    return df


def load_csv(filename: str, raw: bytes, existing_names=()) -> LoadedTable:
    """Validate and parse one uploaded CSV. Raises LoadError on failure."""
    if not raw or not raw.strip():
        raise LoadError(f"'{filename}' is empty.")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise LoadError(f"'{filename}' is larger than the {MAX_UPLOAD_MB} MB limit.")
    if not filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise LoadError(f"'{filename}' is not a CSV file.")

    text = _decode(raw)
    delim = _sniff_delimiter(text)
    notes: list[str] = []
    try:
        df = pd.read_csv(io.StringIO(text), sep=delim, skipinitialspace=True, on_bad_lines="skip")
    except pd.errors.EmptyDataError:
        raise LoadError(f"'{filename}' contains no data.")
    except Exception as exc:
        raise LoadError(f"'{filename}' could not be parsed as CSV ({exc}).")

    n_raw = len(df)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.shape[1] == 0 or df.empty:
        raise LoadError(f"'{filename}' has no usable rows or columns.")
    if n_raw - len(df) > 0:
        notes.append(f"Dropped {n_raw - len(df)} fully empty rows.")
    if delim != ",":
        notes.append(f"Detected delimiter {delim!r}.")

    old = [str(c) for c in df.columns]
    new = clean_columns(old)
    renamed = {o: n for o, n in zip(old, new) if o != n}
    df.columns = new
    if renamed:
        notes.append(f"{len(renamed)} column names were normalised to snake_case for SQL.")

    df = _coerce_types(df.reset_index(drop=True), notes)
    name = table_name_from_filename(filename, existing_names)
    return LoadedTable(name=name, filename=filename, df=df, warnings=notes, renamed_columns=renamed)
