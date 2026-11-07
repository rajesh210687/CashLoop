# CashLoop

- **Never write raw SQL or import a DB driver outside `erp/`.** Use `erp.api`
  (`get_customer`, `get_item`, `get_price`, `find_order_by_po`, `create_draft_order`).
  If a needed operation is missing, add it to `erp/api.py`.
  `tests/test_no_raw_sql.py` enforces this.
- `erp/seed.py` is the only script allowed to define schema; re-running it resets the data.
- `get_price` returns `unit_price=None` when there is no contract price; never silently
  fall back to the base price.
- Run tests with `.venv/bin/python -m pytest` (needs `docker compose up -d` and `python erp/seed.py`).
