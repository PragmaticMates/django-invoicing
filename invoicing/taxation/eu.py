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
        'EE': Decimal(20),  # Estonia
        'FI': Decimal(24),  # Finland
        'FR': Decimal(20),  # France
        'DE': Decimal(19),  # Germany
        'GR': Decimal(24),  # Greece
        'HR': Decimal(25),  # Croatia
        'HU': Decimal(27),  # Hungary
        'IE': Decimal(21),  # Ireland
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
        'GB': Decimal(20),  # United Kingdom (Great Britain)
    }

    @classmethod
    def is_in_EU(cls, country_code):
        if country_code == 'GB':
            return False

        return country_code.upper() in cls.EU_COUNTRIES_RATES.keys()

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
    def get_empty_tax_rate(cls, supplier_is_vat_payer):
        return 0 if supplier_is_vat_payer else None

    @classmethod
    def get_tax_rate(cls, vat_id, customer_country, supplier_country=None, supplier_is_vat_payer=None):

        if supplier_is_vat_payer is False:
            # Supplier is not a vat payer
            return None

        if not supplier_country:
            supplier_country = cls.get_supplier_country_code()

        if not cls.is_in_EU(supplier_country):
            raise ImproperlyConfigured("EUTaxationPolicy requires that supplier country is in EU")

        if vat_id in EMPTY_VALUES:
            # We don't know VAT ID

            if customer_country in EMPTY_VALUES:
                # We don't know VAT ID or country
                return cls.get_default_tax(supplier_country)

            # Customer is not a company, we know his country

            if cls.is_in_EU(customer_country):
                # Customer (private person) is from a EU
                # He must pay full VAT of our country
                return cls.get_default_tax(supplier_country)
            else:
                # Customer (private person) is not from EU
                # charge back
                return cls.get_empty_tax_rate(supplier_is_vat_payer)

        # Customer is company, we know country and VAT ID

        if customer_country.upper() == supplier_country.upper():
            # Company is from the same country as supplier
            # Normal tax
            return cls.get_default_tax(supplier_country)

        if not cls.is_in_EU(customer_country):
            # Company is not from EU
            # Charge back
            return cls.get_empty_tax_rate(supplier_is_vat_payer)

        # Company is from other EU country
        use_vies_validator = getattr(settings, 'INVOICING_USE_VIES_VALIDATOR', True)

        if not use_vies_validator:
            # trust VAT ID is correct
            # Charge back
            return cls.get_empty_tax_rate(supplier_is_vat_payer)

        try:
            # verify VAT ID in VIES
            VATNumberValidator(eu_only=True, vies_check=True)(vat_id)

            # Company is registered in VIES
            # Charge back
            return cls.get_empty_tax_rate(supplier_is_vat_payer)
        except ValidationError:
            return cls.get_default_tax(supplier_country)
