# Taxation

django-invoicing resolves the applicable VAT rate per invoice through a **taxation policy** — a class that encapsulates the tax rules for a given jurisdiction.

## How the policy is resolved

When `invoice.get_tax_rate()` is called (e.g. by `Item.calculate_tax()`), the following logic runs:

1. If `INVOICING_TAXATION_POLICY` is set, that class is used unconditionally.
2. If the invoice's `supplier_country` is an EU member state, `EUTaxationPolicy` is used automatically.
3. Otherwise, `TaxationPolicy.get_default_tax()` is used, which returns `INVOICING_TAX_RATE` from settings (or `None` if not set).

## EUTaxationPolicy

`invoicing.taxation.eu.EUTaxationPolicy` implements the standard EU VAT rules:

| Scenario | Tax rate returned |
|---|---|
| Supplier and customer are in the **same country** | Default rate for that country |
| Customer is a **private person** in another EU country | Default rate for the supplier's country |
| Customer is a **company in another EU country** with a VAT ID that **fails VIES validation** | Default rate for the supplier's country |
| Customer is a **company in another EU country** with a **valid VIES VAT ID** | `None` (reverse charge) |
| Customer is **outside the EU** (private or business) | `None` (not applicable) |

!!! note "Private person vs. company"
    The policy uses the presence of a `customer_vat_id` to distinguish private persons (no VAT ID) from companies (VAT ID set).

### Per-country default rates

Rates are defined in `EUTaxationPolicy.EU_COUNTRIES_RATES`. Some countries define date-based rate schedules (e.g. Slovakia switched from 20% to 23% on 2025-01-01):

```python
'SK': [
    {"from": date.min, "to": date(2024, 12, 31), "rate": Decimal(20)},
    {"from": date(2025, 1, 1), "to": date.max,   "rate": Decimal(23)},
],
```

The `date_tax_point` field on the invoice is used to select the correct rate when a country has multiple date ranges.

### VIES validation

The EU policy validates customer VAT IDs against the [VIES](https://ec.europa.eu/taxation_customs/vies/) service. Disable this check (e.g. for testing or offline environments) with:

```python
INVOICING_USE_VIES_VALIDATOR = False
```

When disabled, any cross-border B2B transaction is treated as reverse charge without VIES confirmation.

### Reverse charge

`EUTaxationPolicy.is_reverse_charge(supplier_vat_id, customer_vat_id)` returns `True` when:

- Both VAT IDs are set.
- The supplier is in an EU country.
- The supplier and customer are in **different** countries.

## Writing a custom taxation policy

Subclass `TaxationPolicy` and implement `get_tax_rate()`:

```python
from decimal import Decimal
from invoicing.taxation import TaxationPolicy


class MyTaxationPolicy(TaxationPolicy):
    @classmethod
    def get_tax_rate(cls, supplier_vat_id, customer_vat_id, date_tax_point=None):
        # Return a Decimal rate, 0 for zero-rated, or None for not applicable
        return Decimal('10')
```

Register it:

```python
INVOICING_TAXATION_POLICY = 'myapp.taxation.MyTaxationPolicy'
```

The `get_tax_rate_by_invoice(invoice)` classmethod is also available for override when you need access to the full invoice object.
