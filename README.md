# CashLoop

An AI system for order-to-cash workflows: extracting, validating, and reconciling
purchase orders and invoices, built up one production-grade component at a time.

## Structure

| Folder     | Purpose                                         |
|------------|-------------------------------------------------|
| `extract/` | Structured extraction from POs and invoices     |
| `evals/`   | Evaluation datasets and quality benchmarks      |
| `erp/`     | ERP-side logic and mock ERP integration         |
| `corpus/`  | Sample documents (synthetic/redacted only)      |

## Quick start

    cp .env.example .env      # then set a password
    docker compose up -d      # starts Postgres on localhost:5432

## ERP access rule

**No project writes raw SQL against the ERP.** All ERP reads and writes go through
`erp/api.py` (`get_customer`, `get_item`, `get_price`, `find_order_by_po`,
`create_draft_order`). Need something new? Add a function there.
`erp/seed.py` is the one exception: it provisions the mock ERP itself.
`tests/test_no_raw_sql.py` fails if SQL or a DB driver appears outside `erp/`.

    pip install -r requirements.txt
    python erp/seed.py        # build the mock ERP (needs Postgres running); loads the golden-set
                              # reference CSVs as-is, then generates the rest around them
    pytest                    # tests roll back, so they leave the database untouched
