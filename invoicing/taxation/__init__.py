from django.conf import settings


class TaxationPolicy(object):
    """
    Abstract class for defining taxation policies.
    Taxation policy is a way to handle what tax rate should be put on the invoice items by default if not set any.
    It depends on customer billing data.

    Custom taxation policy should implement only method
    ``get_tax_rate(vat_id, customer_country_code, supplier_country_code)``.
    This method should return a percent value of tax that should be added to the invoice item
    or 0 if tax is not applicable.
    """

    @classmethod
    def get_default_tax(cls, country_code=None):
        """
        Gets default tax rate.``

        :return: Decimal()
        """
        return getattr(settings, 'INVOICING_TAX_RATE', None)

    @classmethod
    def get_supplier_country_code(cls):
        """
        Gets suppliers country.``

        :return: unicode
        """
        supplier = getattr(settings, 'INVOICING_SUPPLIER')
        return supplier['country_code']

    @classmethod
    def get_tax_rate(cls, vat_id, customer_country_code, supplier_country_code, supplier_is_vat_payer):
        """
        Methods

        :param vat_id: customer vat id
        :param customer_country_code: customer country in ISO 2-letters format
        :param supplier_country_code: supplier country in ISO 2-letters format
        :param supplier_is_vat_payer: defines whether the supplier is a VAT payer or not.
        :return: Decimal()
        """
        raise NotImplementedError('Method get_tax_rate should be implemented.')
