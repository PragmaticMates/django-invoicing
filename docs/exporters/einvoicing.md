# E-invoicing actions: check, send

Two admin actions that work through each invoice's provider
(`INVOICING_EINVOICING['PROVIDER_RESOLVER']`), e.g. SLOVAKODATA: *Check
e-invoice* and *Send as e-invoice (API)*. Sending is to e-invoicing what
*Export to MRP (API)* is to MRP; the [Peppol UBL exporter](peppol.md) is the
matching file export. See [E-invoicing](../einvoicing.md) for the setup.

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
| `einvoicingmanager_export_check` | Check e-invoice |
| `einvoicingmanager_export_via_api` | Send as e-invoice (API) |

## Check e-invoice

Runs every check on the selected invoices, as `services.check()` does: the
library's own (preflight, UBL schema, Peppol Schematron, Slovak rules) and the
provider's (SLOVAKODATA: its five validation levels, and whether the customer
can receive the document in Peppol). A page lists, per invoice, whether it is
valid and every finding (errors and warnings, with rule and source). Nothing is
stored or sent.

- Without a configured provider, an invoice is checked locally only, and the
  page says so.
- A provider failure (e.g. SLOVAKODATA's rate limit: 10 checks a minute on its
  MINI plan) is reported for that invoice; the others are still checked.

## Send as e-invoice

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
