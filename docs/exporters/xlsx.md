# XLSX exporter

Exports invoices as an Excel spreadsheet (`.xlsx`). All selected invoices are written to a single workbook and delivered by email.

## Configuration

No additional configuration is required.

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.xlsx.managers.XlsxManager": {},
}
```

## Admin action

| Action name | Label |
|---|---|
| `xlsxmanager_export_list_xlsx` | Export to XLSX |

## Exporter class

`invoicing.exporters.xlsx.managers.XlsxManager`

Override it via the `exporter_class` key:

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.xlsx.managers.XlsxManager": {
        "exporter_class": "myapp.exporters.MyCustomXlsxExporter",
    },
}
```
