from django.conf import settings


class TaxationPolicy(object):
    """
    Abstract class for defining taxation policies.
    Taxation policy is a way to handle what tax rate should be put on the invoice items by default if not set any.
    It depends on customer billing data.

    Custom taxation policy should implement only method
    ``get_tax_rate(invoice)``.
    This method should return a percent value (even 0) of tax that should be added to the invoice item
    or None if tax is not applicable or is reverse charged.
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
    def get_tax_rate(cls, invoice):
        """
        Methods

        :param invoice: invoice
        :return: Decimal()
        """
        raise NotImplementedError('Method get_tax_rate should be implemented.')
