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

To receive provider webhooks, include the URLs **outside** `i18n_patterns`
(providers do not follow the language redirect):

```python
urlpatterns += [path('einvoicing/', include('invoicing.einvoicing.urls'))]
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

services.send_blocked_reason(invoice)  # why it must not be sent now, or None
xml, report = services.check(invoice)  # what would be sent, all checks; stores and sends nothing
transmission = services.send(invoice)  # prepare (build, validate, store) and submit in the background
services.refresh_status(transmission)  # ask the provider now (webhooks and polling do it otherwise)
```

`send()` returns the invoice's live transmission if it has one; otherwise it
checks `send_blocked_reason()`, prepares a transmission with the configured
attachments and queues its submission once the transaction commits. It raises
`SendNotAllowed`, `EInvoiceValidationError` or `ResubmissionNotAllowed` when
the invoice cannot be sent.

`send_blocked_reason()` blocks an invoice whose status is not in
`SENDABLE_STATUSES` (e.g. only `NEW`: a sent, paid or canceled invoice is past
being issued), one without the customer's electronic address, and one the
provider would refuse (see *Sending again*).

`ATTACHMENTS` names a callable returning the documents to embed into each
e-invoice, typically its PDF; sending, checking and the Peppol export use it:

```python
def get_attachments(invoice):
    return [Attachment(f'{invoice.number}.pdf', render_pdf(invoice))]
```

The lower-level steps remain available: `prepare()` (build, validate, store),
`submit()` (hand over; safe to retry) and `refresh_status()`.

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
| `PREPARED` | Stored, not yet sent | submitted |
| `SUBMITTING` | Being sent | resubmittable after `SUBMITTING_TIMEOUT_SECONDS` (a worker died) |
| `SUBMIT_UNKNOWN` | Timeout or retryable error | resubmitted: same key, same bytes |
| `CONFLICT` | HTTP 409: the provider may already hold the document | a human decides, see below |
| `REFUSED` | The provider did not take it (invalid, no credit, ...) | may be sent again |
| `SUBMITTED` | The provider has it | polled |
| `DELIVERED` | Reached the recipient's Access Point | polled, for the recipient's confirmation |
| `UNCONFIRMED` | Delivered, no confirmation in time | polled: a late one still turns it `ACCEPTED` or `REJECTED` |
| `ACCEPTED`, `DELIVERED_NON_PEPPOL` | Delivered (to the tax authority instead, for a buyer outside Peppol) | final |
| `REJECTED`, `UNDELIVERABLE`, `FAILED`, `CANCELLED` | Ended without reaching the recipient | may be sent again, unless the provider refuses |

`submit()` maps a `ProviderError`: retryable or unknown outcome → `SUBMIT_UNKNOWN`
and re-raised; HTTP 409 → `CONFLICT`; anything else → `REFUSED`.

`signals.transmission_status_changed(transmission, previous_status)` is sent on
every change, e.g. to mark the invoice itself sent.

### Sending again

After a transmission ended without reaching the recipient, a new one can be
prepared, with freshly built XML and a new idempotency key. Providers differ
on whether they take it: SLOVAKODATA, for one, refuses another submission
under the same number once a transfer started and failed, and repeats it
itself on request. A provider says so through
`resubmission_blocked_reason()`; `prepare()` then raises
`ResubmissionNotAllowed` with that reason, and `send_blocked_reason()` returns
it.

### Conflicts

`CONFLICT` means the provider answered 409: it may hold this document already
(e.g. the first response was lost more than a day ago), or the submission
duplicates an earlier one. It is neither retried nor treated as unsent, and it
keeps the invoice locked. Once a human has checked (usually in the provider's
portal) that the provider did not take this submission,
`services.resolve_conflict(transmission, note)` ends it `REFUSED`, with the
note in the event log. The admin offers the same as an action.

## Background jobs and status updates

`invoicing.einvoicing.tasks` runs through django-pragmatic's task decorator
(`PRAGMATIC_TASK_DECORATOR`, e.g. `'django_rq.job'`) on the `QUEUE` queue, like
the exporters; without django-pragmatic the jobs run synchronously.

- `submit_einvoice`: hands a prepared transmission over (`send()` queues it).
- `refresh_einvoice`: asks the provider for news (webhooks queue it).
- `einvoicing_maintenance`: resubmits unsent transmissions (prepared, of
  unknown outcome or stuck submitting; at most `MAX_SUBMIT_ATTEMPTS`) and polls
  those submitted, delivered or unconfirmed in the last `STATUS_POLL_DAYS`.

