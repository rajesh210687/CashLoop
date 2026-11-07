"""
erp/api.py - the only way the rest of CashLoop talks to the ERP.

Rule: no project writes raw SQL against the ERP. Anything outside `erp/` that
needs ERP data or wants to change it calls a function here. If a function you
need is missing, add it here rather than reaching for a database connection.

Reads:   get_customer, get_item, get_price, find_order_by_po
Writes:  create_draft_order (draft status only; nothing else is ever written)

Design notes:
  * Results are frozen dataclasses; callers never see rows or column names.
  * Money is Decimal throughout, never float.
  * Failures are domain exceptions (ErpError subclasses); no psycopg error escapes.
  * Prices are looked up here when an order is created, so callers cannot
    supply (or fake) a price.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Literal, Sequence

import psycopg
from dotenv import load_dotenv
from psycopg import errors as pg_errors
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]

__all__ = [
    "Customer", "Item", "Price", "Order", "OrderLine", "LineRequest",
    "ErpError", "CustomerNotFound", "InactiveCustomer", "UnknownSku",
    "InactiveItem", "NoContractPrice", "DuplicatePO", "InvalidOrder",
    "get_customer", "get_item", "get_price", "find_order_by_po", "create_draft_order",
]

# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Customer:
    customer_code: str
    legal_name: str
    gstin: str
    city: str
    state: str
    payment_terms_days: int
    credit_limit: Decimal
    is_active: bool


@dataclass(frozen=True)
class Item:
    sku: str
    description: str
    category: str
    uom: str
    base_price: Decimal
    gst_rate: Decimal
    is_active: bool


@dataclass(frozen=True)
class Price:
    """A customer's contracted price for one SKU.

    `unit_price` is None when the customer has no contract for the SKU
    (`source == "none"`). That is deliberately NOT replaced by the base price:
    whether to fall back is a business decision for the caller.
    """
    customer_code: str
    sku: str
    unit_price: Decimal | None
    source: Literal["contract", "none"]
    valid_from: date | None
    item_is_active: bool


@dataclass(frozen=True)
class LineRequest:
    """One line the caller wants on a new order. Note: no price field."""
    sku: str
    quantity: Decimal


@dataclass(frozen=True)
class OrderLine:
    line_no: int
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal


@dataclass(frozen=True)
class Order:
    order_number: str
    customer_code: str
    po_number: str
    order_date: date
    status: str
    currency: str
    lines: tuple[OrderLine, ...]
    subtotal: Decimal
    gst_amount: Decimal
    grand_total: Decimal


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class ErpError(Exception):
    """Base class for every error this module raises on purpose."""


class CustomerNotFound(ErpError):
    pass


class InactiveCustomer(ErpError):
    pass


class UnknownSku(ErpError):
    pass


class InactiveItem(ErpError):
    pass


class NoContractPrice(ErpError):
    pass


class InvalidOrder(ErpError):
    """The requested order is malformed (no lines, bad quantity, repeated SKU...)."""


class DuplicatePO(ErpError):
    """This customer already has an order for this PO number."""

    def __init__(self, customer_code: str, po_number: str, existing_order_number: str | None = None):
        self.customer_code = customer_code
        self.po_number = po_number
        self.existing_order_number = existing_order_number
        detail = f" (existing order {existing_order_number})" if existing_order_number else ""
        super().__init__(f"{customer_code} already has PO {po_number}{detail}")


# --------------------------------------------------------------------------
# Connection (internal)
# --------------------------------------------------------------------------


@contextmanager
def _connection() -> Iterator[psycopg.Connection]:
    """One short-lived connection per public call; commits on success, rolls back on error.

    Tests replace this to share one connection that is always rolled back.
    """
    load_dotenv(REPO_ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ErpError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    with psycopg.connect(url, row_factory=dict_row) as conn:
        yield conn


_CUSTOMER_COLS = ("customer_code, legal_name, gstin, city, state, "
                  "payment_terms_days, credit_limit, is_active")


def _customer(row: dict) -> Customer:
    return Customer(**row)


def _fetch_customer(cur, customer_code: str) -> dict:
    cur.execute(f"SELECT id, {_CUSTOMER_COLS} FROM customers WHERE customer_code = %s",
                (customer_code,))
    row = cur.fetchone()
    if row is None:
        raise CustomerNotFound(f"No customer with code {customer_code!r}")
    return row


def _fetch_item(cur, sku: str) -> dict:
    cur.execute("SELECT id, sku, description, category, uom, base_price, gst_rate, is_active "
                "FROM items WHERE sku = %s", (sku,))
    row = cur.fetchone()
    if row is None:
        raise UnknownSku(f"No item with SKU {sku!r}")
    return row


def _load_order(cur, order_id: int) -> Order:
    cur.execute(
        "SELECT o.order_number, c.customer_code, o.po_number, o.order_date, o.status, o.currency, "
        "       t.subtotal, t.gst_amount, t.grand_total "
        "FROM orders o "
        "JOIN customers c ON c.id = o.customer_id "
        "JOIN order_totals t ON t.order_id = o.id "
        "WHERE o.id = %s", (order_id,))
    head = cur.fetchone()
    cur.execute(
        "SELECT l.line_no, i.sku, i.description, l.quantity, l.unit_price, l.line_amount "
        "FROM order_lines l JOIN items i ON i.id = l.item_id "
        "WHERE l.order_id = %s ORDER BY l.line_no", (order_id,))
    lines = tuple(OrderLine(**r) for r in cur.fetchall())
    return Order(lines=lines, **head)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

_MAX_NAME_MATCHES = 10


def get_customer(query: str, *, city: str | None = None) -> list[Customer]:
    """Find customers by code, GSTIN, or name as written on a PO.

    Tries, in order, and returns the matches of the first step that has any:
      1. exact customer code or GSTIN (case-insensitive);
      2. exact legal name or known alias (case-insensitive);
      3. partial match on legal name or alias (at most 10 results).
    `city` narrows any step. Returns a LIST because names are ambiguous
    ("Acme" matches several companies); an empty list means no match. Inactive
    customers are included, check `is_active`.
    """
    q = query.strip()
    if not q:
        return []
    city_sql, city_args = ("AND lower(c.city) = lower(%s)", (city.strip(),)) if city else ("", ())

    base = f"SELECT DISTINCT c.id, " + ", ".join(f"c.{col.strip()}" for col in _CUSTOMER_COLS.split(","))
    base += " FROM customers c LEFT JOIN customer_aliases a ON a.customer_id = c.id "
    steps = [
        ("WHERE (lower(c.customer_code) = lower(%s) OR upper(c.gstin) = upper(%s))", (q, q), ""),
        ("WHERE (lower(c.legal_name) = lower(%s) OR lower(a.alias) = lower(%s))", (q, q), ""),
        ("WHERE (c.legal_name ILIKE %s OR a.alias ILIKE %s)",
         (f"%{_escape_like(q)}%",) * 2, f" LIMIT {_MAX_NAME_MATCHES}"),
    ]
    with _connection() as conn, conn.cursor() as cur:
        for where, args, tail in steps:
            cur.execute(f"{base} {where} {city_sql} ORDER BY c.id{tail}", (*args, *city_args))
            rows = cur.fetchall()
            if rows:
                return [_customer({k: v for k, v in r.items() if k != "id"}) for r in rows]
    return []


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_item(sku: str) -> Item:
    """Look up one catalogue item. Raises UnknownSku."""
    with _connection() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, sku.strip())
    row.pop("id")
    return Item(**row)


def get_price(customer_code: str, sku: str) -> Price:
    """The customer's contract price for a SKU.

    Raises CustomerNotFound / UnknownSku. If the customer has no contract for the
    SKU you get a Price with `unit_price=None` and `source="none"`, not an error.
    """
    with _connection() as conn, conn.cursor() as cur:
        customer = _fetch_customer(cur, customer_code.strip())
        item = _fetch_item(cur, sku.strip())
        cur.execute("SELECT unit_price, valid_from FROM price_lists "
                    "WHERE customer_id = %s AND item_id = %s", (customer["id"], item["id"]))
        row = cur.fetchone()
    return Price(
        customer_code=customer["customer_code"], sku=item["sku"],
        unit_price=row["unit_price"] if row else None,
        source="contract" if row else "none",
        valid_from=row["valid_from"] if row else None,
        item_is_active=item["is_active"],
    )


def find_order_by_po(customer_code: str, po_number: str) -> Order | None:
    """The customer's existing order for this PO number, or None (duplicate-PO check)."""
    with _connection() as conn, conn.cursor() as cur:
        customer = _fetch_customer(cur, customer_code.strip())
        cur.execute("SELECT id FROM orders WHERE customer_id = %s AND po_number = %s",
                    (customer["id"], po_number.strip()))
        row = cur.fetchone()
        return _load_order(cur, row["id"]) if row else None


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def create_draft_order(customer_code: str, po_number: str, lines: Sequence[LineRequest]) -> Order:
    """Create an order in 'draft' status, priced from the customer's contract.

    All-or-nothing: either the header and every line are saved, or nothing is.
    Raises InvalidOrder, CustomerNotFound, InactiveCustomer, DuplicatePO,
    UnknownSku, InactiveItem, NoContractPrice.
    """
    po_number = po_number.strip()
    if not po_number:
        raise InvalidOrder("PO number is required")
    if not lines:
        raise InvalidOrder("An order needs at least one line")
    skus = [ln.sku.strip() for ln in lines]
    if len(set(skus)) != len(skus):
        raise InvalidOrder("Each SKU may appear only once per order")
    for ln in lines:
        if ln.quantity <= 0:
            raise InvalidOrder(f"Quantity for {ln.sku} must be positive")

    with _connection() as conn, conn.cursor() as cur:
        customer = _fetch_customer(cur, customer_code.strip())
        if not customer["is_active"]:
            raise InactiveCustomer(f"{customer['customer_code']} is not active")

        cur.execute("SELECT order_number FROM orders WHERE customer_id = %s AND po_number = %s",
                    (customer["id"], po_number))
        existing = cur.fetchone()
        if existing:
            raise DuplicatePO(customer["customer_code"], po_number, existing["order_number"])

        priced = []  # (item id, quantity, unit price)
        for sku, ln in zip(skus, lines):
            item = _fetch_item(cur, sku)
            if not item["is_active"]:
                raise InactiveItem(f"{sku} is discontinued")
            cur.execute("SELECT unit_price FROM price_lists WHERE customer_id = %s AND item_id = %s",
                        (customer["id"], item["id"]))
            price = cur.fetchone()
            if price is None:
                raise NoContractPrice(f"{customer['customer_code']} has no contract price for {sku}")
            priced.append((item["id"], ln.quantity, price["unit_price"]))

        today = date.today()
        cur.execute("SELECT nextval(pg_get_serial_sequence('orders', 'id')) AS id")
        order_id = cur.fetchone()["id"]
        try:
            cur.execute(
                "INSERT INTO orders (id, order_number, customer_id, po_number, order_date, status) "
                "VALUES (%s, %s, %s, %s, %s, 'draft')",
                (order_id, f"SO-{today.year}-{order_id:06d}", customer["id"], po_number, today))
        except pg_errors.UniqueViolation:  # lost a race with a concurrent insert
            raise DuplicatePO(customer["customer_code"], po_number) from None
        cur.executemany(
            "INSERT INTO order_lines (order_id, line_no, item_id, quantity, unit_price) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(order_id, n, item_id, qty, price) for n, (item_id, qty, price) in enumerate(priced, 1)])
        return _load_order(cur, order_id)
