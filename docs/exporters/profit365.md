# Profit365 exporter

Pushes invoices to the [Profit365](https://www.profit365.eu/) accounting REST API. Each invoice is sent as a **separate** `POST` request to `{API_URL}/sales/invoices`.

## Configuration

```python
INVOICING_MANAGERS = {
    "invoicing.exporters.profit365.managers.Profit365Manager": {
        "API_URL": "https://api.profit365.eu/1.6",
        "API_DATA": {
            "Authorization": "Bearer your-token",
            "bankAccountId": "12345",
            "ClientID": "your-client-id",
            "ClientSecret": "your-client-secret",
            "CompanyID": "your-company-id",   # optional
        },
    },
}
```

| Key | Required | Description |
|---|---|---|
| `API_URL` | Yes | Profit365 API base URL |
| `API_DATA.Authorization` | Yes | Full `Authorization` header value (e.g. `Bearer <token>`) |
| `API_DATA.bankAccountId` | Yes | Bank account identifier in Profit365 |
| `API_DATA.ClientID` | Yes | OAuth client ID |
| `API_DATA.ClientSecret` | Yes | OAuth client secret |
| `API_DATA.CompanyID` | No | Company ID; added as a header when present |

## Admin action

| Action name | Label |
|---|---|
| `profit365manager_export_via_api` | Export to Profit365 (API) |

## Behaviour

- One `POST` request is made per invoice. A summary of results is logged and displayed in Admin messages.
- The `partnerAddress` field is built from customer name, address, and tax identifiers, joined with `\r\n`. The language of the identifier labels follows the invoice's `language` field via `translation.override`.
- Canceled invoices set `description='STORNO'` and `commentBelowItems='STORNO 2'` with no line items.
- Items with a non-zero `discount` include `discountPercent`.

## Field mapping

| Profit365 field | Invoice field |
|---|---|
| `recordNumber` | `number` |
| `bankAccountId` | `API_DATA.bankAccountId` |
| `dateCreated` | `date_issue` |
| `dateAccounting` | `date_tax_point` |
| `dateValidTo` | `date_due` |
| `symbolVariable` | `variable_symbol` |
| `symbolSpecific` | `specific_symbol` |
| `symbolConstant` | `constant_symbol` |
| `localCurrencyID` / `currencyID` | `currency` |
| `issuedBy` | `issuer_name` |
