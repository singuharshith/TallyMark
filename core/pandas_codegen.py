"""Prepare the (illustrative, never executed) pandas equivalent shown next to the SQL."""
from __future__ import annotations

import ast


def prepare_pandas(snippet: str | None, tables: dict) -> str | None:
    """Syntax-check the LLM's pandas snippet and prepend loading boilerplate. Returns None if unusable."""
    if not snippet or not str(snippet).strip():
        return None
    code = str(snippet).strip().strip("`")
    if code.lower().startswith("python"):
        code = code[6:].strip()
    try:
        ast.parse(code)
    except SyntaxError:
        return None
    header = ["import pandas as pd", ""] + [f'{name} = pd.read_csv("{name}.csv")' for name in tables]
    return "\n".join(header) + "\n\n" + code + "\nprint(result)"
