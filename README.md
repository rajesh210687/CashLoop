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
