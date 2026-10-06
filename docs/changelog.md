# Changelog

## Unreleased

- New optional `invoicing.einvoicing` package for structured e-invoices (Peppol BIS Billing 3.0 / EN 16931, Slovak eFaktúra). See [E-invoicing](einvoicing.md).
    - UBL 2.1 Invoice and CreditNote builder, with EN 16931 totals computed independently and reconciled against the stored ones.
    - Validation: preflight checks, UBL 2.1 XSD, Peppol BIS 3.0.21 Schematron (needs the new `einvoicing` extra, `saxonche`), unofficial Slovak rules.
    - Add `'invoicing.einvoicing'` to `INSTALLED_APPS` for idempotent sending: `EInvoiceTransmission` stores the exact XML sent, provider document ID, status, timestamps and errors; a provider interface with a generic SAPI-SK implementation.
- New `Invoice` fields `supplier_endpoint_scheme`, `supplier_endpoint_id`, `customer_endpoint_scheme`, `customer_endpoint_id`, `buyer_reference`, `vat_exemption_reason`, `vat_exemption_reason_code`, and `Item.vat_category`, all blank by default. `set_supplier_data()` / `set_customer_data()` accept `endpoint_scheme` and `endpoint_id`.

## 13.1.0

- New `INVOICING_FILL_SEQUENCE_GAPS` setting (default `False`). When enabled, the sequence generator returns the lowest unused sequence within the counter period instead of continuing after the highest one, so numbers freed up by deleted invoices get reused. A single invoice can override the setting via the `fill_sequence_gaps` instance attribute.
- New `InvoiceQuerySet.sequence_gaps()` helper listing the sequences missing from a (scoped) queryset.
- `sequence_generator()` no longer discards a legitimate sequence of `0` when resolving `INVOICING_NUMBER_START_FROM`.
- Added new invoice status `IN_COLLECTION` plus queryset helpers `.in_collection()` and `.not_in_collection()` for filtering invoices currently in collection.
- Improved MRP v2 export error handling: per-invoice XML validation failures no longer abort the whole export and are reported in the summary email, and fatal configuration errors mark the export as failed with a clear message.
- Updated exporters (PDF, XLSX, ISDOC, MRP v1, MRP v2) and managers to align with the latest `ExporterMixin` API, using `model`/`queryset` fields and queryset-based validation; managers without `required_origin` now allow mixed-origin querysets.

## 10.0.0

- Exporter classes of managers configurable via manager settings (`exporter_class`, `exporter_subclasses` keys in `INVOICING_MANAGERS`)
- Export managers refactored — shared logic consolidated in `InvoiceManagerMixin`
- New exporters: XLSX, PDF, MRP v1, MRP v2
- ISDOC exporter
- `NotExportedWithExporterListFilter` in Django Admin
- Dynamic export action registration from all configured managers
- Slovakia VAT rate updated to 23% from 2025-01-01
- ReadTheDocs configuration (`readthedocs.yaml`)
