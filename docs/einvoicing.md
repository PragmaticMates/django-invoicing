# E-invoicing (Peppol BIS Billing 3.0)

`invoicing.einvoicing` turns an `Invoice` into a structured electronic invoice:
a UBL 2.1 document compliant with [Peppol BIS Billing 3.0](https://docs.peppol.eu/poacc/billing/3.0/)
(EN 16931), as required for Slovak eFaktúra from 2027, and sends it through a
replaceable provider (an Access Point, "Digital Postman" in Slovakia).

```
Invoice ─▶ calculations ─▶ ubl (builder) ─▶ validation ─▶ services ─▶ EInvoiceProvider ─▶ Peppol
```

Only the last layer talks to the network. Calculations, the builder and
validation work without installing anything; sending needs the Django app.

New to UBL, Peppol, Access Points or SAPI-SK? Start with
[E-invoicing concepts](einvoicing-concepts.md).

## Installation

```bash
pip install "django-invoicing[einvoicing]"   # adds saxonche (Schematron rules) and requests
```

```python
INSTALLED_APPS = [
    ...
    'invoicing',
    'invoicing.einvoicing',   # only to send: adds the transmission log (two tables)
]
```

```bash
python manage.py migrate
```

## Building and validating

```python
from invoicing.einvoicing.ubl import Attachment, get_builder
from invoicing.einvoicing.validation import preflight, validate

report = preflight(invoice)          # can this invoice become a correct e-invoice?
if report.is_valid:
    xml = get_builder(invoice, attachments=[Attachment('2026-001.pdf', pdf_bytes)]).build()
    report = validate(xml)           # UBL XSD + Peppol Schematron + Slovak rules
```

Both checks return a `ValidationReport`: `errors` (fatal: do not send),
`warnings`, `is_valid`, `findings` (each with `rule_id`, `severity`,
`message`, `source`, `location`) and `as_dict()`.

The builder is deterministic: the same invoice (and attachments) give the same
bytes.

## Data the invoice needs

| Field | EN 16931 | Notes |
|---|---|---|
| `supplier_endpoint_scheme` / `supplier_endpoint_id` | BT-34 | Peppol ID of the seller; Slovak businesses use `0245` + DIČ |
| `customer_endpoint_scheme` / `customer_endpoint_id` | BT-49 | Peppol ID of the buyer |
| `buyer_reference` | BT-10 | Falls back to the invoice number |
| `Item.vat_category` | BT-151 | Blank derives it: rate > 0 is `S`, 0 is `Z`, no rate without supplier VAT ID is `O`. A VAT payer's item without a rate (reverse charge, exemption) has to set it |
| `vat_exemption_reason` / `_code` | BT-120/121 | Required for `E`; `AE`, `K`, `G`, `O` default to their VATEX code |
| `supplier_additional_info['legal_form']`, `['register']` | BT-33 | Seller legal form and commercial register entry |

`set_supplier_data()` and `set_customer_data()` accept `endpoint_scheme` and
`endpoint_id`. `identifiers.sk_participant_id(tax_id)` makes the Slovak
`0245:<DIČ>` participant ID.

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

1. `preflight(invoice)`: data present, supported type and currency, valid participant IDs, VAT categories resolvable, exemption reasons, totals matching
2. UBL 2.1 XSD
3. Peppol BIS Billing 3.0.21 Schematron: CEN EN 16931 rules and Peppol rules (artefacts 1.3.16), run on Saxon-HE
4. Slovak national rules, `SK-LOCAL-*`
5. When sending, the provider's own validation too, if it has one (`PREVALIDATE_WITH_PROVIDER`)

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

transmission = services.prepare(invoice, attachments=[...])  # build + validate + store
services.submit(transmission)                                 # hand over; safe to retry
services.refresh_status(transmission)                         # ask the provider, if it can tell
```

`EInvoiceTransmission` is one attempt to send an invoice. It keeps the exact
XML sent (and its SHA-256), the validation report, the provider document ID,
the status (and the provider's own name for it), the timestamps, the last
error, and an append-only log of events (`transmission.events`).

### Idempotency

- `prepare()` builds and validates the XML once and stores it before any
  network call. `submit()` sends exactly those bytes with the same
  `Idempotency-Key` every time, so a timeout, crash or 5xx followed by a retry
  cannot create a second document.
- An invoice has at most one live or successful transmission, enforced by a
  conditional unique constraint; `prepare()` returns it instead of creating
  another, also when two requests race.
- A transmitted invoice cannot be deleted (`on_delete=PROTECT`), so its
  number, which identifies the document in Peppol, is never reused (mind
  `INVOICING_FILL_SEQUENCE_GAPS`).

### Statuses

| Status | Meaning | Next |
|---|---|---|
| `PREPARED` | Stored, not yet sent | `submit()` |
| `SUBMITTING` | Being sent | resubmittable after `SUBMITTING_TIMEOUT_SECONDS` (a worker died) |
| `SUBMIT_UNKNOWN` | Timeout or retryable error | resubmit: same key, same bytes |
| `CONFLICT` | HTTP 409: the provider may already hold the document | a human decides, see below |
| `REFUSED` | The provider did not take it (invalid, no credit, ...) | may be prepared again |
| `SUBMITTED` | The provider has it | polled |
| `DELIVERED` | Reached the recipient's Access Point | polled, for the recipient's confirmation |
| `UNCONFIRMED` | Delivered, no confirmation in time | polled: a late one still turns it `ACCEPTED` or `REJECTED` |
| `ACCEPTED`, `DELIVERED_NON_PEPPOL` | Delivered (to the tax authority instead, for a buyer outside Peppol) | final |
| `REJECTED`, `UNDELIVERABLE`, `FAILED`, `CANCELLED` | Ended without reaching the recipient | may be prepared again, unless the provider refuses |

`submit()` maps a `ProviderError`: retryable or unknown outcome → `SUBMIT_UNKNOWN`
and re-raised (so a job queue retries it); HTTP 409 → `CONFLICT`; anything else
→ `REFUSED`.

`signals.transmission_status_changed(transmission, previous_status)` is sent on
every change, e.g. to mark the invoice itself sent.

### Sending again

After a transmission ended without reaching the recipient, `prepare()` creates
a new one, with freshly built XML and a new idempotency key. Providers differ
on whether they take it: SLOVAKODATA ePostman, for one, refuses another
submission under the same number once a transfer started and failed, and
repeats it itself on request. A provider says so through
`resubmission_blocked_reason()`; `prepare()` then raises
`ResubmissionNotAllowed` with that reason, before building anything.
`services.resubmission_blocked_reason(invoice, provider)` asks the same
question without preparing, e.g. to hide a send button.

### Conflicts

`CONFLICT` means the provider answered 409: it may hold this document already
(e.g. the first response was lost more than a day ago), or the submission
duplicates an earlier one. It is neither retried nor treated as unsent, and it
keeps the invoice locked. Once a human has checked (usually in the provider's
portal) that the provider did not take this submission,
`services.resolve_conflict(transmission, note)` ends it `REFUSED`, with the
note in the event log. The admin offers the same as an action.

## Keeping statuses up to date

Run both of these periodically, e.g. every 15 minutes from a scheduler:

```python
from invoicing.einvoicing import services
from invoicing.einvoicing.providers import ProviderError

for transmission in services.transmissions_to_resubmit():  # PREPARED, SUBMIT_UNKNOWN, stale SUBMITTING
    try:
        services.submit(transmission)
    except ProviderError:
        pass  # still unsent; next run

for transmission in services.transmissions_to_poll():      # SUBMITTED, DELIVERED, UNCONFIRMED, last STATUS_POLL_DAYS
    services.refresh_status(transmission)
```

Cap the resubmission attempts (`transmission.attempt_count`) as you see fit.

**Webhooks** are provider-specific and not part of the library. A safe pattern
(the one Invoicer uses): verify the provider's signature and timestamp, find
the transmission by `provider_document_id`, and call `refresh_status()` in the
background. Do not take the status from the notification itself; asking the
provider makes a forged, replayed or out-of-order notification harmless. Keep
polling as well, since not every status change necessarily has an event.

## Admin

With `invoicing.einvoicing` installed, *E-invoice transmissions* lists every
attempt, read-only, with its event log, a download of the exact XML sent (and
its SHA-256), and the *Resolve conflict* action.

## Providers

```python
from invoicing.einvoicing.providers import EInvoiceProvider

class MyProvider(EInvoiceProvider):
    name = 'my-provider'          # stored on each transmission
    environment = 'production'
    supports_status = True        # capabilities; only submit() is required

    def submit(self, document): ...                       # OutgoingDocument -> SubmitResult, or raise ProviderError
    def get_status(self, provider_document_id): ...       # -> StatusResult (status: a TransmissionStatus)
    def validate(self, xml, receiver_id=None): ...        # -> ValidationReport (supports_validation)
    def check_reachability(self, participant_id, document_type_id): ...  # -> Reachability (supports_reachability)
    def resubmission_blocked_reason(self, previous): ...  # -> str or None (default None)
```

`ProviderError(message, code=, retryable=, outcome_unknown=, http_status=,
correlation_id=, details=, retry_after=, raw=)`: `retryable` means the same
request may simply be sent again; `outcome_unknown` that it may have been
processed even so.

`INVOICING_EINVOICING['PROVIDER_RESOLVER']` names a callable returning the
provider for an invoice, e.g. built from that supplier's credentials; `None`
means not configured.

### SAPI-SK

`providers.sapi_sk.SapiSkProvider(base_url, client_id, client_secret,
environment='', timeout=30)` implements
[SAPI-SK 1.0](https://www.sapi-sk.sk/openapi.json), the standard interface of
Slovak Digital Postmen; `base_url` is the provider's SAPI base, e.g.
`https://<host>/sapi`.

- OAuth2 client credentials; tokens cached in the Django cache, refresh tokens
  rotated when the provider issues them, a fresh token otherwise. A revoked
  token is replaced once.
- `POST /document/send` with `Idempotency-Key`, `X-Peppol-Participant-Id` and
  the payload's SHA-256.
- Errors retried only when the provider marks them `retryable`; both the
  SAPI-SK error envelope and plain gateway errors are understood.
- `health()` checks `GET /health`.

SAPI-SK 1.0 has no call for the status of a sent document, nor for validation;
a provider offering those outside SAPI subclasses it (Invoicer's
`SlovakodataProvider` does, with ePostman's Enterprise API).

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

## Exceptions

| Exception | Raised by | When |
|---|---|---|
| `services.EInvoiceValidationError` | `prepare()`, `build_and_validate()` | any fatal finding; `.report` has them |
| `services.ResubmissionNotAllowed` | `prepare()` | the provider would refuse a new submission |
| `services.TransmissionError` | `submit()`, `resolve_conflict()` | wrong provider, or not in conflict |
| `providers.ProviderError` | providers, `submit()` | the provider failed or refused |
| `calculations.ReconciliationError` | `calculations.reconcile()` | computed totals differ from the stored ones |
| `vat.VatCategoryError` | `vat.resolve_category()` | an item's VAT category is ambiguous or contradicts its rate |

## Translations

Statuses, field names, VAT categories and admin texts are translatable; Slovak
is included.
