"""
erp/testing.py - test support for code that uses erp.api.

`rolled_back_erp()` makes every erp.api call inside the block share one
transaction that is rolled back at the end, so tests can create draft orders
without leaving rows in the dev database. It lives here, not in tests/, because
only erp/ may import a database driver.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from erp import api


class ErpUnavailable(RuntimeError):
    """The ERP database cannot be reached."""


@contextmanager
def rolled_back_erp() -> Iterator[None]:
    load_dotenv(api.REPO_ROOT / ".env")
    try:
        conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=3)
    except (KeyError, psycopg.OperationalError) as exc:
        raise ErpUnavailable(str(exc)) from exc

    @contextmanager
    def shared() -> Iterator[psycopg.Connection]:
        yield conn  # never commits

    original = api._connection
    api._connection = shared
    try:
        yield
    finally:
        api._connection = original
        conn.rollback()
        conn.close()
