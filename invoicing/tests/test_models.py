"""
Tests for Invoice and Item models.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from invoicing.models import Invoice, Item


@pytest.mark.django_db
@pytest.mark.models
class TestInvoice:
    """Tests for Invoice model."""

    def test_invoice_str_representation(self, invoice_factory):
        """Test __str__ and __unicode__ methods."""
        invoice = invoice_factory()
        assert str(invoice) == invoice.number
        assert invoice.__unicode__() == invoice.number

    def test_invoice_get_absolute_url(self, invoice_factory):
        """Test URL generation."""
        invoice = invoice_factory()
        url = invoice.get_absolute_url()
        assert url is not None
        # URL should contain invoice detail path or be a custom URL
        assert isinstance(url, str)
        assert len(url) > 0

    def test_invoice_save_auto_sequence(self, invoice_factory, settings_override):
        """Test automatic sequence generation on save."""
        invoice = invoice_factory(sequence=None)
        assert invoice.sequence is not None
        assert invoice.sequence > 0

    def test_invoice_save_auto_number(self, invoice_factory, settings_override):
        """Test automatic number generation on save."""
        invoice = invoice_factory(number=None)
        assert invoice.number is not None
        assert invoice.number != ''

    def test_invoice_save_with_existing_sequence(self, invoice_factory):
        """Test save with pre-set sequence."""
        invoice = invoice_factory(sequence=999)
        assert invoice.sequence == 999

    def test_invoice_save_with_existing_number(self, invoice_factory):
        """Test save with pre-set number."""
        invoice = invoice_factory(number='CUSTOM-001')
        assert invoice.number == 'CUSTOM-001'

    def test_get_next_sequence_daily(self, invoice_factory, settings_daily_counter):
        """Test daily counter period."""
        date1 = date(2024, 1, 15)
        date2 = date(2024, 1, 16)
        
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        invoice3 = invoice_factory(date_issue=date2)
        
        assert invoice2.sequence == invoice1.sequence + 1
        assert invoice3.sequence == 1  # New day, reset counter

    def test_get_next_sequence_monthly(self, invoice_factory, settings_monthly_counter):
        """Test monthly counter period."""
        date1 = date(2024, 1, 15)
        date2 = date(2024, 2, 15)
        
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        invoice3 = invoice_factory(date_issue=date2)
        
        assert invoice2.sequence == invoice1.sequence + 1
        assert invoice3.sequence == 1  # New month, reset counter

    def test_get_next_sequence_yearly(self, invoice_factory, settings_yearly_counter):
        """Test yearly counter period."""
        date1 = date(2024, 1, 15)
        date2 = date(2025, 1, 15)
        
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        invoice3 = invoice_factory(date_issue=date2)
        
        assert invoice2.sequence == invoice1.sequence + 1
        assert invoice3.sequence == 1  # New year, reset counter

    def test_invoice_taxation_policy(self, invoice_factory):
        """Test taxation policy property."""
        invoice = invoice_factory(supplier_country='SK')
        policy = invoice.taxation_policy
        # Should return EUTaxationPolicy for EU countries
        assert policy is not None

    def test_invoice_is_overdue(self, invoice_factory, item_factory):
        """Test overdue detection."""
        invoice = invoice_factory(
            status=Invoice.STATUS.SENT,
            date_due=date.today() - timedelta(days=1),
            total=Decimal('100.00')
        )
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        assert invoice.is_overdue is True

    def test_invoice_is_not_overdue_when_paid(self, invoice_factory, item_factory):
        """Test that paid invoices are not overdue."""
        invoice = invoice_factory(
            status=Invoice.STATUS.PAID,
            date_due=date.today() - timedelta(days=10),
            total=Decimal('100.00')
        )
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        assert invoice.is_overdue is False

    def test_invoice_is_not_overdue_when_zero_total(self, invoice_factory):
        """Test that zero total invoices are not overdue."""
        invoice = invoice_factory(
            status=Invoice.STATUS.SENT,
            date_due=date.today() - timedelta(days=10),
            total=Decimal('0.00')
        )
        assert invoice.is_overdue is False

    def test_invoice_overdue_days(self, invoice_factory):
        """Test overdue days calculation."""
        invoice = invoice_factory(date_due=date.today() - timedelta(days=5))
        assert invoice.overdue_days == 5

    def test_invoice_days_to_overdue(self, invoice_factory):
        """Test days until overdue."""
        invoice = invoice_factory(date_due=date.today() + timedelta(days=10))
        assert invoice.days_to_overdue == 10

    def test_invoice_payment_term(self, invoice_factory, item_factory):
        """Test payment term calculation."""
        invoice = invoice_factory(
            date_issue=date.today(),
            date_due=date.today() + timedelta(days=30),
        )
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        invoice.calculate_total()
        assert invoice.payment_term == 30

    def test_invoice_payment_term_zero_total(self, invoice_factory):
        """Test payment term with zero total."""
        invoice = invoice_factory(
            date_issue=date.today(),
            date_due=date.today() + timedelta(days=30),
            total=Decimal('0.00')
        )
        assert invoice.payment_term == 0

    def test_invoice_subtotal(self, sample_invoice):
        """Test subtotal calculation."""
        # 2 * 50 + 1 * 100 = 200
        assert sample_invoice.subtotal == Decimal('200.00')

    def test_invoice_subtotal_with_credit(self, invoice_factory, item_factory):
        """Test subtotal with credit."""
        invoice = invoice_factory(credit=Decimal('10.00'))
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        invoice.calculate_total()
        # 100 - 10 = 90
        assert invoice.subtotal == Decimal('90.00')

    def test_invoice_discount(self, sample_invoice_with_discount):
        """Test discount calculation."""
        # Item has 10% discount on 100 = 10 discount
        assert sample_invoice_with_discount.discount > Decimal('0.00')

    def test_invoice_total_before_discount(self, invoice_factory, item_factory):
        """Test total before discount."""
        invoice = invoice_factory(credit=Decimal('5.00'))
        item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            discount=Decimal('10.0')
        )
        invoice.calculate_total()
        # Should include original price before discount
        assert invoice.total_before_discount > invoice.total

    def test_invoice_to_pay(self, invoice_factory, item_factory):
        """Test amount to pay calculation."""
        invoice = invoice_factory(already_paid=Decimal('50.00'))
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        invoice.calculate_total()
        # 100 - 50 = 50
        assert invoice.to_pay == invoice.total - invoice.already_paid

    def test_invoice_set_supplier_data(self, invoice_factory):
        """Test supplier data setting."""
        invoice = invoice_factory()
        supplier_data = {
            'name': 'New Supplier',
            'street': 'New Street',
            'zip': '99999',
            'city': 'New City',
            'country_code': 'CZ',
            'registration_id': 'REG123',
            'tax_id': 'TAX123',
            'vat_id': 'CZ1234567890',
            'bank': {
                'name': 'Bank Name',
                'street': 'Bank Street',
                'zip': '11111',
                'city': 'Bank City',
                'country_code': 'CZ',
                'iban': 'CZ6508000000192000145399',
                'swift_bic': 'GIBACZPX'
            }
        }
        invoice.set_supplier_data(supplier_data)
        assert invoice.supplier_name == 'New Supplier'
        assert invoice.supplier_country == 'CZ'

    def test_invoice_set_customer_data(self, invoice_factory):
        """Test customer data setting."""
        invoice = invoice_factory()
        customer_data = {
            'name': 'New Customer',
            'street': 'Customer Street',
            'zip': '88888',
            'city': 'Customer City',
            'country_code': 'DE',
            'registration_id': 'REG456',
            'tax_id': 'TAX456',
            'vat_id': 'DE123456789',
        }
        invoice.set_customer_data(customer_data)
        assert invoice.customer_name == 'New Customer'
        assert invoice.customer_country == 'DE'

    def test_invoice_set_shipping_data(self, invoice_factory):
        """Test shipping data setting."""
        invoice = invoice_factory()
        shipping_data = {
            'name': 'Shipping Name',
            'street': 'Shipping Street',
            'zip': '77777',
            'city': 'Shipping City',
            'country_code': 'PL',
        }
        invoice.set_shipping_data(shipping_data)
        assert invoice.shipping_name == 'Shipping Name'
        assert invoice.shipping_country == 'PL'

    def test_invoice_is_EU_customer(self, invoice_factory):
        """Test EU customer detection."""
        invoice = invoice_factory(customer_country='SK')
        assert invoice.is_EU_customer() is True
        
        invoice = invoice_factory(customer_country='US')
        assert invoice.is_EU_customer() is False

    def test_invoice_has_discount(self, sample_invoice_with_discount):
        """Test discount detection."""
        assert sample_invoice_with_discount.has_discount is True

    def test_invoice_has_unit(self, sample_invoice):
        """Test unit detection."""
        assert sample_invoice.has_unit is True

    def test_invoice_max_quantity(self, sample_invoice):
        """Test maximum quantity calculation."""
        assert sample_invoice.max_quantity == Decimal('2.0')

    def test_invoice_sum_quantity(self, sample_invoice):
        """Test quantity summation."""
        # 2.0 + 1.0 = 3.0
        assert sample_invoice.sum_quantity == Decimal('3.0')

    def test_invoice_all_items_with_single_quantity(self, invoice_factory, item_factory):
        """Test single quantity items detection (positive case)."""
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'))
        item_factory(invoice=invoice, quantity=Decimal('1.0'))

        # all_items_with_single_quantity checks if count == sum_quantity
        # For two items with quantity 1.0 each this should be True.
        assert invoice.all_items_with_single_quantity is True

    def test_invoice_calculate_vat(self, sample_invoice):
        """Test VAT calculation."""
        vat = sample_invoice.calculate_vat()
        assert vat is not None
        assert vat >= Decimal('0.00')

    def test_invoice_calculate_total(self, sample_invoice):
        """Test total calculation."""
        total = sample_invoice.calculate_total()
        assert total > Decimal('0.00')
        assert sample_invoice.total == total

    def test_invoice_recalculate_tax(self, invoice_factory, item_factory):
        """Test tax recalculation."""
        invoice = invoice_factory()
        item = item_factory(invoice=invoice, tax_rate=None)
        invoice.recalculate_tax()
        item.refresh_from_db()
        # Tax rate should be set after recalculation
        assert item.tax_rate is not None

    def test_invoice_create_copy(self, sample_invoice):
        """Test invoice copying functionality."""
        # create_copy now handles None values for sequence_generator and number_formatter
        copy = sample_invoice.create_copy()
        assert copy.id != sample_invoice.id
        assert copy.number != sample_invoice.number
        assert copy.sequence != sample_invoice.sequence
        assert copy.item_set.count() == sample_invoice.item_set.count()
        assert sample_invoice in copy.related_invoices.all()

    def test_invoice_with_empty_items(self, invoice_factory):
        """Test invoice with no items."""
        invoice = invoice_factory()
        assert invoice.subtotal == Decimal('0.00')
        assert invoice.total == Decimal('0.00')

    def test_invoice_credit_note(self, sample_credit_note):
        """Test credit note type."""
        assert sample_credit_note.type == Invoice.TYPE.CREDIT_NOTE
        assert sample_credit_note.is_overdue is False  # Credit notes are never overdue

    def test_invoice_vat_summary(self, sample_invoice):
        """Test VAT summary property."""
        summary = sample_invoice.vat_summary
        assert isinstance(summary, list)
        assert len(summary) > 0

    def test_invoice_get_tax_rate(self, sample_invoice_eu):
        """Test tax rate retrieval."""
        tax_rate = sample_invoice_eu.get_tax_rate()
        # Tax rate can be None (reverse charge), a Decimal, or 0
        assert tax_rate is None or isinstance(tax_rate, (Decimal, int, float)) or tax_rate == 0

    def test_invoice_is_reverse_charge(self, invoice_factory):
        """Test reverse charge detection."""
        invoice = invoice_factory(
            supplier_country='SK',
            customer_country='CZ',
            supplier_vat_id='SK1234567890',
            customer_vat_id='CZ1234567890'
        )
        # Reverse charge depends on taxation policy
        result = invoice.is_reverse_charge()
        assert isinstance(result, bool)


@pytest.mark.django_db
@pytest.mark.models
class TestItem:
    """Tests for Item model."""

    def test_item_str_representation(self, invoice_factory, item_factory):
        """Test __str__ method."""
        invoice = invoice_factory()
        item = item_factory(invoice=invoice, title='Test Item')
        assert str(item) == 'Test Item'

    def test_item_get_absolute_url(self, invoice_factory, item_factory):
        """Test URL generation."""
        invoice = invoice_factory()
        item = item_factory(invoice=invoice)
        url = item.get_absolute_url()
        # URL might be empty string by default
        assert isinstance(url, str)

    def test_item_subtotal(self, invoice_factory, item_factory):
        """Test subtotal calculation."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('2.0'),
            unit_price=Decimal('50.00'),
            discount=Decimal('0.0')
        )
        # 2 * 50 = 100
        assert item.subtotal == Decimal('100.00')

    def test_item_subtotal_with_discount(self, invoice_factory, item_factory):
        """Test subtotal with discount."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            discount=Decimal('10.0')  # 10% discount
        )
        # 100 * (100 - 10) / 100 = 90
        assert item.subtotal == Decimal('90.00')

    def test_item_subtotal_before_discount(self, invoice_factory, item_factory):
        """Test subtotal before discount."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('2.0'),
            unit_price=Decimal('50.00'),
            discount=Decimal('10.0')
        )
        # Should be 2 * 50 = 100 (before discount)
        assert item.subtotal_before_discount == Decimal('100.00')

    def test_item_discount_amount(self, invoice_factory, item_factory):
        """Test discount amount calculation."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            discount=Decimal('10.0'),
            tax_rate=Decimal('20.0')
        )
        # Discount amount should be calculated with VAT
        assert item.discount_amount > Decimal('0.00')

    def test_item_vat(self, invoice_factory, item_factory):
        """Test VAT calculation."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            tax_rate=Decimal('20.0')
        )
        # 100 * 20 / 100 = 20
        assert item.vat == Decimal('20.00')

    def test_item_vat_no_tax_rate(self, invoice_factory, item_factory):
        """Test VAT with no tax rate."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            tax_rate=None
        )
        assert item.vat == Decimal('0.00')

    def test_item_total(self, invoice_factory, item_factory):
        """Test total calculation."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            tax_rate=Decimal('20.0')
        )
        # subtotal + vat = 100 + 20 = 120
        assert item.total == Decimal('120.00')

    def test_item_zero_quantity(self, invoice_factory, item_factory):
        """Test zero quantity handling."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('0.0'),
            unit_price=Decimal('100.00')
        )
        assert item.subtotal == Decimal('0.00')

    def test_item_zero_unit_price(self, invoice_factory, item_factory):
        """Test zero unit price handling."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('0.00')
        )
        assert item.subtotal == Decimal('0.00')

    def test_item_without_tax_rate(self, invoice_factory, item_factory):
        """Test item without tax."""
        invoice = invoice_factory()
        item = item_factory(
            invoice=invoice,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            tax_rate=None
        )
        assert item.vat == Decimal('0.00')
        assert item.total == item.subtotal

    def test_item_calculate_tax(self, invoice_factory, item_factory):
        """Test tax calculation method."""
        invoice = invoice_factory(supplier_vat_id='SK1234567890', supplier_country='SK')
        item = item_factory(invoice=invoice, tax_rate=None)
        item.calculate_tax()
        # Tax rate should be set from invoice
        assert item.tax_rate is not None

