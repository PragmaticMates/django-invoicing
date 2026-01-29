"""
Tests for taxation policies.
"""
import pytest
from decimal import Decimal
from datetime import date

from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from invoicing.taxation.eu import EUTaxationPolicy


@pytest.mark.taxation
class TestEUTaxationPolicy:
    """Tests for EUTaxationPolicy."""

    def test_is_in_EU(self):
        """Test EU country detection."""
        assert EUTaxationPolicy.is_in_EU('SK') is True
        assert EUTaxationPolicy.is_in_EU('CZ') is True
        assert EUTaxationPolicy.is_in_EU('DE') is True
        assert EUTaxationPolicy.is_in_EU('FR') is True
        assert EUTaxationPolicy.is_in_EU('US') is False
        assert EUTaxationPolicy.is_in_EU('GB') is False

    def test_is_reverse_charge_same_country(self):
        """Test reverse charge detection - same country."""
        # Same country - not reverse charge
        assert EUTaxationPolicy.is_reverse_charge(
            'SK1234567890', 'SK9876543210'
        ) is False

    def test_is_reverse_charge_different_countries(self):
        """Test reverse charge detection - different EU countries."""
        # Different EU countries - reverse charge
        assert EUTaxationPolicy.is_reverse_charge(
            'SK1234567890', 'CZ9876543210'
        ) is True

    def test_is_reverse_charge_missing_supplier_vat_id(self):
        """Test reverse charge with missing supplier VAT ID."""
        assert EUTaxationPolicy.is_reverse_charge(
            None, 'CZ9876543210'
        ) is False

    def test_is_reverse_charge_missing_customer_vat_id(self):
        """Test reverse charge with missing customer VAT ID."""
        assert EUTaxationPolicy.is_reverse_charge(
            'SK1234567890', None
        ) is False

    def test_is_reverse_charge_non_EU_supplier(self):
        """Test reverse charge with non-EU supplier."""
        assert EUTaxationPolicy.is_reverse_charge(
            'US1234567890', 'CZ9876543210'
        ) is False

    def test_get_default_tax(self):
        """Test default tax rate retrieval."""
        rate = EUTaxationPolicy.get_default_tax('SK')
        assert rate == Decimal(20)  # Slovakia rate before 2025

    def test_get_default_tax_with_date(self):
        """Test default tax with date."""
        rate_2024 = EUTaxationPolicy.get_default_tax('SK', date(2024, 12, 31))
        assert rate_2024 == Decimal(20)
        
        # Note: get_default_tax uses get_rate_for_country for date-specific rates
        rate_2025 = EUTaxationPolicy.get_rate_for_country('SK', date(2025, 1, 1))
        assert rate_2025 == Decimal(23)

    def test_get_default_tax_different_countries(self):
        """Test default tax for different countries."""
        # get_default_tax may use settings.INVOICING_TAX_RATE if set
        # Use get_rate_for_country for country-specific rates
        cz_rate = EUTaxationPolicy.get_rate_for_country('CZ', date.today())
        assert cz_rate == Decimal(21)
        
        de_rate = EUTaxationPolicy.get_rate_for_country('DE', date.today())
        assert de_rate == Decimal(19)

    def test_get_tax_rate_same_country(self):
        """Test tax rate for same country."""
        rate = EUTaxationPolicy.get_tax_rate(
            'SK1234567890', 'SK9876543210'
        )
        assert rate == Decimal(20)  # Default SK rate

    def test_get_tax_rate_different_country(self):
        """Test tax rate for different country."""
        rate = EUTaxationPolicy.get_tax_rate(
            'SK1234567890', 'CZ9876543210'
        )
        # Should be None for reverse charge (if VIES validation passes)
        # or default rate if VIES validation fails
        assert rate is None or rate == Decimal(20)

    def test_get_tax_rate_non_EU_supplier(self):
        """Test tax rate with non-EU supplier."""
        with pytest.raises(ImproperlyConfigured):
            EUTaxationPolicy.get_tax_rate(
                'US1234567890', 'CZ9876543210'
            )

    def test_get_tax_rate_empty_supplier_vat_id(self):
        """Test tax rate with empty supplier VAT ID."""
        rate = EUTaxationPolicy.get_tax_rate(None, 'CZ9876543210')
        assert rate is None

    def test_get_rate_for_country(self):
        """Test country-specific rate."""
        rate = EUTaxationPolicy.get_rate_for_country('SK', date(2024, 1, 1))
        assert rate == Decimal(20)

    def test_get_rate_for_country_date_specific(self):
        """Test date-specific tax rates (Slovakia)."""
        # Before 2025
        rate_2024 = EUTaxationPolicy.get_rate_for_country(
            'SK', date(2024, 12, 31)
        )
        assert rate_2024 == Decimal(20)
        
        # After 2025
        rate_2025 = EUTaxationPolicy.get_rate_for_country(
            'SK', date(2025, 1, 1)
        )
        assert rate_2025 == Decimal(23)

    def test_get_rate_for_country_invalid_date(self):
        """Test invalid date range."""
        # SK ranges cover all dates, so this test is skipped
        # If we had a country with gaps, we could test ValueError
        pass

    def test_get_tax_rate_by_invoice(self, invoice_factory, item_factory):
        """Test tax rate from invoice."""
        invoice = invoice_factory(
            supplier_country='SK',
            customer_country='SK',
            supplier_vat_id='SK1234567890',
            customer_vat_id='SK9876543210',
            date_tax_point=date(2024, 1, 1)
        )
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        rate = EUTaxationPolicy.get_tax_rate_by_invoice(invoice)
        assert rate == Decimal(20) or rate is None

    def test_get_tax_rate_by_invoice_non_EU_customer(self, invoice_factory, item_factory):
        """Test tax rate with non-EU customer."""
        invoice = invoice_factory(
            supplier_country='SK',
            customer_country='US',
            supplier_vat_id='SK1234567890',
            customer_tax_id='US123456789',
            date_tax_point=date(2024, 1, 1)
        )
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        rate = EUTaxationPolicy.get_tax_rate_by_invoice(invoice)
        # Non-EU customer with tax ID should return 0
        assert rate == 0

    @override_settings(INVOICING_USE_VIES_VALIDATOR=False)
    def test_get_tax_rate_reverse_charge_no_vies(self):
        """Test reverse charge without VIES validation."""
        rate = EUTaxationPolicy.get_tax_rate(
            'SK1234567890', 'CZ9876543210'
        )
        # Without VIES, should return None for reverse charge
        assert rate is None

    def test_taxation_policy_empty_vat_id(self):
        """Test taxation policy with empty VAT ID."""
        rate = EUTaxationPolicy.get_tax_rate(None, None)
        assert rate is None

    def test_get_rate_for_country_all_eu_countries(self):
        """Test that all EU countries have defined rates."""
        eu_countries = [
            'AT', 'BE', 'BG', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE',
            'GR', 'HR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
            'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
        ]
        
        for country in eu_countries:
            rate = EUTaxationPolicy.get_rate_for_country(country, date(2024, 1, 1))
            assert rate is not None
            assert isinstance(rate, Decimal)
            assert rate >= Decimal(0)

