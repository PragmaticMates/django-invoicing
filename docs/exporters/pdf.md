# PDF exporter

Exports invoices as PDF files. Each selected invoice is rendered individually and delivered by email.

## Configuration

No additional configuration is required.

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.pdf.managers.PdfManager": {},
}
```

## Admin action

| Action name | Label |
|---|---|
| `pdfmanager_export_detail_pdf` | Export to PDF |

## Exporter class

`invoicing.exporters.pdf.detail.InvoicePdfDetailExporter`

Override it via the `exporter_class` key:

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.pdf.managers.PdfManager": {
        "exporter_class": "myapp.exporters.MyCustomPdfExporter",
    },
}
```
