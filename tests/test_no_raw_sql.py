"""Guardrail: nothing outside erp/ may touch the database or contain SQL.

erp/seed.py lives in erp/ and is allowed: it provisions the mock ERP itself.
This file is excluded from the scan because it has to spell out the patterns.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "erp"}

FORBIDDEN = [
    re.compile(r"^\s*(import|from)\s+(psycopg2?|sqlite3|sqlalchemy|asyncpg|pymysql)\b", re.M),
    re.compile(r"\bSELECT\b.+\bFROM\b"),
    re.compile(r"\bINSERT\s+INTO\b"),
    re.compile(r"\bUPDATE\s+\w+\s+SET\b"),
    re.compile(r"\bDELETE\s+FROM\b"),
    re.compile(r"\b(CREATE|DROP|ALTER)\s+(TABLE|VIEW|INDEX)\b"),
]


def test_no_raw_sql_outside_erp():
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if rel.parts[0] in SKIP_DIRS or any(p in SKIP_DIRS for p in rel.parts) or path == Path(__file__):
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern.search(text):
                offenders.append(f"{rel}: matches {pattern.pattern}")
    assert not offenders, "Raw SQL / DB drivers found outside erp/ - use erp.api:\n" + "\n".join(offenders)
