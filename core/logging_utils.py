"""Observability: structured JSONL query log + standard logging."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "tallymark_activity.jsonl"

logger = logging.getLogger("tallymark")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def log_event(**fields) -> None:
    """Append one event to logs/tallymark_activity.jsonl. Never raises."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        fields["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fields, default=str) + "\n")
    except Exception as exc:  # pragma: no cover
        logger.warning("could not write log: %s", exc)


def read_events(limit: int = 50) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out[::-1]