The maintenance is scheduled on `MAINTENANCE_CRON` (every 15 minutes by
default, on the `MAINTENANCE_QUEUE` queue) by django-pragmatic's
`rqscheduler`, which calls `EInvoicingConfig.schedule_jobs()` after wiping the
`cron` scheduler, so redeploys never duplicate it. Set `MAINTENANCE_CRON` to
`None` to schedule it yourself.

**Webhooks** arrive at `/einvoicing/webhook/<provider>/`
(`invoicing.einvoicing.urls`, providers in `WEBHOOK_PROVIDERS`):

1. the notification names a provider document, which finds the transmission
   and so the invoice -- nothing is trusted yet, this only picks the account;
2. the resolver gives that invoice's provider, with its webhook secret, which
   verifies the notification (otherwise 401);
3. the status is then asked from the provider in the background, never taken
   from the notification, so a forged, replayed or out-of-order one changes
   nothing.

Notifications about documents that are not ours (incoming invoices, documents
sent from the provider's portal) are acknowledged and ignored. Polling keeps
running anyway: not every status change necessarily has an event.

## SLOVAKODATA

`providers.slovakodata.SlovakodataProvider` sends through SAPI-SK and uses
ePostman's Enterprise API (`X-Api-Key`) for status, validation, participant
lookups and webhooks:

```python
SlovakodataProvider(environment, client_id, client_secret, api_key='', webhook_secret='')
```

- `environment`: `'test'` (`testpostman.slovakodata.com`, documents stay in the
  Peppol test network) or `'production'` (`postman.slovakodata.com`);
- `client_id`, `client_secret`: a SAPI client created in the ePostman portal;
- `api_key`: an Enterprise API key (portal: *Nastavenia → API kľúče*); without
  it the provider can only send;
- `webhook_secret`: the secret of the webhook pointing at this project.

It stores no credentials: the project decides where they live, through the
resolver.

### One account for the project

```python
INVOICING_EINVOICING = {
    'PROVIDER_RESOLVER': 'invoicing.einvoicing.providers.slovakodata.from_settings',
    'SLOVAKODATA': {
        'ENVIRONMENT': 'production',
        'CLIENT_ID': env('SLOVAKODATA_CLIENT_ID'),
        'CLIENT_SECRET': env('SLOVAKODATA_CLIENT_SECRET'),
        'API_KEY': env('SLOVAKODATA_API_KEY'),
        'WEBHOOK_SECRET': env('SLOVAKODATA_WEBHOOK_SECRET'),
    },
}
```

### An account per supplier (or anything else)

Keep the credentials wherever the project keeps such things (a model,
encrypted at rest) and resolve the provider per invoice:

```python
# myapp/einvoicing.py
from invoicing.einvoicing.providers.slovakodata import SlovakodataProvider

def get_provider(invoice):
    account = Account.objects.filter(peppol_id=f'{invoice.supplier_endpoint_scheme}:{invoice.supplier_endpoint_id}',
                                     enabled=True).first()
    if account is None:
        return None
    return SlovakodataProvider(account.environment, account.client_id, account.client_secret,
                               api_key=account.api_key, webhook_secret=account.webhook_secret)
```

```python
INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'myapp.einvoicing.get_provider'}
```

The webhook view finds each notification's account through the same resolver,
so one URL serves every account.

### The webhook

ePostman shows a webhook's secret only once, in the API's answer when the
webhook is created -- not in its portal. Create it through the API and store
the secret where the resolver reads it:

```python
provider = get_provider(invoice)   # or from_settings()
webhook = provider.create_webhook('https://example.com/einvoicing/webhook/slovakodata/')
webhook['secret']                  # store it as the account's webhook secret, now
provider.test_webhook(webhook['id'])
```

`create_webhook()` subscribes to every outcome (`WEBHOOK_EVENTS`, more than the
portal offers). `list_webhooks()` and `delete_webhook(id)` manage them; a
webhook cannot be edited.

### SLOVAKODATA specifics

- **Sending again**: after a transfer started and failed (`FAILED`), ePostman
  refuses any new submission under the same number; the provider blocks it
  and points to ePostman's support.
- **Status mapping**: `PENDING`, `VALIDATING`, `VALIDATED`, `READY`, `SENDING` →
  `SUBMITTED`; `VALIDATION_FAILED` → `REJECTED`; the others one to one; an
  unknown status keeps the transmission polled.
- **Test receivers**: a document cannot be addressed to its own sender; a
  receiver that accepts documents in the test network has to come from
  SLOVAKODATA.

## Admin

- **Invoices**:
    - a collapsed *E-invoicing* section (electronic addresses, buyer
      reference, VAT exemption reason); items have their VAT category;
    - with `invoicing.einvoicing` installed: an **e-invoice** column in the
      list (the newest transmission's status, colour-coded, linking to it); an
      invoice with a live or delivered transmission is **read-only**, except
      `status`, `date_paid` and `already_paid`; the invoice page lists its
      transmissions.
- **Send as e-invoice (API)**, an action enabled by the
  [`EInvoicingManager`](exporters/einvoicing.md): a confirmation page lists
  the selected invoices, which will be sent and which will not (and why),
  before anything is sent.
- **Export to Peppol UBL (XML)**, by the [`PeppolManager`](exporters/peppol.md):
  the e-invoices as they would be sent, sent nowhere.
- **E-invoice transmissions**: every attempt, read-only, with its event log,
  a download of the exact XML sent (and its SHA-256), and the *Resolve
  conflict* action.

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

    @classmethod
    def webhook_document_id(cls, payload): ...            # the document a notification is about
    def verify_webhook(self, raw_body, headers): ...      # True for a genuine notification
```

`ProviderError(message, code=, retryable=, outcome_unknown=, http_status=,
correlation_id=, details=, retry_after=, raw=)`: `retryable` means the same
request may simply be sent again; `outcome_unknown` that it may have been
processed even so.

`INVOICING_EINVOICING['PROVIDER_RESOLVER']` names a callable returning the
provider for an invoice; `None` means not configured. To receive a new
provider's webhooks, add it to `WEBHOOK_PROVIDERS`.

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
a provider offering those outside SAPI subclasses it, as `SlovakodataProvider`
does.

## Settings

```python
INVOICING_EINVOICING = {
    # building and checking
    'BUILDER_CLASS': 'invoicing.einvoicing.ubl.PeppolBIS3Builder',
    'UNIT_CODES': {'EMPTY': 'C62', 'PIECES': 'H87', 'HOURS': 'HUR'},  # UN/ECE Rec 20
    'DEFAULT_UNIT_CODE': 'C62',
    'PAYMENT_MEANS_CODES': {'BANK_TRANSFER': '30', 'CASH': '10', 'CASH_ON_DELIVERY': '10', 'PAYMENT_CARD': '48'},
    'SCHEMATRON': True,
    'ALLOWED_CURRENCIES': ('EUR',),      # None: any
    'ALLOWED_CUSTOMER_COUNTRIES': None,  # e.g. ('SK',)
    'ATTACHMENTS': None,                 # 'myapp.einvoicing.get_attachments'

    # sending
    'PROVIDER_RESOLVER': None,           # 'invoicing.einvoicing.providers.slovakodata.from_settings'
    'SENDABLE_STATUSES': None,           # e.g. ('NEW',)
    'PREVALIDATE_WITH_PROVIDER': True,
    'SUBMITTING_TIMEOUT_SECONDS': 300,

    # background jobs
    'QUEUE': 'default',
    'MAINTENANCE_CRON': '*/15 * * * *',  # None: schedule it yourself
    'MAINTENANCE_QUEUE': 'cron',
    'MAX_SUBMIT_ATTEMPTS': 10,
    'STATUS_POLL_DAYS': 30,

    # providers
    'WEBHOOK_PROVIDERS': {'slovakodata': 'invoicing.einvoicing.providers.slovakodata.SlovakodataProvider'},
    'SLOVAKODATA': None,                 # credentials for from_settings, see above
}
```

Customise the XML by subclassing `PeppolBIS3Builder` and overriding its
`get_*` methods (`get_buyer_reference`, `get_seller_legal_info`,
`get_payment_id`, `get_unit_code`, ...).

## Exceptions

| Exception | Raised by | When |
|---|---|---|
| `services.SendNotAllowed` | `send()` | `send_blocked_reason()` gives a reason |
| `services.EInvoiceValidationError` | `send()`, `prepare()`, `build_and_validate()` | any fatal finding; `.report` has them |
| `services.ResubmissionNotAllowed` | `prepare()` | the provider would refuse a new submission |
| `services.TransmissionError` | `submit()`, `resolve_conflict()` | wrong provider, or not in conflict |
| `providers.ProviderError` | providers, `submit()` | the provider failed or refused |
| `calculations.ReconciliationError` | `calculations.reconcile()` | computed totals differ from the stored ones |
| `vat.VatCategoryError` | `vat.resolve_category()` | an item's VAT category is ambiguous or contradicts its rate |

## Translations

Statuses, field names, VAT categories, messages and admin texts are
translatable; Slovak is included.
