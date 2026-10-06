# E-invoicing (Peppol BIS Billing 3.0)

`invoicing.einvoicing` turns an `Invoice` into a structured electronic invoice:
a UBL 2.1 document compliant with [Peppol BIS Billing 3.0](https://docs.peppol.eu/poacc/billing/3.0/)
(EN 16931), as required for Slovak eFaktúra from 2027.

It is split into layers. Only the last one talks to the network, through a
replaceable provider:

```
Invoice ─▶ calculations ─▶ ubl (builder) ─▶ validation ─▶ services ─▶ EInvoiceProvider ─▶ Peppol
```

The first three work without installing anything; sending needs
`'invoicing.einvoicing'` in `INSTALLED_APPS` (it adds two tables).

## Installation

```bash
pip install django-invoicing[einvoicing]   # adds saxonche, for the Schematron rules
```

## Usage

```python
from invoicing.einvoicing.ubl import Attachment, get_builder
from invoicing.einvoicing.validation import preflight, validate

report = preflight(invoice)          # can this invoice become a correct e-invoice?
if report.is_valid:
    xml = get_builder(invoice, attachments=[Attachment('2026-001.pdf', pdf_bytes)]).build()
    report = validate(xml)           # UBL XSD + Peppol Schematron + Slovak rules
```

Both checks return a `ValidationReport`: `errors` (fatal: do not send),
`warnings`, `is_valid` and `as_dict()`.

## Data the invoice needs

| Field | EN 16931 | Notes |
|---|---|---|
| `supplier_endpoint_scheme` / `supplier_endpoint_id` | BT-34 | Peppol ID of the seller; Slovak businesses use `0245` + DIČ |
| `customer_endpoint_scheme` / `customer_endpoint_id` | BT-49 | Peppol ID of the buyer |
| `buyer_reference` | BT-10 | Falls back to the invoice number |
| `Item.vat_category` | BT-151 | Blank derives it: rate > 0 is `S`, 0 is `Z`, no rate without supplier VAT ID is `O`. A VAT payer's item without a rate (reverse charge, exemption) has to set it |
| `vat_exemption_reason` / `_code` | BT-120/121 | Required for `E`; `AE`, `K`, `G`, `O` default to their VATEX code |
| `supplier_additional_info['legal_form']`, `['register']` | BT-33 | Seller legal form and commercial register entry |

`set_supplier_data()` and `set_customer_data()` accept `endpoint_scheme` and `endpoint_id`.

Proforma and advance invoices are not tax documents and are refused. Credit
notes become a UBL `CreditNote` referring to their `related_invoices` (or
`related_document`). The `credit` deduction has no EN 16931 equivalent, so an
invoice with credit is refused.

## Totals and rounding

`calculations.compute_for_invoice(invoice)` computes the totals the e-invoice
declares, half-up to the cent: every line first, then VAT once per category
and rate (BR-CO-10 to BR-CO-17).

The stored `Invoice.total` is computed differently and can be a cent off.
Rather than silently declare a different amount than the invoice (and its PDF)
shows, `preflight()` refuses it (`PREFLIGHT-TOTALS`).

## Validation

1. `preflight(invoice)`: data present, supported type and currency, VAT categories resolvable, totals matching
2. UBL 2.1 XSD
3. Peppol BIS Billing 3.0.21 Schematron: CEN EN 16931 rules and Peppol rules (artefacts 1.3.16), run on Saxon-HE
4. Slovak national rules, `SK-LOCAL-*`

!!! warning "The Slovak rules are unofficial"
    The Financial Administration publishes its national requirements only as a
    human-readable table, with no rule IDs or Schematron. `SK-LOCAL-*` are this
    library's reading of that table.

The vendored artefacts and their versions are listed in
`invoicing/einvoicing/validation/artefacts/README.md`.

## Identifiers

`identifiers.document_uuid()` computes the deterministic document UUID of
Slovak rule ID-BDID-01 (seller endpoint scheme and ID, type code, number and
issue date). The namespace comes from the Solution Architecture v1.2, whose
example it reproduces. The FS transposition table v1.11 quotes a different
namespace whose own example does not verify.

## Sending

```python
from invoicing.einvoicing import services

transmission = services.prepare(invoice, attachments=[...])  # build + validate + store; raises EInvoiceValidationError
services.submit(transmission)                                 # safe to retry
services.refresh_status(transmission)                         # if the provider can report status
```

`EInvoiceTransmission` keeps, per attempt, the exact XML sent (and its
SHA-256), the validation report, the provider document ID, the status, the
timestamps, the last error, and an append-only log of events.

Sending is idempotent:

- The XML is built once and stored before any network call. Every
  resubmission sends exactly those bytes with the same `Idempotency-Key`, so a
  timeout or crash followed by a retry cannot create a second document.
- An invoice has at most one live or successful transmission, enforced by a
  conditional unique constraint; `prepare()` returns it instead of creating
  another. A new attempt is possible only after one ended `REFUSED`,
  `REJECTED`, `UNDELIVERABLE`, `FAILED` or `CANCELLED`.
- A transmitted invoice cannot be deleted (`on_delete=PROTECT`), so its
  number, which identifies the document in Peppol, is never reused.

| Status | Meaning |
|---|---|
| `PREPARED` | Stored, not yet sent |
| `SUBMITTING` | Being sent; resubmittable after `SUBMITTING_TIMEOUT_SECONDS` |
| `SUBMIT_UNKNOWN` | Timeout or retryable error: resubmit (same key, same bytes) |
| `CONFLICT` | HTTP 409: the provider may already hold the document; needs a human |
| `REFUSED` | The provider did not take it (invalid, no credit, ...) |
| `SUBMITTED` | The provider has it |
| `DELIVERED`, `DELIVERED_NON_PEPPOL`, `ACCEPTED`, `UNCONFIRMED` | Reached the recipient (or the tax authority) |
| `REJECTED`, `UNDELIVERABLE`, `FAILED`, `CANCELLED` | Ended without reaching the recipient |

`signals.transmission_status_changed` is sent on every change. Poll with
`services.transmissions_to_poll()`, retry with `services.transmissions_to_resubmit()`.

### Providers

```python
from invoicing.einvoicing.providers import EInvoiceProvider

class MyProvider(EInvoiceProvider):
    name = 'my-provider'
    supports_status = True

    def submit(self, document): ...                 # -> SubmitResult, or raise ProviderError
    def get_status(self, provider_document_id): ... # -> StatusResult
```

`INVOICING_EINVOICING['PROVIDER_RESOLVER']` names a callable returning the
provider for an invoice, e.g. with that supplier's credentials.

`providers.sapi_sk.SapiSkProvider(base_url, client_id, client_secret)`
implements [SAPI-SK 1.0](https://www.sapi-sk.sk/openapi.json), the standard
interface of Slovak Digital Postmen: OAuth2 client credentials (tokens cached
in the Django cache, refresh tokens rotated), `POST /document/send` with
`Idempotency-Key`, and errors retried only when the provider marks them
`retryable`. SAPI-SK 1.0 has no outbound status or validation call; a provider
offering those outside SAPI can subclass it.

## Settings

```python
INVOICING_EINVOICING = {
    'BUILDER_CLASS': 'invoicing.einvoicing.ubl.PeppolBIS3Builder',
    'UNIT_CODES': {'EMPTY': 'C62', 'PIECES': 'H87', 'HOURS': 'HUR'},  # UN/ECE Rec 20
    'DEFAULT_UNIT_CODE': 'C62',
    'PAYMENT_MEANS_CODES': {'BANK_TRANSFER': '30', 'CASH': '10', 'CASH_ON_DELIVERY': '10', 'PAYMENT_CARD': '48'},
    'SCHEMATRON': True,
    'ALLOWED_CURRENCIES': ('EUR',),      # None: any
    'ALLOWED_CUSTOMER_COUNTRIES': None,  # e.g. ('SK',)
    'PROVIDER_RESOLVER': None,           # 'myapp.einvoicing.get_provider'
    'PREVALIDATE_WITH_PROVIDER': True,
    'STATUS_POLL_DAYS': 30,
    'SUBMITTING_TIMEOUT_SECONDS': 300,
}
```

Customise the XML by subclassing `PeppolBIS3Builder` and overriding its
`get_*` methods (`get_buyer_reference`, `get_seller_legal_info`,
`get_payment_id`, `get_unit_code`, ...).
