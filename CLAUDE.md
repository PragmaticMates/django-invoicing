# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements-test.txt

# Run all tests
pytest

# Run a single test file
pytest invoicing/tests/test_models.py

# Run a single test
pytest invoicing/tests/test_models.py::TestInvoice::test_something

# Run tests by marker
pytest -m unit
pytest -m "not slow"

# Run linting
flake8
black --check .
isort --check .
```

Tests use SQLite in-memory (`':memory:'`) with `--nomigrations` and `--reuse-db`. Settings are at `invoicing/tests/test_settings.py`.

## Architecture

This is a reusable Django app (`invoicing`) for invoice management with pluggable export backends.

### Core Models (`invoicing/models.py`)

- **`Invoice`**: Central model. Key fields: `type` (INVOICE/ADVANCE/PROFORMA/CREDIT_NOTE), `origin` (ISSUED/RECEIVED), `status`, `sequence`, `number`. Stores full denormalized supplier/customer/bank data as flat fields. `total` and `vat` are stored fields that must be explicitly saved (not auto-updated).
- **`Item`**: Line items on an invoice. `tax_rate` can be null (no-tax / reverse charge). Saving an `Item` with a non-null `tax_rate` when the invoice has no `supplier_vat_id` raises `ValueError`.

### Sequence & Number Generation

On `Invoice.save()`, if `sequence` is blank it's auto-generated via `INVOICING_SEQUENCE_GENERATOR` (default: `invoicing.helpers.sequence_generator`), then `number` is generated via `INVOICING_NUMBER_FORMATTER` (default: `invoicing.helpers.number_formatter`). The number format is a Django template string set in `INVOICING_NUMBER_FORMAT` (default: `"{{ invoice.date_issue|date:'Y' }}/{{ invoice.sequence }}"`).

### Taxation (`invoicing/taxation/`)

`TaxationPolicy` provides base logic. `EUTaxationPolicy` handles EU VAT rules including reverse charge. The active policy is resolved per-invoice: if `INVOICING_TAXATION_POLICY` is set in settings it's used; otherwise EU policy is used for EU suppliers; otherwise default tax from `INVOICING_TAX_RATE`.

### Exporters (`invoicing/exporters/`)

Each export format has a `managers.py` with a Manager class and an exporter class (detail/list). Managers inherit from `InvoiceManagerMixin` and expose methods named `export_*` that become Django admin actions automatically.

Available exporters:
- `pdf/` — PDF via `InvoicePdfDetailExporter`
- `xlsx/` — Excel spreadsheet
- `isdoc/` — Czech ISDOC XML format
- `mrp/v1/` — MRP XML export (file-based)
- `mrp/v2/` — MRP API export (issued and received variants)
- `ikros/` — IKROS API integration (Slovak accounting)
- `profit365/` — Profit365 API integration

Exports are asynchronous: `InvoiceManagerMixin._execute_export()` calls `outputs.usecases.execute_export()` (from `django-outputs` package), which queues the export and emails the result. All exports require `outputs` app in `INSTALLED_APPS`.

### Manager Configuration (`invoicing/settings.py`)

`INVOICING_MANAGERS` dict in Django settings maps manager dotted paths to their config. Default includes only `PdfManager` and `XlsxManager`. Per-manager config supports `exporter_class` and `exporter_subclasses` keys to override the default exporter class via dotted import paths.

### Admin Integration (`invoicing/admin.py`)

`InvoiceAdmin.get_actions()` dynamically discovers all `export_*` methods from every configured manager and adds them as admin actions. Action names are `{manager_class_name_lower}_{method_name}`. The `NotExportedWithExporterListFilter` lets admins filter invoices not yet exported with a specific exporter.

### Key Django Settings

| Setting | Default | Purpose |
|---|---|---|
| `INVOICING_MANAGERS` | `{PdfManager: {}, XlsxManager: {}}` | Active export managers |
| `INVOICING_SUPPLIER` | — | Default supplier data dict |
| `INVOICING_COUNTER_PERIOD` | `YEARLY` | Sequence counter reset period |
| `INVOICING_NUMBER_FORMAT` | `Y/sequence` | Django template for invoice number |
| `INVOICING_NUMBER_START_FROM` | `1` | First sequence number |
| `INVOICING_COUNTER_PER_TYPE` | `False` | Separate sequences per invoice type |
| `INVOICING_TAXATION_POLICY` | EU auto-detect | Dotted path to taxation policy class |
| `INVOICING_TAX_RATE` | — | Default tax rate (Decimal) |
| `INVOICING_SEQUENCE_GENERATOR` | `invoicing.helpers.sequence_generator` | Dotted path to sequence generator |
| `INVOICING_NUMBER_FORMATTER` | `invoicing.helpers.number_formatter` | Dotted path to number formatter |
