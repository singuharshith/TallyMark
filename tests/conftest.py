import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.loader import load_csv  # noqa: E402


@pytest.fixture(scope="session")
def sales():
    return load_csv("sales.csv", (ROOT / "sample_data" / "sales.csv").read_bytes()).df


@pytest.fixture(scope="session")
def customers():
    return load_csv("customers.csv", (ROOT / "sample_data" / "customers.csv").read_bytes()).df
