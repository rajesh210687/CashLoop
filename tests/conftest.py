"""Shared fixtures. Tests run against the seeded dev database (python erp/seed.py).

Each test runs inside erp.testing.rolled_back_erp(), so create_draft_order tests
never leave rows behind. Tests use only erp.api; raw SQL and DB drivers outside
erp/ are forbidden (see test_no_raw_sql.py).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from erp import api  # noqa: E402
from erp.testing import ErpUnavailable, rolled_back_erp  # noqa: E402


@pytest.fixture
def db():
    try:
        with rolled_back_erp():
            yield
    except ErpUnavailable as exc:
        pytest.skip(f"Postgres not reachable ({exc}); run docker compose up -d and erp/seed.py")


@pytest.fixture
def sku_catalogue(db):
    """Find SKUs of each kind for customer C00001 by scanning the deterministic SKU range."""
    found = {"priced": [], "unpriced": [], "inactive": None}
    for n in range(1, 186):
        sku = f"FST-{n:05d}"
        price = api.get_price("C00001", sku)
        if not price.item_is_active:
            found["inactive"] = found["inactive"] or sku
        elif price.source == "contract":
            found["priced"].append(sku)
        else:
            found["unpriced"].append(sku)
    assert len(found["priced"]) >= 2 and found["unpriced"], "seed data unexpected; re-run erp/seed.py"
    return found
