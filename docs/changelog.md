# Changelog

## Unreleased

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
