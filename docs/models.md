# Invoice & Item models

## Invoice

`invoicing.models.Invoice` — the central model. All supplier, customer, bank, and shipping data is stored as **denormalized flat fields** directly on the invoice record. This ensures the invoice snapshot never changes even if the underlying contact data changes.

### Type choices

| Value | Meaning |
|---|---|
| `INVOICE` | Standard tax invoice |
| `ADVANCE` | Advance invoice (prepayment request) |
| `PROFORMA` | Proforma invoice (non-binding) |
| `CREDIT_NOTE` | Credit note (partial or full reversal) |

### Origin choices

| Value | Meaning |
|---|---|
| `ISSUED` | Invoice issued by the supplier (outgoing) |
| `RECEIVED` | Invoice received from a supplier (incoming) |

### Status choices

| Value | Meaning |
|---|---|
| `NEW` | Freshly created, not yet sent |
| `SENT` | Delivered to the customer |
| `RETURNED` | Returned by the customer |
| `CANCELED` | Voided |
| `PAID` | Payment received |
| `CREDITED` | Replaced by a credit note |
| `IN_COLLECTION` | Sent to collection / debt recovery |
| `UNCOLLECTIBLE` | Written off as bad debt |

`date_sent` and `date_paid` are `MonitorField` values — they are set automatically when `status` transitions to `SENT` or `PAID`.

### Payment method choices

`BANK_TRANSFER`, `CASH`, `CASH_ON_DELIVERY`, `PAYMENT_CARD`

### Counter period choices

`DAILY`, `MONTHLY`, `YEARLY`, `INFINITE` — controls the scope of the auto-incremented sequence.

### Key fields

| Field | Notes |
|---|---|
| `sequence` | Auto-assigned integer; scope determined by `INVOICING_COUNTER_PERIOD` |
| `number` | Human-readable string rendered from `INVOICING_NUMBER_FORMAT` |
| `total` | Stored Decimal, recalculated by signal on every `Item` save/delete and on `Invoice.pre_save` |
| `vat` | Stored Decimal, same lifecycle as `total`; `None` means "not applicable" |
| `credit` | Amount to subtract from the subtotal (e.g. advance payment credit) |
| `already_paid` | Amount already received; use `invoice.to_pay` for the remaining balance |
| `attachments` | JSONField for arbitrary attachment metadata |
| `related_invoices` | ManyToMany self-reference; populated automatically by `create_copy()` |

### Computed properties

| Property | Description |
|---|---|
| `is_overdue` | `True` if unpaid and `date_due` is in the past |
| `overdue_days` | Number of days past the due date |
| `days_to_overdue` | Number of days until the due date (negative if overdue) |
| `payment_term` | `(date_due - date_issue).days` |
| `subtotal` | Sum of item subtotals minus `credit` |
| `discount` | Total discount amount across all items |
| `total_before_discount` | `total + discount + credit` |
| `to_pay` | `total - already_paid` |
| `vat_summary` | List of dicts `{rate, base, vat}` grouped by tax rate; computed via raw SQL |
| `has_discount` | `True` if any item has a non-zero discount |
| `has_unit` | `True` if items use mixed or non-empty units |
| `taxation_policy` | Resolved `TaxationPolicy` class for this invoice |

### Methods

#### `Invoice.save()`

On first save (when `sequence` is blank):

1. `get_next_sequence()` is called to assign `sequence` (uses a table-level lock on PostgreSQL).
2. `_get_number()` is called to render `number` from the template.

Subsequent saves do not reassign sequence or number.

#### `Invoice.create_copy(**kwargs)`

Creates a full copy of the invoice including all items. The new invoice gets a fresh sequence and number. The original invoice is added to `new_invoice.related_invoices`.

```python
credit_note = invoice.create_copy(
    type=Invoice.TYPE.CREDIT_NOTE,
    date_issue=today,
    date_tax_point=today,
    date_due=today,
)
```

Any `kwargs` are applied to the new instance before saving, allowing you to override any field.

#### `Invoice.set_supplier_data(supplier_dict)` / `set_customer_data()` / `set_shipping_data()`

Convenience methods that copy a settings-style dict into the corresponding denormalized fields.

#### `Invoice.recalculate_tax()`

Iterates over all items, calls `item.calculate_tax()`, and saves each item. This triggers the signal that recalculates `total` and `vat` on the invoice.

---

## Item

`invoicing.models.Item` — a line item belonging to an `Invoice`.

### Key fields

| Field | Notes |
|---|---|
| `invoice` | FK to `Invoice` (CASCADE delete) |
| `title` | Description of the item (TextField) |
| `quantity` | Decimal, minimum 0.001 |
| `unit` | `EMPTY`, `PIECES`, `HOURS` |
| `unit_price` | Price per unit, before discount and VAT |
| `discount` | Discount percentage (0–100) |
| `tax_rate` | VAT rate percentage; `None` means no tax or reverse charge |
| `tag` | Optional string for grouping/filtering items |
| `weight` | Integer ordering field |

!!! warning "Validation on save"
    Saving an `Item` with a non-`None` `tax_rate` when the parent invoice has no `supplier_vat_id` raises a `ValueError`. A supplier VAT ID is required to charge VAT.

### Computed properties

| Property | Formula |
|---|---|
| `subtotal` | `unit_price × quantity × (1 - discount/100)` |
| `subtotal_before_discount` | `unit_price × quantity` |
| `discount_amount` | Discount in currency units (based on `unit_price_with_vat`) |
| `vat` | `subtotal × tax_rate / 100` (0 if no tax rate) |
| `unit_price_with_vat` | `unit_price × (1 + tax_rate/100)` |
| `total` | `subtotal + vat` |
| `total_before_discount` | `subtotal_before_discount + vat_before_discount` |

### `Item.calculate_tax()`

Sets `self.tax_rate` by calling `invoice.get_tax_rate()`. Call this before saving to apply the invoice's taxation policy to the item.
