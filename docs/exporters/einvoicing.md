# Send as e-invoice (API)

An admin action that sends the selected invoices as e-invoices through their
provider (`INVOICING_EINVOICING['PROVIDER_RESOLVER']`), e.g. SLOVAKODATA. It is
to e-invoicing what *Export to MRP (API)* is to MRP; the
[Peppol UBL exporter](peppol.md) is the matching file export. See
[E-invoicing](../einvoicing.md) for the setup.

Requires `'invoicing.einvoicing'` in `INSTALLED_APPS` and a configured provider.

## Configuration

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.einvoicing.managers.EInvoicingManager": {},
}
```

## Admin action

| Action name | Label |
|---|---|
| `einvoicingmanager_export_via_api` | Send as e-invoice (API) |

## Behaviour

A sent e-invoice cannot be taken back, so nothing is sent straight away:

1. A **confirmation page** lists the selected invoices, with their customer,
   total and provider, and whether each **will be sent** or **will not be
   sent**, and why: not issued, already sent (with its status), no provider
   configured, blocked by `send_blocked_reason()` (status not in
   `SENDABLE_STATUSES`, no customer electronic address, the provider would
   refuse it), or failing the preflight checks.
2. **Yes, send** sends those that can be, each as `services.send()` does:
   validated (including the provider's own validation), stored, and submitted
   in the background. A message reports how many were queued, and why any
   were not.

The statuses then follow by webhook and polling, and appear in the invoice
list's *e-invoice* column.
