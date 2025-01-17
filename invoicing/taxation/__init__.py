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
    def get_default_tax(cls, country_code=None, tax_point_date=None):
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
    def get_tax_rate(cls, supplier_vat_id, customer_vat_id):
        """
        Methods

        :param supplier_vat_id: supplier vat id
        :param customer_vat_id: customer vat id
        :return: Decimal()
        """
        raise NotImplementedError('Method get_tax_rate should be implemented.')

    @classmethod
    def get_tax_rate_by_invoice(cls, invoice):
        """
        Methods

        :param invoice: invoice
        :return: Decimal()
        """
        return cls.get_tax_rate(invoice.supplier_vat_id, invoice.customer_vat_id)

    @classmethod
    def calculate_tax(cls, price, tax_rate):
        """
        Methods

        :param price: price
        :param tax_rate: tax rate
        :return: Decimal()
        """
        return price * (tax_rate / 100) if tax_rate and price else 0