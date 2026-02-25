# QuerySets

Both `Invoice` and `Item` use custom QuerySet managers, accessible via `Invoice.objects` and `Item.objects`.

## InvoiceQuerySet

All methods return a filtered `QuerySet` and can be chained.

### Status / payment filters

| Method | Returns |
|---|---|
| `.paid()` | Invoices with `status=PAID` |
| `.unpaid()` | Invoices that are not paid, cancelled, credited, and have a non-zero total |
| `.overdue()` | Unpaid invoices whose `date_due` is in the past (excludes credit notes) |
| `.not_overdue()` | Invoices that are not overdue (either future due date, or in a terminal status) |

### Validity / accounting filters

| Method | Returns |
|---|---|
| `.valid()` | Excludes `RETURNED`, `CANCELED`, `CREDITED`, and `UNCOLLECTIBLE` invoices |
| `.accountable()` | Excludes proforma and advance invoices (not yet legally binding) |
| `.collectible()` | Excludes `UNCOLLECTIBLE` invoices |
| `.uncollectible()` | Only `UNCOLLECTIBLE` invoices |

### Origin filters

| Method | Returns |
|---|---|
| `.issued()` | Only `origin=ISSUED` invoices |
| `.received()` | Only `origin=RECEIVED` invoices |

### Relation filters

| Method | Returns |
|---|---|
| `.having_related_invoices()` | Invoices that have at least one related invoice |
| `.not_having_related_invoices()` | Invoices with no related invoices |

### Utilities

#### `.duplicate_numbers()`

Returns a list of invoice number strings that appear more than once in the queryset. Useful for data integrity checks.

```python
dupes = Invoice.objects.duplicate_numbers()
if dupes:
    print(f"Duplicate numbers found: {dupes}")
```

#### `.lock()`

Acquires a `SHARE ROW EXCLUSIVE` table-level lock (PostgreSQL). Called internally by the sequence generator to prevent race conditions during sequence assignment. Silently no-ops on SQLite and other backends that do not support `LOCK TABLE`.

---

## ItemQuerySet

| Method | Returns |
|---|---|
| `.with_tag(tag)` | Items whose `tag` field equals the given string |

```python
invoice.item_set.with_tag('shipping')
```
