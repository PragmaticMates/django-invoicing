# ISDOC exporter

Exports invoices in [ISDOC](https://www.isdoc.org/) — the Czech standard XML format for electronic invoices. The resulting `.isdoc` file is delivered by email.

## Configuration

No additional configuration is required.

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.isdoc.managers.IsdocManager": {},
}
```

## Admin action

| Action name | Label |
|---|---|
| `isdocmanager_export_detail_isdoc` | Export to ISDOC |

## Exporter class

`invoicing.exporters.isdoc.managers.IsdocManager`

Override it via the `exporter_class` key:

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.isdoc.managers.IsdocManager": {
        "exporter_class": "myapp.exporters.MyCustomIsdocExporter",
    },
}
```
