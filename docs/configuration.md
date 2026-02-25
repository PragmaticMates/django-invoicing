# Configuration

All settings live in your Django `settings.py` under names prefixed with `INVOICING_`.

## Supplier defaults

```python
INVOICING_SUPPLIER = {
    'name': 'Acme Ltd.',          # required
    'street': 'Main Street 1',
    'city': 'Springfield',
    'zip': '12345',
    'country_code': 'SK',         # ISO 3166-1 alpha-2
    'registration_id': '12345678',
    'tax_id': '2012345678',
    'vat_id': 'SK2012345678',
    'additional_info': None,      # optional JSON-serialisable dict
    'bank': {
        'name': 'Good Bank',
        'street': 'Bank Street 1',
        'city': 'Springfield',
        'zip': '12345',
        'country_code': 'SK',
        'iban': 'SK0000000000000000000028',
        'swift_bic': 'GOODBANK',
    },
}
```

When a new `Invoice` is saved, `Invoice.set_supplier_data()` copies these values into the denormalized supplier fields on the invoice. Changes to `INVOICING_SUPPLIER` do **not** retroactively affect saved invoices.

## Sequence & numbering

| Setting | Default | Description |
|---|---|---|
| `INVOICING_COUNTER_PERIOD` | `'YEARLY'` | Reset the sequence counter every `DAILY`, `MONTHLY`, `YEARLY`, or never (`INFINITE`) |
| `INVOICING_NUMBER_START_FROM` | `1` | First sequence number issued within a counter period |
| `INVOICING_COUNTER_PER_TYPE` | `False` | If `True`, each invoice type (`INVOICE`, `ADVANCE`, …) has its own independent counter |
| `INVOICING_NUMBER_FORMAT` | `"{{ invoice.date_issue\|date:'Y' }}/{{ invoice.sequence }}"` | Django template string used to render the human-readable invoice number |
| `INVOICING_SEQUENCE_GENERATOR` | `'invoicing.helpers.sequence_generator'` | Dotted path to a callable that returns the next integer sequence |
| `INVOICING_NUMBER_FORMATTER` | `'invoicing.helpers.number_formatter'` | Dotted path to a callable that returns the formatted invoice number string |

### Custom number format

The number format is a standard Django template rendered with a single context variable `invoice`:

```python
# Generates numbers like "2024-001", "2024-002", ...
INVOICING_NUMBER_FORMAT = "{{ invoice.date_issue|date:'Y' }}-{{ invoice.sequence|stringformat:'03d' }}"
```

### Custom sequence generator

Supply a dotted path to any callable with the following signature:

```python
def my_sequence_generator(type, important_date, number_prefix=None,
                           counter_period=None, related_invoices=None,
                           start_from=None):
    ...
    return next_integer
```

```python
INVOICING_SEQUENCE_GENERATOR = 'myapp.invoicing.my_sequence_generator'
```

### Custom number formatter

Supply a dotted path to any callable that accepts an `Invoice` instance and returns a string:

```python
def my_number_formatter(invoice):
    return f"INV-{invoice.date_issue.year}-{invoice.sequence:04d}"
```

```python
INVOICING_NUMBER_FORMATTER = 'myapp.invoicing.my_number_formatter'
```

## Taxation

| Setting | Default | Description |
|---|---|---|
| `INVOICING_TAX_RATE` | `None` | Default tax rate (`Decimal`) used when no policy resolves a rate |
| `INVOICING_TAXATION_POLICY` | EU auto-detect | Dotted path to a `TaxationPolicy` subclass |
| `INVOICING_USE_VIES_VALIDATOR` | `True` | Whether to validate customer VAT IDs against the EU VIES service for reverse-charge decisions |

See [Taxation](taxation.md) for details.

## Invoice detail view

| Setting | Default | Description |
|---|---|---|
| `INVOICING_FORMATTER` | `'invoicing.formatters.html.BootstrapHTMLFormatter'` | Dotted path to the formatter class used by `InvoiceDetailView` |
| `INVOICING_INVOICE_ABSOLUTE_URL` | Built-in URL | Callable `(invoice) -> str` that returns the canonical URL for an invoice |
| `INVOICING_INVOICE_ITEM_ABSOLUTE_URL` | `lambda item: ''` | Callable `(item) -> str` that returns the canonical URL for an invoice item |

## VAT visibility

| Setting | Default | Description |
|---|---|---|
| `INVOICING_IS_SUPPLIER_VAT_ID_VISIBLE` | Built-in logic | Callable `(invoice) -> bool` that controls whether the supplier VAT ID is shown on the invoice |

## Export managers

```python
INVOICING_MANAGERS = {
    # key: dotted path to manager class
    # value: manager-specific config dict
    "invoicing.exporters.pdf.managers.PdfManager": {},
    "invoicing.exporters.xlsx.managers.XlsxManager": {},
}
```

By default only `PdfManager` and `XlsxManager` are enabled. Add any combination of the available managers. See [Exporters](exporters/index.md) for per-manager configuration options.

### Overriding exporter classes

Each manager accepts two optional keys that replace the built-in exporter classes:

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.pdf.managers.PdfManager": {
        "exporter_class": "myapp.exporters.CustomPdfExporter",
    },
    "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {
        "exporter_class": "invoicing.exporters.mrp.v1.list.InvoiceXmlMrpListExporter",
        "exporter_subclasses": [
            "invoicing.exporters.mrp.v1.list.InvoiceFakvyXmlMrpExporter",
            "invoicing.exporters.mrp.v1.list.InvoiceFakvypolXmlMrpExporter",
            "invoicing.exporters.mrp.v1.list.InvoiceFvAdresXmlMrpExporter",
        ],
    },
}
```

| Key | Description |
|---|---|
| `exporter_class` | Dotted import path to the main exporter class |
| `exporter_subclasses` | List of dotted import paths to exporter subclasses (used by some managers, e.g. MRP v1) |
