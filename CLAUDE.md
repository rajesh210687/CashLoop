# CashLoop

- **Never write raw SQL or import a DB driver outside `erp/`.** Use `erp.api`
  (`get_customer`, `get_item`, `get_price`, `find_order_by_po`, `create_draft_order`).
  If a needed operation is missing, add it to `erp/api.py`.
  `tests/test_no_raw_sql.py` enforces this.
- `erp/seed.py` is the only script allowed to define schema; re-running it resets the data.
- `get_price` returns `unit_price=None` when there is no contract price; never silently
  fall back to the base price.
- Run tests with `.venv/bin/python -m pytest` (needs `docker compose up -d` and `python erp/seed.py`).

## Golden set (evals/extraction, corpus/po_emails)
- `extract/` must never import, read, or quote anything under `evals/` (gold labels leaking into
  prompts make accuracy meaningless). Few-shot examples go in `extract/examples/`, written
  separately. `tests/test_no_gold_leakage.py` enforces this.
- `evals/extraction/reference/*.csv` is the source of truth for those customers, SKUs and prices.
  The ERP seed must load them as-is; never regenerate their prices randomly.
- A gold file change gets its own commit with the reason in the message, e.g.
  "po_010: confirmed stale total should flag TOTAL_MISMATCH", so a score change can be
  traced to the extractor or to the answer key.
- The eval runner (`evals/extraction/run.py`, not written yet) should glob
  `corpus/po_emails/*.txt` and load `evals/extraction/gold/<id>.json` by email ID, so new
  emails (po_026 to po_030) are picked up automatically.
- `python evals/build_golden_set.py` regenerates po_001..po_025, the gold JSON, manifest and
  reference CSVs, and DELETES those three folders first. Hand-written emails (po_026+) in
  `corpus/po_emails/` would be erased by it, so change the script before adding them.
