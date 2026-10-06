# E-invoicing (Peppol BIS Billing 3.0)

`invoicing.einvoicing` turns an `Invoice` into a structured electronic invoice:
a UBL 2.1 document compliant with [Peppol BIS Billing 3.0](https://docs.peppol.eu/poacc/billing/3.0/)
(EN 16931), as required for Slovak eFaktúra from 2027.

It is split into independent layers. None of them knows about any network or
Access Point provider:

```
Invoice ─▶ calculations ─▶ ubl (builder) ─▶ validation
```

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
}
```

Customise the XML by subclassing `PeppolBIS3Builder` and overriding its
`get_*` methods (`get_buyer_reference`, `get_seller_legal_info`,
`get_payment_id`, `get_unit_code`, ...).
