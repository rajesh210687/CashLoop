from decimal import Decimal

import pytest

from erp import api
from erp.api import LineRequest


# ---- get_customer ----------------------------------------------------------

def test_lookup_by_code_and_gstin(db):
    [by_code] = api.get_customer("C00001")
    [by_gstin] = api.get_customer(by_code.gstin.lower())
    assert by_code == by_gstin
    assert by_code.legal_name == "Acme Engineering Private Limited"


def test_lookup_by_alias(db):
    [c] = api.get_customer("acme engg")
    assert c.customer_code == "C00001"


def test_partial_name_returns_several_candidates_and_city_narrows(db):
    matches = api.get_customer("Acme")
    assert len(matches) >= 2
    narrowed = api.get_customer("Acme", city="Pune")
    assert [c.city for c in narrowed] == ["Pune"]


def test_no_match_is_empty_list(db):
    assert api.get_customer("zzz no such company") == []
    assert api.get_customer("   ") == []


def test_like_wildcards_are_not_special(db):
    assert api.get_customer("%") == []


# ---- get_item / get_price --------------------------------------------------

def test_get_item_and_unknown_sku(db):
    item = api.get_item("FST-00001")
    assert item.sku == "FST-00001" and isinstance(item.base_price, Decimal)
    with pytest.raises(api.UnknownSku):
        api.get_item("NOPE-1")


def test_contract_price_none_and_inactive(db, sku_catalogue):
    priced = api.get_price("C00001", sku_catalogue["priced"][0])
    assert priced.source == "contract" and priced.unit_price > 0

    unpriced = api.get_price("C00001", sku_catalogue["unpriced"][0])
    assert unpriced.source == "none" and unpriced.unit_price is None  # no silent base-price fallback

    if sku_catalogue["inactive"]:
        assert api.get_price("C00001", sku_catalogue["inactive"]).item_is_active is False


def test_get_price_unknown_customer(db):
    with pytest.raises(api.CustomerNotFound):
        api.get_price("C99999", "FST-00001")


# ---- create_draft_order ----------------------------------------------------

def test_create_draft_order_prices_from_contract(db, sku_catalogue):
    a, b = sku_catalogue["priced"][:2]
    order = api.create_draft_order(
        "C00001", "TEST-PO-1", [LineRequest(a, Decimal("10")), LineRequest(b, Decimal("2.5"))])

    assert order.status == "draft" and order.po_number == "TEST-PO-1"
    assert order.order_number.startswith("SO-")
    assert [ln.line_no for ln in order.lines] == [1, 2]
    for line in order.lines:
        assert line.unit_price == api.get_price("C00001", line.sku).unit_price
        assert line.line_amount == (line.quantity * line.unit_price).quantize(Decimal("0.01"))
    assert order.subtotal == sum(ln.line_amount for ln in order.lines)
    assert order.grand_total == order.subtotal + order.gst_amount  # totals come from the order_totals view


def test_duplicate_po_rejected(db, sku_catalogue):
    lines = [LineRequest(sku_catalogue["priced"][0], Decimal("1"))]
    first = api.create_draft_order("C00001", "TEST-PO-DUP", lines)
    assert api.find_order_by_po("C00001", "TEST-PO-DUP").order_number == first.order_number
    with pytest.raises(api.DuplicatePO) as err:
        api.create_draft_order("C00001", "TEST-PO-DUP", lines)
    assert err.value.existing_order_number == first.order_number


def test_find_order_by_po_missing(db):
    assert api.find_order_by_po("C00001", "NO-SUCH-PO") is None


def test_rejections_leave_nothing_behind(db, sku_catalogue):
    ok = sku_catalogue["priced"][0]
    bad_unpriced = sku_catalogue["unpriced"][0]

    with pytest.raises(api.NoContractPrice):
        api.create_draft_order("C00001", "TEST-PO-2",
                               [LineRequest(ok, Decimal("1")), LineRequest(bad_unpriced, Decimal("1"))])
    with pytest.raises(api.UnknownSku):
        api.create_draft_order("C00001", "TEST-PO-2", [LineRequest("NOPE-1", Decimal("1"))])
    if sku_catalogue["inactive"]:
        with pytest.raises(api.InactiveItem):
            api.create_draft_order("C00001", "TEST-PO-2", [LineRequest(sku_catalogue["inactive"], Decimal("1"))])
    with pytest.raises(api.CustomerNotFound):
        api.create_draft_order("C99999", "TEST-PO-2", [LineRequest(ok, Decimal("1"))])
    assert api.find_order_by_po("C00001", "TEST-PO-2") is None


@pytest.mark.parametrize("po, lines", [
    ("", [LineRequest("FST-00001", Decimal("1"))]),
    ("P", []),
    ("P", [LineRequest("FST-00001", Decimal("0"))]),
    ("P", [LineRequest("FST-00001", Decimal("1")), LineRequest("FST-00001", Decimal("2"))]),
])
def test_invalid_orders(db, po, lines):
    with pytest.raises(api.InvalidOrder):
        api.create_draft_order("C00001", po, lines)
