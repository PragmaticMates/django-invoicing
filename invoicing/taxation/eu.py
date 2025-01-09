from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import EMPTY_VALUES
from internationalflavor.vat_number import VATNumberValidator

from invoicing.taxation import TaxationPolicy


class EUTaxationPolicy(TaxationPolicy):
    """
    This taxation policy should be correct for all EU countries. It uses following rules:
        * if supplier country is not in EU - assert error,
        * return 'default tax' in cases:
            * if supplier country and customer country are the same,
            * if supplier country and customer country are not the same, but customer is private person from EU,
            * if supplier country and customer country are not the same, customer is company from EU, but his VAT ID is not valid according VIES system.
        * return tax not applicable (None) in cases:
            * if supplier country and customer country are not the same, customer is company from EU and his tax id is valid according VIES system.
            * if supplier country and customer country are not the same and customer is private person not from EU,
            * if supplier country and customer country are not the same and customer is company not from EU.


    Please note, that term "private person" refers in system to user that did not provide tax ID and
    ``company`` refers to user that provides it.

    """
    EU_COUNTRIES_RATES = {
        'AT': Decimal(20),  # Austria
        'BE': Decimal(21),  # Belgium
        'BG': Decimal(20),  # Bulgaria
        'CY': Decimal(19),  # Cyprus
        'CZ': Decimal(21),  # Czech Republic
        'DK': Decimal(25),  # Denmark
        'EE': Decimal(22),  # Estonia
        'FI': Decimal(24),  # Finland
        'FR': Decimal(20),  # France
        'DE': Decimal(19),  # Germany
        'GR': Decimal(24),  # Greece
        'HR': Decimal(25),  # Croatia
        'HU': Decimal(27),  # Hungary
        'IE': Decimal(23),  # Ireland
        'IT': Decimal(22),  # Italy
        'LV': Decimal(21),  # Latvia
        'LT': Decimal(21),  # Lithuania
        'LU': Decimal(17),  # Luxembourg
        'MT': Decimal(18),  # Malta
        'NL': Decimal(21),  # Netherlands
        'PL': Decimal(23),  # Poland
        'PT': Decimal(23),  # Portugal
        'RO': Decimal(19),  # Romania
        'SK': Decimal(20),  # Slovakia
        'SI': Decimal(22),  # Slovenia
        'ES': Decimal(21),  # Spain
        'SE': Decimal(25),  # Sweden
        # 'GB': Decimal(20),  # United Kingdom (Great Britain)
    }

    @classmethod
    def is_in_EU(cls, country_code):
        return country_code.upper() in cls.EU_COUNTRIES_RATES.keys()

    @classmethod
    def is_reverse_charge_by_vat_id(cls, supplier_vat_id, supplier_country, customer_vat_id, customer_country):
        if supplier_country:
            supplier_country = supplier_country.code if hasattr(supplier_country, 'code') else supplier_country

        if customer_country:
            customer_country = customer_country.code if hasattr(customer_country, 'code') else customer_country

        if supplier_country is None or customer_country is None:
            return False

        if not cls.is_in_EU(supplier_country):
            return False

        # Supplier VAT ID has to be set
        if supplier_vat_id in EMPTY_VALUES:
            return False

        # Customer VAT ID has to be set
        if customer_vat_id in EMPTY_VALUES:
            return False

        # Same supplier country as place of supply
        if supplier_country == customer_country:
            return False

        return True


    @classmethod
    def is_reverse_charge(cls, invoice, delivery_country=None, check_items=True):
        if check_items and invoice.item_set.exists() and not invoice.item_set.filter(tax_rate=None).exists():
            return False

        return cls.is_reverse_charge_by_vat_id(
            supplier_vat_id=invoice.supplier_vat_id,
            supplier_country=invoice.supplier_country,
            customer_vat_id=invoice.customer_vat_id,
            customer_country=delivery_country if delivery_country else invoice.customer_country,
        )

    @classmethod
    def get_default_tax(cls, country_code=None):
        """
        Gets default tax rate.``

        :return: Decimal()
        """

        default_tax_rate = super().get_default_tax(country_code)

        # tax rate by country
        if country_code and not hasattr(settings, 'INVOICING_TAX_RATE'):
            return cls.EU_COUNTRIES_RATES.get(country_code, default_tax_rate)

        return default_tax_rate

    @classmethod
    def get_tax_rate_by_vat_id(cls, supplier_vat_id, supplier_country, customer_vat_id, customer_country):
        if supplier_vat_id in EMPTY_VALUES:
            return None

        if supplier_country:
            supplier_country = supplier_country.code if hasattr(supplier_country, 'code') else supplier_country

        if not supplier_country:
            supplier_country = cls.get_supplier_country_code()

        if not cls.is_in_EU(supplier_country):
            raise ImproperlyConfigured("EUTaxationPolicy requires that supplier country is in EU")

        # Reverse charge
        if cls.is_reverse_charge_by_vat_id(supplier_vat_id, supplier_country, customer_vat_id, customer_country):
            if not getattr(settings, 'INVOICING_USE_VIES_VALIDATOR', True):
                return None

            try:
                # Verify VAT ID in VIES
                VATNumberValidator(eu_only=True, vies_check=True)(customer_vat_id)

                # Company is registered in VIES
                # Charge back
                return None
            except ValidationError:
                pass

        # return default tax
        return cls.get_default_tax(supplier_country)

    @classmethod
    def get_tax_rate(cls, invoice):
        return cls.get_tax_rate_by_vat_id(
            supplier_vat_id=invoice.supplier_vat_id,
            supplier_country=invoice.supplier_country,
            customer_vat_id=invoice.customer_vat_id,
            customer_country=invoice.customer_country,
        )
