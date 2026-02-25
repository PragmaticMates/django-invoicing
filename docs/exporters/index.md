# Exporters overview

django-invoicing ships with a pluggable export system built on top of `django-outputs`. Every export format is represented by two cooperating classes:

- **Exporter** — knows how to render a queryset of invoices into a file or API payload.
- **Manager** — owns the Django Admin action(s) and wires the exporter into the request lifecycle.

## How exports work

1. A user selects invoices in Django Admin and picks an export action.
2. `InvoiceAdmin.get_actions()` finds all `export_*` methods on every configured manager and registers them as actions.
3. The action calls the manager method (e.g. `PdfManager.export_detail_pdf()`).
4. The manager validates the queryset (must be non-empty; all invoices must share the same `origin`; some managers enforce a specific origin).
5. For file-based exports the manager calls `outputs.usecases.execute_export()`, which queues an async task and emails the result to the requesting user.
6. For API-based exports (MRP v2, IKROS, Profit365) the manager posts directly to the external service.

## Configuring managers

Managers are configured in `settings.py` via `INVOICING_MANAGERS`. The default configuration enables PDF and XLSX:

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.pdf.managers.PdfManager": {},
    "invoicing.exporters.xlsx.managers.XlsxManager": {},
}
```

Replace or extend this dict to change the active set of exporters. Each value is a manager-specific config dict.

## Available managers

| Manager | Format | Config required |
|---|---|---|
| `PdfManager` | PDF | None |
| `XlsxManager` | Excel (XLSX) | None |
| `IsdocManager` | ISDOC XML | None |
| `MrpV1Manager` | MRP XML v1 | None |
| `MrpIssuedManager` | MRP XML / API v2 (issued) | `API_URL` |
| `MrpReceivedManager` | MRP XML / API v2 (received) | `API_URL` |
| `IKrosManager` | IKROS API | `API_URL`, `API_KEY` |
| `Profit365Manager` | Profit365 API | `API_URL`, `API_DATA` |

See the individual pages for full configuration details and admin action names.
