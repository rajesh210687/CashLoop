"""Shared fixtures. Tests run against the seeded dev database (python erp/seed.py).

Each test runs inside erp.testing.rolled_back_erp(), so create_draft_order tests
never leave rows behind. Tests use only erp.api; raw SQL and DB drivers outside
erp/ are forbidden (see test_no_raw_sql.py).
"""

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from erp import api  # noqa: E402
from erp.testing import ErpUnavailable, rolled_back_erp  # noqa: E402

REFERENCE_DIR = REPO_ROOT / "evals" / "extraction" / "reference"
GOLD_DIR = REPO_ROOT / "evals" / "extraction" / "gold"

# The reference customer most tests use: has a full price list, an active contract.
CUSTOMER = "C001"


def _rows(name):
    with open(REFERENCE_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="session")
def reference():
    return {"customers": _rows("customers.csv"), "items": _rows("items.csv"),
            "prices": _rows("price_list.csv")}


@pytest.fixture(scope="session")
def gold():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLD_DIR.glob("*.json"))]


@pytest.fixture
def db():
    try:
        with rolled_back_erp():
            yield
    except ErpUnavailable as exc:
        pytest.skip(f"Postgres not reachable ({exc}); run docker compose up -d and erp/seed.py")


@pytest.fixture
def sku_catalogue(db, reference):
    """SKUs of each kind for CUSTOMER: with a contract price, without one, and discontinued."""
    priced_skus = {r["sku"] for r in reference["prices"] if r["customer_id"] == CUSTOMER}
    priced = sorted(priced_skus)
    unpriced = sorted(r["sku"] for r in reference["items"] if r["sku"] not in priced_skus)
    inactive = next((f"FST-{n:05d}" for n in range(1, 186)
                     if not api.get_item(f"FST-{n:05d}").is_active), None)
    assert len(priced) >= 2 and unpriced, "reference data unexpected; re-run erp/seed.py"
    return {"priced": priced, "unpriced": unpriced, "inactive": inactive}
