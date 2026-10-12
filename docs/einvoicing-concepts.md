# E-invoicing concepts

Structured e-invoicing involves several standards and parties that are easy to
mix up. This page explains what each one is and how `invoicing.einvoicing`
maps onto them. For the API, see [E-invoicing](einvoicing.md).

An analogy runs through it: e-invoicing is like registered mail, with a
mandatory envelope, a postal network, a post office you choose, and a counter
where you hand letters in.

## The terms

### E-invoicing (eFaktúra)

The **goal and the obligation**. An e-invoice is not a PDF or a scan, but
structured data that the recipient's accounting software reads without
retyping. In Slovakia, from 1 January 2027, VAT payers must issue domestic
invoices as e-invoices, every business must be able to receive them, and their
data is reported to the Financial Administration (FS SR).

*The law that letters must go by registered mail, in a prescribed envelope.*

### EN 16931, UBL and Peppol BIS: the format

What an e-invoice contains and how it is written down, in three layers:

| Layer | What it defines |
|---|---|
| **EN 16931** | The European standard: which data an invoice carries ("business terms", BT-1 invoice number, BT-49 buyer electronic address, ...) and the rules they obey, e.g. how totals and VAT add up (BR-CO-*). |
| **UBL 2.1** (Universal Business Language) | An OASIS XML syntax: where in the XML each of those data goes. EN 16931 can also be expressed in UN/CEFACT CII; Peppol uses UBL. |
| **Peppol BIS Billing 3.0** | The specification for invoices exchanged in Peppol: EN 16931 in UBL, plus Peppol's own rules (PEPPOL-EN16931-*) and code lists. Published with machine-readable rules (Schematron) that every Access Point applies. |

Countries can add national rules on top. Slovakia publishes its requirements
only as a human-readable table; the library checks its reading of it as
`SK-LOCAL-*`.

*The prescribed shape and content of the letter.*

**In this library:** `ubl.PeppolBIS3Builder` writes the UBL;
`calculations` computes the EN 16931 totals; `validation` checks the UBL
schema, the Peppol BIS Schematron (EN 16931 and Peppol rules) and the Slovak
rules.

### Peppol: the network

The **delivery network**, a pan-European "postal service" for business
documents. Companies do not send e-invoices to each other directly; each is
served by an **Access Point**, and Access Points deliver to one another over a
secured protocol (AS4). Its parts:

- **Participant ID**: a company's address in the network, `scheme:identifier`.
  Slovak companies use scheme `0245` with their DIČ, e.g. `0245:2023537813`.
- **SMP** (Service Metadata Publisher): the directory saying which Access Point
  receives for a participant, and which document types it accepts. Sending
  starts with an SMP lookup.
- **Message Level Status (MLS)**: the recipient's Access Point confirms (or
  rejects) what it received.
- **Peppol Authority**: the national body that accredits Access Points and sets
  national rules; in Slovakia, the Financial Directorate (FR SR).
- **Tax data document**: in Slovakia, the Access Points also report each
  invoice's data to the Financial Administration ("five-corner model").

*The postal network, with addresses, a directory and delivery receipts.*

**In this library:** `identifiers` (participant IDs, document type and process
IDs, the Slovak deterministic document UUID); the
`supplier_/customer_endpoint_*` fields hold the participant IDs.

### Digital Postman: your Access Point

A **concrete provider** that operates an Access Point for you; Slovakia calls
them *digitálny poštár*. It is accredited by the Peppol Authority, and it
takes your e-invoice, validates it, finds the recipient in the SMP, delivers
it, reports the tax data, and archives it. You can switch to another one.
SLOVAKODATA (ePostman) is one of them.

*The post office you chose; you could pick another.*

**In this library:** an `EInvoiceProvider`. The library does not know any
particular provider.

### SAPI-SK: the counter

The **standardised API** through which software hands documents to a Slovak
Digital Postman (Standardised Access Point Interface, defined by the Slovak
Peppol community with the Financial Administration). Every Digital Postman
implementing it offers the same API, so switching providers does not change
how documents are submitted: OAuth2 client credentials, then
`POST /sapi/document/send` with an idempotency key.

SAPI-SK 1.0 covers sending and receiving, but has no call for the status of a
sent document, nor for validating one. Providers offer those through their own
APIs, which differ from provider to provider.

*The same counter at every post office.*

**In this library:** `providers.sapi_sk.SapiSkProvider` implements SAPI-SK;
status, validation and participant lookups are optional provider capabilities
that a subclass adds with the provider's own API.

## How they fit together

```
your app ──(UBL, Peppol BIS 3.0)──▶ SAPI-SK ──▶ Digital Postman ──▶ Peppol ──▶ recipient's Access Point ──▶ recipient
                                               (Access Point)  │
                                                               └──▶ tax data ──▶ Financial Administration
```

1. Your application builds the **UBL** document and checks it against
   **EN 16931 / Peppol BIS** (`ubl`, `calculations`, `validation`).
2. It hands it to its **Digital Postman** through **SAPI-SK**
   (`services.submit()` with `SapiSkProvider`).
3. The Digital Postman looks the recipient's **Participant ID** up in the
   **SMP**, delivers through **Peppol**, and reports the tax data.
4. The status comes back through the provider's own API or its webhooks
   (`services.refresh_status()`, with a provider-specific subclass).

All of that together is **e-invoicing**.

## Portability

| Part | Standard | Changes with the provider? |
|---|---|---|
| UBL document, validation | EN 16931, Peppol BIS 3.0 | no |
| Submitting documents | SAPI-SK | no |
| Status, validation, lookups, webhooks | provider's own API | **yes** |

Keep the provider-specific part in one provider class, as Invoicer does with
its `SlovakodataProvider`; everything else stays the same when you switch.
