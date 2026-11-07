# Labelling rules: extraction golden set v1

These rules define what "correct" means. When a new email is ambiguous, decide the rule here first, then label.

## Output shape

Each email maps to an `ExtractionResult`: `{"purchase_orders": [PurchaseOrder, ...]}`.

- **Zero POs:** RFQs, payment advices, amendments to existing POs, anything that isn't a new order (po_012, po_013, po_022).
- **Several POs:** one entry per PO number (po_011).

Small adjustments to the `po.v1` schema from the guide: it is wrapped in `ExtractionResult` (replacing `is_purchase_order`), and `description` is optional.

## Field rules

| Field | Rule |
|---|---|
| `po_number` | Exactly as written, including slashes and prefixes. `null` if absent ("will follow" counts as absent). |
| `customer_name_as_written` | The **buyer**, as written, even when someone else sends the email (po_021). Don't normalise. |
| `order_date` | The PO date stated in the body, ISO format. Indian DD/MM by default. Year missing: take it from the email header. No date in the body: `null` (don't use the header date). |
| `currency` | `INR` unless the email clearly states otherwise. |
| `sku_as_written` | Exactly as written, **including typos** (po_006 keeps `VLV-2O4`). |
| `description` | As written in the email; `null` if none. Scored loosely (fuzzy match), not exact. |
| `quantity` | A number. Convert words: "2 dozen" = 24, "half dozen" = 6. Revised quantities in a thread override the original (po_010). |
| `unit_price` | As written, per unit. `null` if not stated ("as per rate contract", "same rate as last time"). |
| `stated_total` | The pre-tax total **as written**, even if it's wrong or stale. `null` if not stated. |

## Resolution (done by code, not the model)

`resolution` gives the customer ID and item IDs that business rules should resolve to. `null` means no match in master data.

## Issue codes

| Code | Fires when | May be an extraction error? |
|---|---|---|
| `UNKNOWN_CUSTOMER` | Buyer not in customer master | No |
| `MISSING_PO_NUMBER` | No PO number in the email | No |
| `UNKNOWN_SKU` | SKU not in item master | Yes (could be a misread) |
| `SKU_FUZZY_MATCH` | SKU only matches after fuzzy correction | Yes |
| `PRICE_MISMATCH` | Unit price differs from customer price list by more than 1% | No: real discrepancy, don't retry |
| `TOTAL_MISMATCH` | Stated total differs from sum of lines by more than Rs. 1 | Yes |

All v1 issues have severity `review`. Price checks are skipped for unknown customers and unknown SKUs.

## Cases worth knowing

- **po_003:** "Acme Process Equip." resolves to C003, not C031 Apex Pharma Engineering. The reference customers file includes C031 for this reason.
- **po_010:** the stated total is from the original PO, before the quantity revision, so `TOTAL_MISMATCH` is the correct outcome.
- **po_023:** contains an instruction aimed at automated systems. Prices are correct, so no issue fires. The order must still be a draft and still validated (seed case for Project 11).
- **po_025:** numbers in the terms and conditions must not leak into line items.
