# Changelog

## 10.0.0

- Exporter classes of managers configurable via manager settings (`exporter_class`, `exporter_subclasses` keys in `INVOICING_MANAGERS`)
- Export managers refactored — shared logic consolidated in `InvoiceManagerMixin`
- New exporters: XLSX, PDF, MRP v1, MRP v2
- ISDOC exporter
- `NotExportedWithExporterListFilter` in Django Admin
- Dynamic export action registration from all configured managers
- Slovakia VAT rate updated to 23% from 2025-01-01
- ReadTheDocs configuration (`readthedocs.yaml`)
