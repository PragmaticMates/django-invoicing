from decimal import Decimal

import pytest

from invoicing.einvoicing.calculations import (
    LineInput, ReconciliationError, compute, compute_for_invoice, reconcile, round_amount,
)
from invoicing.einvoicing.vat import VatCategory
from invoicing.models import Item


D = Decimal


def line(quantity, unit_price, tax_rate=D('23'), discount=D('0'), category=VatCategory.STANDARD):
    return LineInput(
        quantity=D(quantity), unit_price=D(unit_price), tax_rate=tax_rate,
        discount_percent=D(discount), vat_category=category,
    )


class TestRounding:
    @pytest.mark.parametrize('value, expected', [
        ('0.005', '0.01'),
        ('0.015', '0.02'),
        ('0.025', '0.03'),   # round() would give 0.02 (half-even)
        ('2.675', '2.68'),
        ('-0.005', '-0.01'),
        ('1.004999', '1.00'),
    ])
    def test_half_up(self, value, expected):
        assert round_amount(D(value)) == D(expected)


class TestCompute:
    def test_single_standard_line(self):
        totals = compute([line('1', '100.00')])

        assert totals.line_extension_amount == D('100.00')
        assert totals.tax_amount == D('23.00')
        assert totals.tax_inclusive_amount == D('123.00')
        assert totals.payable_amount == D('123.00')
        assert totals.vat_breakdown[0].category == 'S'
        assert totals.vat_breakdown[0].rate == D('23')

    def test_line_amounts_are_rounded_before_summing(self):
        # 3 × 0.333 = 0.999 → 1.00 per line; the per-group base is the sum of rounded lines
        totals = compute([line('3', '0.333'), line('3', '0.333')])

        assert [l.net_amount for l in totals.lines] == [D('1.00'), D('1.00')]
        assert totals.vat_breakdown[0].taxable_amount == D('2.00')
        assert totals.tax_amount == D('0.46')

    def test_vat_is_computed_per_group_not_per_line(self):
        # per line: 0.10 × 23% = 0.023 → 0.02, ×3 = 0.06; per group: 0.30 × 23% = 0.069 → 0.07
        totals = compute([line('1', '0.10')] * 3)

        assert totals.tax_amount == D('0.07')

    def test_multiple_rates(self):
        totals = compute([
            line('2', '50.00', D('23')),
            line('1', '10.00', D('19')),
            line('4', '2.50', D('5')),
        ])

        rows = {row.rate: row for row in totals.vat_breakdown}
        assert rows[D('23')].taxable_amount == D('100.00')
        assert rows[D('23')].tax_amount == D('23.00')
        assert rows[D('19')].tax_amount == D('1.90')
        assert rows[D('5')].tax_amount == D('0.50')
        assert totals.tax_amount == D('25.40')
        assert totals.tax_inclusive_amount == D('145.40')
        assert [row.rate for row in totals.vat_breakdown] == [D('23'), D('19'), D('5')]

    def test_line_discount(self):
        totals = compute([line('3', '33.33', discount='10')])

        only = totals.lines[0]
        assert only.gross_amount == D('99.99')
        assert only.allowance_amount == D('10.00')  # 9.999
        assert only.net_amount == D('89.99')
        assert totals.tax_amount == D('20.70')     # 20.6977

    def test_fractional_quantity(self):
        totals = compute([line('1.255', '10.00')])

        assert totals.lines[0].net_amount == D('12.55')

    def test_not_subject_to_vat_has_no_rate(self):
        totals = compute([line('1', '100', tax_rate=None, category=VatCategory.NOT_SUBJECT)])

        assert totals.vat_breakdown[0].rate is None
        assert totals.tax_amount == D('0.00')
        assert totals.tax_inclusive_amount == D('100.00')

    def test_reverse_charge_has_zero_rate(self):
        totals = compute([line('1', '100', tax_rate=None, category=VatCategory.REVERSE_CHARGE)])

        assert totals.vat_breakdown[0].rate == D('0')
        assert totals.tax_amount == D('0.00')

    def test_prepaid(self):
        totals = compute([line('1', '100.00')], prepaid_amount=D('23'))

        assert totals.prepaid_amount == D('23.00')
        assert totals.payable_amount == D('100.00')

    @pytest.mark.parametrize('lines', [
        [line('1', '0.01')],
        [line('7', '1.43', discount='12.5'), line('0.333', '99.99', D('5'))],
        [line('13', '0.07', D('19')), line('1', '1999.99'), line('2.5', '3.33', None, category='O')],
    ])
    def test_en16931_invariants(self, lines):
        totals = compute(lines)

        # BR-CO-10: sum of line net amounts
        assert totals.line_extension_amount == sum(l.net_amount for l in totals.lines)
        # BR-CO-13: tax exclusive = line extension − allowances + charges
        assert totals.tax_exclusive_amount == (
            totals.line_extension_amount - totals.allowance_total_amount + totals.charge_total_amount
        )
        # BR-CO-14: invoice VAT = Σ category VAT
        assert totals.tax_amount == sum(row.tax_amount for row in totals.vat_breakdown)
        # BR-CO-15: tax inclusive = tax exclusive + VAT
        assert totals.tax_inclusive_amount == totals.tax_exclusive_amount + totals.tax_amount
        # BR-CO-16: payable = inclusive − prepaid
        assert totals.payable_amount == totals.tax_inclusive_amount - totals.prepaid_amount
        # BR-CO-17: category VAT = taxable × rate, rounded
        for row in totals.vat_breakdown:
            expected = round_amount(row.taxable_amount * (row.rate or 0) / 100)
            assert row.tax_amount == expected
        # every amount has 2 decimals
        for amount in (totals.line_extension_amount, totals.tax_amount, totals.tax_inclusive_amount):
            assert amount.as_tuple().exponent == -2


