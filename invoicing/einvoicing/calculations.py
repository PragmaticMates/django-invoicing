"""
EN 16931 totals of an invoice, computed one consistent way.

The core models round in several different ways (Python's half-even
``round()`` per item, PostgreSQL half-up per rate group over an unrounded
base), so the stored ``Invoice.total`` can be off by a cent from what
EN 16931 rules BR-CO-10/15/17 accept. This module does not touch those
models: it computes the totals the structured invoice will declare, and
``reconcile()`` refuses when they differ from what the invoice already says
(i.e. from what its PDF shows).

All amounts are rounded half-up to 2 decimals:

* line gross        = quantity × unit price
* line allowance    = line gross × discount %
* line net (BT-131) = line gross − line allowance
* taxable (BT-116)  = Σ line nets per (category, rate)
* tax (BT-117)      = taxable × rate
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from invoicing.einvoicing.vat import category_rate, resolve_category


CENT = Decimal('0.01')
ZERO = Decimal('0.00')


def round_amount(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class ReconciliationError(ValueError):
    def __init__(self, differences):
        self.differences = differences
        super().__init__('; '.join(
            f'{name}: stored {stored}, computed {computed}' for name, stored, computed in differences
        ))


@dataclass(frozen=True)
class LineInput:
    quantity: Decimal
    unit_price: Decimal
    vat_category: str
    tax_rate: Decimal = None
    discount_percent: Decimal = ZERO
    reference: object = None  # e.g. the Item it came from


@dataclass(frozen=True)
class Line:
    input: LineInput
    vat_rate: Decimal  # None for category O
    gross_amount: Decimal
    allowance_amount: Decimal
    net_amount: Decimal

    @property
    def vat_category(self):
        return self.input.vat_category


@dataclass(frozen=True)
class VatBreakdown:
    category: str
    rate: Decimal  # None for category O
    taxable_amount: Decimal
    tax_amount: Decimal


@dataclass(frozen=True)
class DocumentTotals:
    lines: tuple
    vat_breakdown: tuple
    line_extension_amount: Decimal   # BT-106
    tax_exclusive_amount: Decimal    # BT-109
    tax_amount: Decimal              # BT-110
    tax_inclusive_amount: Decimal    # BT-112
    prepaid_amount: Decimal          # BT-113
    payable_amount: Decimal          # BT-115
    allowance_total_amount: Decimal = ZERO  # BT-107, no document-level allowances yet
    charge_total_amount: Decimal = ZERO     # BT-108, no document-level charges yet
    categories: frozenset = field(default=frozenset())


def compute_line(line_input):
    gross = round_amount(Decimal(line_input.quantity) * Decimal(line_input.unit_price))
    allowance = round_amount(gross * Decimal(line_input.discount_percent or 0) / 100)

    return Line(
        input=line_input,
        vat_rate=category_rate(line_input.vat_category, line_input.tax_rate),
        gross_amount=gross,
        allowance_amount=allowance,
        net_amount=gross - allowance,
    )


def compute(line_inputs, prepaid_amount=ZERO):
    lines = tuple(compute_line(line_input) for line_input in line_inputs)

    groups = {}
    for line in lines:
        key = (line.vat_category, line.vat_rate)
        groups[key] = groups.get(key, ZERO) + line.net_amount

    breakdown = tuple(
        VatBreakdown(
            category=category,
            rate=rate,
            taxable_amount=taxable,
            tax_amount=round_amount(taxable * rate / 100) if rate else ZERO,
        )
        for (category, rate), taxable in sorted(groups.items(), key=_breakdown_order)
    )

    line_extension = sum((line.net_amount for line in lines), ZERO)
    tax = sum((row.tax_amount for row in breakdown), ZERO)
    tax_inclusive = line_extension + tax
    prepaid = round_amount(prepaid_amount or 0)

    return DocumentTotals(
        lines=lines,
        vat_breakdown=breakdown,
        line_extension_amount=line_extension,
        tax_exclusive_amount=line_extension,
        tax_amount=tax,
        tax_inclusive_amount=tax_inclusive,
        prepaid_amount=prepaid,
        payable_amount=tax_inclusive - prepaid,
        categories=frozenset(category for category, rate in groups),
    )


def _breakdown_order(item):
    (category, rate), taxable = item
    return (category, -(rate or 0))


def line_inputs_for_invoice(invoice):
    """Line inputs of an ``invoicing.Invoice``, with each item's VAT category resolved."""
    supplier_has_vat_id = bool(invoice.supplier_vat_id)

    return [
        LineInput(
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_percent=item.discount or ZERO,
            tax_rate=item.tax_rate,
            vat_category=resolve_category(
                tax_rate=item.tax_rate,
                supplier_has_vat_id=supplier_has_vat_id,
                explicit=getattr(item, 'vat_category', None),
            ),
            reference=item,
        )
        for item in invoice.item_set.all()
    ]


def compute_for_invoice(invoice):
    return compute(line_inputs_for_invoice(invoice), prepaid_amount=invoice.already_paid)


def reconcile(totals, invoice):
    """
    Raises ``ReconciliationError`` unless the computed totals equal the
    invoice's stored ``total`` and ``vat`` to the cent. A stored ``vat`` of
    None (not a VAT payer) has to correspond to a computed VAT of zero.
    """
    differences = []

    stored_total = round_amount(invoice.total)
    if stored_total != totals.tax_inclusive_amount:
        differences.append(('total', stored_total, totals.tax_inclusive_amount))

    stored_vat = ZERO if invoice.vat is None else round_amount(invoice.vat)
    if stored_vat != totals.tax_amount:
        differences.append(('vat', stored_vat, totals.tax_amount))

    if differences:
        raise ReconciliationError(differences)
