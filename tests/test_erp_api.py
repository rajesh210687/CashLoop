from decimal import Decimal

import pytest

from erp import api
from erp.api import LineRequest

from conftest import CUSTOMER


# ---- get_customer ----------------------------------------------------------

def test_lookup_by_code_and_gstin(db, reference):
    row = next(r for r in reference["customers"] if r["customer_id"] == CUSTOMER)
    [by_code] = api.get_customer(CUSTOMER.lower())
    [by_gstin] = api.get_customer(row["gstin"].lower())
    assert by_code == by_gstin
    assert by_code.legal_name == row["name"]


def test_lookup_by_exact_name_ignores_case(db, reference):
    row = next(r for r in reference["customers"] if r["customer_id"] == CUSTOMER)
    assert [c.customer_code for c in api.get_customer(row["name"].upper())] == [CUSTOMER]


def test_partial_name_returns_candidates_and_city_narrows(db):
    matches = api.get_customer("Acme")
    assert "C003" in {c.customer_code for c in matches}
    narrowed = api.get_customer("Acme", city="Pune")
    assert narrowed and all(c.city == "Pune" for c in narrowed)
    assert "C003" in {c.customer_code for c in narrowed}


def test_lookalike_customers_are_both_findable(db):
    # C031 "Apex Pharma Engineering" is a deliberate look-alike of C003 in the golden set.
    assert "C031" in {c.customer_code for c in api.get_customer("Apex Pharma")}


def test_overseas_customer_has_no_gstin(db):
    [gulf] = api.get_customer("C049")
    assert gulf.gstin is None and gulf.currency == "USD"


def test_no_match_is_empty_list(db):
    assert api.get_customer("zzz no such company") == []
    assert api.get_customer("   ") == []


def test_like_wildcards_are_not_special(db):
    assert api.get_customer("%") == []


# ---- get_item / get_price --------------------------------------------------

def test_get_item_and_unknown_sku(db, reference):
    first = reference["items"][0]
    item = api.get_item(first["sku"])
    assert item.description == first["description"] and isinstance(item.base_price, Decimal)
    with pytest.raises(api.UnknownSku):
        api.get_item("NOPE-1")


def test_contract_price_none_and_inactive(db, sku_catalogue):
    priced = api.get_price(CUSTOMER, sku_catalogue["priced"][0])
    assert priced.source == "contract" and priced.unit_price > 0 and priced.currency == "INR"

    unpriced = api.get_price(CUSTOMER, sku_catalogue["unpriced"][0])
    assert unpriced.source == "none" and unpriced.unit_price is None  # no silent base-price fallback
    assert unpriced.currency is None

    if sku_catalogue["inactive"]:
        assert api.get_price(CUSTOMER, sku_catalogue["inactive"]).item_is_active is False


def test_usd_customer_prices_are_in_usd(db, reference):
    row = next(r for r in reference["prices"] if r["customer_id"] == "C049")
    price = api.get_price("C049", row["sku"])
    assert price.currency == "USD" and price.unit_price == Decimal(row["unit_price"])


def test_get_price_unknown_customer(db):
    with pytest.raises(api.CustomerNotFound):
        api.get_price("C999", "VLV-101")


# ---- create_draft_order ----------------------------------------------------

def test_create_draft_order_prices_from_contract(db, sku_catalogue):
    a, b = sku_catalogue["priced"][:2]
    order = api.create_draft_order(
        CUSTOMER, "TEST-PO-1", [LineRequest(a, Decimal("10")), LineRequest(b, Decimal("2.5"))])

    assert order.status == "draft" and order.po_number == "TEST-PO-1"
    assert order.order_number.startswith("SO-")
    assert [ln.line_no for ln in order.lines] == [1, 2]
    for line in order.lines:
        assert line.unit_price == api.get_price(CUSTOMER, line.sku).unit_price
        assert line.line_amount == (line.quantity * line.unit_price).quantize(Decimal("0.01"))
    assert order.subtotal == sum(ln.line_amount for ln in order.lines)
    assert order.grand_total == order.subtotal + order.gst_amount  # totals come from the order_totals view


def test_duplicate_po_rejected(db, sku_catalogue):
    lines = [LineRequest(sku_catalogue["priced"][0], Decimal("1"))]
    first = api.create_draft_order(CUSTOMER, "TEST-PO-DUP", lines)
    assert api.find_order_by_po(CUSTOMER, "TEST-PO-DUP").order_number == first.order_number
    with pytest.raises(api.DuplicatePO) as err:
        api.create_draft_order(CUSTOMER, "TEST-PO-DUP", lines)
    assert err.value.existing_order_number == first.order_number


def test_find_order_by_po_missing(db):
    assert api.find_order_by_po(CUSTOMER, "NO-SUCH-PO") is None


def test_rejections_leave_nothing_behind(db, sku_catalogue):
    ok = sku_catalogue["priced"][0]
    bad_unpriced = sku_catalogue["unpriced"][0]

    with pytest.raises(api.NoContractPrice):
        api.create_draft_order(CUSTOMER, "TEST-PO-2",
                               [LineRequest(ok, Decimal("1")), LineRequest(bad_unpriced, Decimal("1"))])
    with pytest.raises(api.UnknownSku):
        api.create_draft_order(CUSTOMER, "TEST-PO-2", [LineRequest("NOPE-1", Decimal("1"))])
    if sku_catalogue["inactive"]:
        with pytest.raises(api.InactiveItem):
            api.create_draft_order(CUSTOMER, "TEST-PO-2", [LineRequest(sku_catalogue["inactive"], Decimal("1"))])
    with pytest.raises(api.CustomerNotFound):
        api.create_draft_order("C999", "TEST-PO-2", [LineRequest(ok, Decimal("1"))])
    assert api.find_order_by_po(CUSTOMER, "TEST-PO-2") is None


def test_inactive_customer_rejected(db, sku_catalogue):
    inactive = next((c for n in range(1, 201) for c in api.get_customer(f"C{n:03d}") if not c.is_active), None)
    if inactive is None:
        pytest.skip("seed has no inactive customer")
    with pytest.raises(api.InactiveCustomer):
        api.create_draft_order(inactive.customer_code, "TEST-PO-3",
                               [LineRequest(sku_catalogue["priced"][0], Decimal("1"))])


@pytest.mark.parametrize("po, lines", [
    ("", [LineRequest("VLV-101", Decimal("1"))]),
    ("P", []),
    ("P", [LineRequest("VLV-101", Decimal("0"))]),
    ("P", [LineRequest("VLV-101", Decimal("1")), LineRequest("VLV-101", Decimal("2"))]),
])
def test_invalid_orders(db, po, lines):
    with pytest.raises(api.InvalidOrder):
        api.create_draft_order(CUSTOMER, po, lines)