@pytest.mark.django_db
class TestInvoiceAdapter:
    def test_matches_stored_totals(self, invoice_factory, item_factory):
        invoice = invoice_factory()
        item_factory(invoice, quantity=D('2'), unit_price=D('50.00'), tax_rate=D('23'))
        item_factory(invoice, quantity=D('1'), unit_price=D('10.00'), tax_rate=D('5'))
        invoice.refresh_from_db()

        totals = compute_for_invoice(invoice)

        assert totals.tax_inclusive_amount == D('133.50')
        reconcile(totals, invoice)

    def test_not_a_vat_payer(self, invoice_factory, item_factory):
        invoice = invoice_factory(supplier_vat_id='')
        item_factory(invoice, quantity=D('1'), unit_price=D('100.00'), tax_rate=None)
        invoice.refresh_from_db()

        totals = compute_for_invoice(invoice)

        assert invoice.vat is None
        assert totals.categories == {'O'}
        reconcile(totals, invoice)

    def test_reconcile_refuses_cent_difference(self, invoice_factory, item_factory):
        # Stored totals use an unrounded base per rate group (3 × 0.005 = 0.015),
        # EN 16931 rounds every line first (3 × 0.01 = 0.03)
        invoice = invoice_factory()
        for _ in range(3):
            Item.objects.create(invoice=invoice, title='x', quantity=D('0.5'), unit_price=D('0.01'), tax_rate=D('23'))
        invoice.refresh_from_db()

        totals = compute_for_invoice(invoice)

        # EN 16931: each line 0.005 → 0.01, base 0.03; stored base is 0.015
        assert totals.line_extension_amount == D('0.03')
        assert invoice.total != totals.tax_inclusive_amount
        with pytest.raises(ReconciliationError) as error:
            reconcile(totals, invoice)
        assert error.value.differences[0][0] == 'total'

    def test_explicit_item_category(self, invoice_factory, item_factory):
        invoice = invoice_factory(vat_exemption_reason_code='VATEX-EU-AE')
        item_factory(invoice, quantity=D('1'), unit_price=D('100.00'), tax_rate=None, vat_category='AE')
        invoice.refresh_from_db()

        totals = compute_for_invoice(invoice)

        assert totals.categories == {'AE'}
        assert totals.vat_breakdown[0].rate == D('0')
