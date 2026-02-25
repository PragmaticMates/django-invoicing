# Signals & Views

## Signals

django-invoicing uses Django signals to keep the stored `total` and `vat` fields on `Invoice` in sync whenever line items change.

### `recalculate_total_by_items`

**Trigger:** `post_save` and `post_delete` on `Item`

Recalculates `invoice.total` and `invoice.vat` after any item is saved or deleted, then calls `invoice.save(update_fields=['total', 'vat'])`. This means changing a line item always propagates its financial effect to the parent invoice immediately.

### `recalculate_total_by_invoice`

**Trigger:** `pre_save` on `Invoice`

Recalculates `invoice.total` and `invoice.vat` just before the invoice is saved. This ensures that even if the invoice is saved directly (without going through item changes), the totals reflect the current item set.

!!! note
    Both `total` and `vat` are stored fields, not computed properties. They are kept accurate by these two signals working together, but they should not be edited manually.

---

## Views

### `InvoiceDetailView`

**URL:** `invoicing/invoice/detail/<pk>/` (name: `invoicing:invoice_detail`)

**Access:** Login required; user must be active or superuser.

Renders an invoice using the configured formatter class and returns the result as an `HttpResponse`. The formatter is resolved from the `INVOICING_FORMATTER` setting (default: `invoicing.formatters.html.BootstrapHTMLFormatter`).

### Formatters

| Class | Description |
|---|---|
| `invoicing.formatters.html.HTMLFormatter` | Renders `invoicing/formatters/html.html` |
| `invoicing.formatters.html.BootstrapHTMLFormatter` | Renders `invoicing/formatters/bootstrap.html` (Bootstrap-styled, default) |

To use a custom formatter, point `INVOICING_FORMATTER` at a class that implements `get_response()`:

```python
# myapp/formatters.py
from invoicing.formatters.html import HTMLFormatter


class MyFormatter(HTMLFormatter):
    template_name = 'myapp/invoice.html'

    def get_data(self):
        data = super().get_data()
        data['extra'] = 'value'
        return data
```

```python
# settings.py
INVOICING_FORMATTER = 'myapp.formatters.MyFormatter'
```

### Canonical invoice URL

By default, `invoice.get_absolute_url()` returns the URL for `InvoiceDetailView`. Override this for the whole project by setting `INVOICING_INVOICE_ABSOLUTE_URL` to a callable:

```python
INVOICING_INVOICE_ABSOLUTE_URL = lambda invoice: f'/billing/{invoice.pk}/'
```
