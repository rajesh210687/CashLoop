"""The ERP must contain the golden set's reference data unchanged.

If the seed regenerates any of these rows, every price and resolution check in
the golden set breaks. These tests read evals/extraction/reference/*.csv and the
gold labels, and compare them with what erp.api returns.
"""

from decimal import Decimal

import pytest

from erp import api


def test_reference_customers_match(db, reference):
    for row in reference["customers"]:
        [c] = api.get_customer(row["customer_id"])
        assert c.legal_name == row["name"], row["customer_id"]
        assert (c.city, c.state, c.currency, c.tier) == (row["city"], row["state"], row["currency"], row["tier"])
        assert c.gstin == (row["gstin"] or None)
        assert c.payment_terms_days == int(row["payment_terms"].split()[-1])
        assert c.is_active


def test_reference_items_match(db, reference):
    for row in reference["items"]:
        item = api.get_item(row["sku"])
        assert item.description == row["description"], row["sku"]
        assert item.uom == row["unit"]
        assert item.base_price == Decimal(row["base_price_inr"])
        assert item.is_active


def test_reference_prices_match(db, reference):
    for row in reference["prices"]:
        price = api.get_price(row["customer_id"], row["sku"])
        assert price.source == "contract", (row["customer_id"], row["sku"])
        assert price.unit_price == Decimal(row["unit_price"]), (row["customer_id"], row["sku"])
        assert price.currency == row["currency"]


def test_gold_resolutions_agree_with_erp(db, gold):
    """Every customer/SKU a gold file resolves to exists; every 'no match' really has none."""
    checked = 0
    for g in gold:
        pos = g["expected"]["purchase_orders"]
        for po, res in zip(pos, g["resolution"]):
            if res["customer_id"] is None:
                assert api.get_customer(po["customer_name_as_written"]) == [], g["email_id"]
            else:
                assert [c.customer_code for c in api.get_customer(res["customer_id"])] == [res["customer_id"]]
            for line, item_id in zip(po["line_items"], res["line_item_ids"]):
                if item_id is None:
                    with pytest.raises(api.UnknownSku):
                        api.get_item(line["sku_as_written"])
                else:
                    api.get_item(item_id)
                checked += 1
    assert checked > 0


def test_gold_po_numbers_are_not_already_in_erp(db, gold):
    """A golden email is a NEW order; the seed must not already hold its PO number."""
    for g in gold:
        for po, res in zip(g["expected"]["purchase_orders"], g["resolution"]):
            if po["po_number"] and res["customer_id"]:
                assert api.find_order_by_po(res["customer_id"], po["po_number"]) is None, g["email_id"]
