# MRP v1 exporter

Exports invoices as MRP XML v1 files for import into the MRP accounting system (Czech). The export produces a ZIP archive containing XML files and is delivered by email.

The v1 exporter uses a list-based exporter with three XML sub-exporters for different MRP document types:

- `InvoiceFakvyXmlMrpExporter` — issued invoices (`FAKVY`)
- `InvoiceFakvypolXmlMrpExporter` — invoice line items (`FAKVYPOL`)
- `InvoiceFvAdresXmlMrpExporter` — customer address records (`FVADRES`)

## Configuration

No additional configuration is required.

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {},
}
```

## Admin action

| Action name | Label |
|---|---|
| `mrpv1manager_export_list_mrp` | Export to MRP v1 (XML) |

## Exporter classes

| Class | Dotted path |
|---|---|
| Main list exporter | `invoicing.exporters.mrp.v1.list.InvoiceXmlMrpListExporter` |
| FAKVY sub-exporter | `invoicing.exporters.mrp.v1.list.InvoiceFakvyXmlMrpExporter` |
| FAKVYPOL sub-exporter | `invoicing.exporters.mrp.v1.list.InvoiceFakvypolXmlMrpExporter` |
| FVADRES sub-exporter | `invoicing.exporters.mrp.v1.list.InvoiceFvAdresXmlMrpExporter` |

Override any of them via `exporter_class` / `exporter_subclasses`:

```python
INVOICING_MANAGERS = {
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
