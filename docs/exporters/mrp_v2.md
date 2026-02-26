# MRP v2 exporter

Integrates with the MRP accounting system REST API (Czech). There are two separate managers — one for issued invoices and one for received invoices — because the MRP API endpoint and document structure differ between the two origins.

Each manager exposes **two** admin actions:

- An XML file export (email delivery, same as v1).
- A direct API push to the MRP server.

## Configuration

Both managers require `API_URL`.

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.mrp.v2.managers.MrpIssuedManager": {
        "API_URL": "https://your-mrp-instance.example.com/api/",
    },
    "invoicing.exporters.mrp.v2.managers.MrpReceivedManager": {
        "API_URL": "https://your-mrp-instance.example.com/api/",
    },
}
```

## Admin actions

### MrpIssuedManager

| Action name | Label | Description |
|---|---|---|
| `mrpissuedmanager_export_list_issued_mrp` | Export issued to MRP v2 (XML) | Generates XML and delivers by email |
| `mrpissuedmanager_export_via_api` | Export issued to MRP (API) | POSTs invoices directly to the MRP API |

!!! note "Origin restriction"
    `MrpIssuedManager` only accepts invoices with `origin=ISSUED`. Mixing issued and received invoices in the same export will produce a validation warning and abort.

### MrpReceivedManager

| Action name | Label | Description |
|---|---|---|
| `mrpreceivedmanager_export_list_received_mrp` | Export received to MRP v2 (XML) | Generates XML and delivers by email |
| `mrpreceivedmanager_export_via_api` | Export received to MRP (API) | POSTs invoices directly to the MRP API |

!!! note "Origin restriction"
    `MrpReceivedManager` only accepts invoices with `origin=RECEIVED`.

## API export internals

The API export path uses `outputs.models.Export` with `output_type=OUTPUT_TYPE_STREAM` and delegates to a Celery task (`invoicing.exporters.mrp.v2.tasks.send_invoices_to_mrp`). Make sure Celery is configured and running for API exports to work.

Invoices are processed **one by one**. If a particular invoice fails XML generation or XSD validation, it is skipped, marked as a failure, and included in the summary email, while the rest of the invoices continue to be sent. Only fatal errors (for example, missing exporter configuration) abort the whole export; in that case the export is marked as failed and the email contains the fatal error message.

## Exporter classes

| Manager | Exporter class |
|---|---|
| `MrpIssuedManager` | `invoicing.exporters.mrp.v2.list.IssuedInvoiceMrpListExporter` |
| `MrpReceivedManager` | `invoicing.exporters.mrp.v2.list.ReceivedInvoiceMrpListExporter` |
