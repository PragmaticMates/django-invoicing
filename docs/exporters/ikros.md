# IKROS exporter

Pushes invoices directly to the [IKROS](https://www.inteo.sk/) accounting REST API (Slovak). Invoices are sent synchronously, one batch per admin action invocation.

## Configuration

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.ikros.managers.IKrosManager": {
        "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
        "API_KEY": "your-api-key-here",
    },
}
```

| Key | Required | Description |
|---|---|---|
| `API_URL` | Yes | IKROS API endpoint URL |
| `API_KEY` | Yes | Bearer token for `Authorization` header |

## Admin action

| Action name | Label |
|---|---|
| `ikrosmanager_export_via_api` | Export to IKROS (API) |

## Behaviour

- All selected invoices are serialized to a JSON array and sent as a single `POST` request.
- If the response contains a `message` field, the export is considered failed and the message is shown as a Django Admin error.
- On success, a download URL from `response['documents'][0]['downloadUrl']` is shown as a clickable link in the Admin message bar.
- Canceled invoices are sent with `count=0`, `unitPrice=0`, and `closingText='STORNO'`.
- Invoices with a non-zero `credit` field have `hasDiscount=True` and `discountValue=-credit` applied to the first line item.

## Field mapping

| IKROS field | Invoice field |
|---|---|
| `documentNumber` | `number` |
| `createDate` | `date_issue` |
| `dueDate` | `date_due` |
| `completionDate` | `date_tax_point` |
| `clientName` | `customer_name` |
| `clientRegistrationId` | `customer_registration_id` |
| `clientTaxId` | `customer_tax_id` |
| `clientVatId` | `customer_vat_id` |
| `variableSymbol` | `variable_symbol` |
| `currency` | `currency` |
