# Peppol UBL exporter

Exports the selected invoices as [Peppol BIS Billing 3.0](https://docs.peppol.eu/poacc/billing/3.0/)
UBL documents, one XML per invoice in a zip (`invoices_peppol.zip`), delivered
by email. When the export comes down to a single file (one invoice), that file
is sent alone, not zipped. Each file is exactly what would be sent as an e-invoice; nothing is
sent anywhere. See [E-invoicing](../einvoicing.md).

Requires the `einvoicing` extra (`pip install "django-invoicing[einvoicing]"`).

## Configuration

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.peppol.managers.PeppolManager": {},
}
```

Only issued invoices can be exported (`required_origin = ISSUED`).

## What goes into the export

Every invoice is built and checked as for sending: `preflight()`, the UBL 2.1
schema and the Peppol Schematron rules (and the unofficial Slovak rules).

- Valid invoices: `<number>.xml`.
- Invoices with fatal findings are left out; their findings are listed in
  `_errors.txt`. Warnings do not keep an invoice out.

Credit notes become UBL `CreditNote` documents.

## Admin action

| Action name | Label |
|---|---|
| `peppolmanager_export_list_peppol` | Export to Peppol UBL (XML) |

## Exporter class

`invoicing.exporters.peppol.list.InvoicePeppolXmlListExporter`

Override `get_attachments(invoice)` to embed documents, e.g. the PDF
rendering, and set the subclass via `exporter_class`:

```python
# myapp/exporters.py
from invoicing.einvoicing.ubl import Attachment
from invoicing.exporters.peppol.list import InvoicePeppolXmlListExporter

class MyPeppolExporter(InvoicePeppolXmlListExporter):
    def get_attachments(self, invoice):
        return [Attachment(f'{invoice.number}.pdf', render_pdf(invoice))]
```

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.peppol.managers.PeppolManager": {
        "exporter_class": "myapp.exporters.MyPeppolExporter",
    },
}
```
