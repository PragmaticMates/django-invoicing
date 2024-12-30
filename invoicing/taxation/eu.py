from datetime import date
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
        'SK': [
            {"from": date.min, "to": date(2024, 12, 31), "rate": Decimal(20)},
            {"from": date(2025, 1, 1), "to": date.max, "rate": Decimal(23)},
        ], # Slovakia
        'SI': Decimal(22),  # Slovenia
        'ES': Decimal(21),  # Spain
        'SE': Decimal(25),  # Sweden
        # 'GB': Decimal(20),  # United Kingdom (Great Britain) - not in EU since 1.2.2020
    }

    @classmethod
    def is_in_EU(cls, country_code):
        return country_code.upper() in cls.EU_COUNTRIES_RATES.keys()

    @classmethod
    def is_reverse_charge(cls, invoice, delivery_country=None, check_items=True):
        supplier_country = invoice.supplier_country.code if invoice.supplier_country else None

        if not supplier_country:
            supplier_country = cls.get_supplier_country_code()

        # Supplier has to be from EU
        if not cls.is_in_EU(supplier_country):
            return False

        # Supplier VAT ID has to be set
        if invoice.supplier_vat_id in EMPTY_VALUES:
            return False

        # Customer VAT ID has to be set
        if invoice.customer_vat_id in EMPTY_VALUES:
            return False

        # Place of supply is either delivery country or customer country
        place_of_supply = delivery_country or invoice.customer_country

        # missing place of supply
        if place_of_supply in EMPTY_VALUES:
            return False

        # supplier and delivery countries have to be different
        if invoice.supplier_country == place_of_supply:
            return False

        # there has to be at least one invoice item with None tax rate
        if check_items and invoice.item_set.exists() and not invoice.item_set.filter(tax_rate=None).exists():
            return False

        # customer has to be from EU -> not True (for example Great Britain)
        # if not invoice.is_EU_customer():
        #     return False

        return True

    # TODO: rename to get_default_tax_rate
    @classmethod
    def get_default_tax(cls, country_code=None, tax_point_date=None):
        """
        Gets default tax rate.``

        :param country_code: The ISO country code
        :param tax_point_date: The date of the tax point (date object)
        :return: Decimal()
        """
        # Use the current time if tax_point_date is not provided
        if tax_point_date is None:
            tax_point_date = date.today()

        default_tax_rate = super().get_default_tax(country_code, tax_point_date)

        # If country code and tax point date are provided, fetch the rate
        if country_code and not hasattr(settings, 'INVOICING_TAX_RATE'):
            return cls.get_rate_for_country(country_code, tax_point_date)

        return default_tax_rate

    @classmethod
    def get_tax_rate(cls, invoice):
        if invoice.supplier_vat_id in EMPTY_VALUES:
            # Supplier is not a VAT payer
            return None

        # customer_country = invoice.customer_country.code if invoice.customer_country else None
        supplier_country = invoice.supplier_country.code if invoice.supplier_country else None

        if not supplier_country:
            supplier_country = cls.get_supplier_country_code()

        if not cls.is_in_EU(supplier_country):
            raise ImproperlyConfigured("EUTaxationPolicy requires that supplier country is in EU")

        # Reverse charge
        if cls.is_reverse_charge(invoice, check_items=False):
            if not getattr(settings, 'INVOICING_USE_VIES_VALIDATOR', True):
                return None

            try:
                # Verify VAT ID in VIES
                VATNumberValidator(eu_only=True, vies_check=True)(invoice.customer_vat_id)

                # Company is registered in VIES
                # Charge back
                return None
            except ValidationError:
                pass

        # return default tax
        return cls.get_default_tax(supplier_country, invoice.date_tax_point)

    @classmethod
    def get_rate_for_country(cls, country_code, tax_point_date):
        """
        Gets the tax rate for a specific country and date.

        :param country_code: ISO country code
        :param tax_point_date: Date for which the tax rate applies (date object)
        :return: Decimal
        """
        # Get default tax rate
        default_tax_rate = super().get_default_tax(country_code, tax_point_date)

        # Find rate definition for the country
        rates = cls.EU_COUNTRIES_RATES.get(country_code, default_tax_rate)

        # If rates are defined as a list (date-specific), determine the applicable rate
        if isinstance(rates, list):
            for rate_period in rates:
                if rate_period["from"] <= tax_point_date <= rate_period["to"]:
                    return rate_period["rate"]
            # Fallback if no date range matches (unlikely if ranges are defined properly)
            raise ValueError(f"No valid tax rate found for {country_code} on {tax_point_date}")

        # If rates are not date-specific, return the flat rate
        return rates