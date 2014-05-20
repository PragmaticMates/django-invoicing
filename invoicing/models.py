from __future__ import division

import collections

from decimal import Decimal
from django_iban.fields import IBANField, SWIFTBICField
from djmoney.forms.widgets import CURRENCY_CHOICES
from jsonfield import JSONField

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.validators import EMPTY_VALUES
from django.db import models
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField

from fields import VATField
from utils import import_name
from invoicing.taxation import TaxationPolicy
from invoicing.taxation.eu import EUTaxationPolicy


def next_number():
    try:
        last_invoice = Invoice.objects.all().order_by('-number')[0]
        return last_invoice.number + 1
    except IndexError:
        return getattr(settings, 'INVOICING_START_FROM', 1)


def default_supplier(attribute):
    supplier = getattr(settings, 'INVOICING_SUPPLIER', None)
    return supplier.get(attribute, None) if supplier else None


class Invoice(models.Model):
    TYPE_INVOICE = 'INVOICE'
    TYPE_ADVANCE = 'ADVANCE'
    TYPE_PROFORMA = 'PROFORMA'
    TYPE_VAT_CREDIT_NOTE = 'VAT_CREDIT_NOTE'
    TYPES = (
        (TYPE_INVOICE, _(u'Invoice')),
        (TYPE_ADVANCE, _(u'Advance invoice')),
        (TYPE_PROFORMA, _(u'Proforma invoice')),
        (TYPE_VAT_CREDIT_NOTE, _(u'VAT credit note')),
    )

    STATUS_NEW = 'NEW'
    STATUS_SENT = 'SENT'
    STATUS_RETURNED = 'RETURNED'
    STATUS_CANCELED = 'CANCELED'
    STATUS_PAID = 'PAID'
    STATUSES = (
        (STATUS_NEW, _(u'new')),
        (STATUS_SENT, _(u'sent')),
        (STATUS_RETURNED, _(u'returned')),
        (STATUS_CANCELED, _(u'canceled')),
        (STATUS_PAID, _(u'paid')),
    )

    PAYMENT_METHOD_BANK_TRANSFER = 'BANK_TRANSFER'
    PAYMENT_METHOD_CASH = 'CASH'
    PAYMENT_METHOD_CASH_ON_DELIVERY = 'CASH_ON_DELIVERY'
    PAYMENT_METHOD_PAYMENT_CARD = 'PAYMENT_CARD'
    PAYMENT_METHODS = (
        (PAYMENT_METHOD_BANK_TRANSFER, _(u'bank transfer')),
        (PAYMENT_METHOD_CASH, _(u'cash')),
        (PAYMENT_METHOD_CASH_ON_DELIVERY, _(u'cash on delivery')),
        (PAYMENT_METHOD_PAYMENT_CARD, _(u'payment card')),
    )
    DELIVERY_METHOD_PERSONAL_PICKUP = 'PERSONAL_PICKUP'
    DELIVERY_METHOD_MAILING = 'MAILING'
    DELIVERY_METHODS = (
        (DELIVERY_METHOD_PERSONAL_PICKUP, _(u'personal pickup')),
        (DELIVERY_METHOD_MAILING, _(u'mailing')),
    )
    CONSTANT_SYMBOLS = (
        ('0001', _(u'0001 - Payments for goods based on legal and executable decision from legal authority')),
        ('0008', _(u'0008 - Cashless payments for goods')),
        ('0038', _(u'0038 - Cashless funds for wages')),
        ('0058', _(u'0058 - Cashless penalty and delinquency charges')),
        ('0068', _(u'0068 - Transfer of funds for wages and other personal costs')),
        ('0138', _(u'0138 - Cashless deductions at source')),
        ('0168', _(u'0168 - Cashless payments in loans')),
        ('0178', _(u'0178 - Sales from provided services')),
        ('0298', _(u'0298 - Other cashless transfers')),
        ('0304', _(u'0304 - Prior payments for services')),
        ('0308', _(u'0308 - Cashless payments for services')),
        ('0358', _(u'0358 - Payments dedicated to payout through post offices')),
        ('0379', _(u'0379 - Other income, income from postal order')),
        ('0498', _(u'0498 - Payments in loans')),
        ('0558', _(u'0558 - Cashless other financial payments')),
        ('0934', _(u'0934 - Benefits - prior payments')),
        ('0968', _(u'0968 - Other cashless transfers')),
        ('1144', _(u'1144 - Prior payment - advance')),
        ('1148', _(u'1148 - Payment - current advance')),
        ('1744', _(u'1744 - Accounting of tax at income tax of physical body and corporate body')),
        ('1748', _(u'1748 - Income tax of physical body and corporate body based on declared tax year')),
        ('3118', _(u'3118 - Insurance and empl. contrib. to insur. co. and the Labor Office')),
        ('3344', _(u'3344 - Penalty from message - prior')),
        ('3354', _(u'3354 - Insurance payments by insurance companies')),
        ('3558', _(u'3558 - Cashless insurance payments by insurance companies')),
        ('8147', _(u'8147 - Payment (posted together with the instruction)'))
    )

    # General information
    type = models.CharField(_(u'type'), max_length=64, choices=TYPES,
        default=TYPE_INVOICE)
    prefix = models.CharField(_(u'number prefix'), max_length=255)
    number = models.IntegerField(_(u'number'), unique=True, default=next_number)
    status = models.CharField(_(u'status'), choices=STATUSES, max_length=64, default=STATUS_NEW)
    subtitle = models.CharField(_(u'subtitle'), max_length=255,
        blank=True, null=True, default=None)
    language = models.CharField(_(u'language'), max_length=2, choices=settings.LANGUAGES)
    note = models.CharField(_(u'note'), max_length=255,
        blank=True, null=True, default=_(u'Thank you for using our services.'))
    date_issue = models.DateTimeField(_(u'issue date'))
    date_tax_point = models.DateTimeField(_(u'tax point date'))  # time of supply
    date_due = models.DateTimeField(_(u'due date'))

    # Payment details
    currency = models.CharField(_(u'currency'), max_length=10, choices=CURRENCY_CHOICES)
    discount = models.DecimalField(_(u'discount (%)'), max_digits=3, decimal_places=1, default=0)
    credit = models.DecimalField(_(u'credit'), max_digits=10, decimal_places=2, default=0)
    #already_paid = models.DecimalField(_(u'already paid'), max_digits=10, decimal_places=2, default=0)

    payment_method = models.CharField(_(u'payment method'), choices=PAYMENT_METHODS, max_length=64)
    constant_symbol = models.CharField(_(u'constant symbol'), max_length=64, choices=CONSTANT_SYMBOLS,
        blank=True, null=True, default=None)
    variable_symbol = models.PositiveIntegerField(_(u'variable symbol'), max_length=10,
        blank=True, null=True, default=None)
    specific_symbol = models.PositiveIntegerField(_(u'specific symbol'), max_length=10,
        blank=True, null=True, default=None)
    reference = models.CharField(_(u'reference'), max_length=140,
        blank=True, null=True, default=None)

    bank = models.CharField(_(u'bank'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('bank'))
    bank_street = models.CharField(_(u'bank street and number'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('bank_street'))
    bank_zip = models.CharField(_(u'bank ZIP'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('bank_zip'))
    bank_city = models.CharField(_(u'bank city'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('bank_city'))
    bank_country = CountryField(_(u'bank country'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('bank_country_code'))
    bank_iban = IBANField(verbose_name=_(u'Account number (IBAN)'), default=lambda: default_supplier('bank_iban'))
    bank_swift_bic = SWIFTBICField(verbose_name=_(u'Bank SWIFT / BIC'), default=lambda: default_supplier('bank_swift_bic'))

    # Issuer details
    supplier_name = models.CharField(_(u'supplier name'), max_length=255, default=lambda: default_supplier('name'))
    supplier_street = models.CharField(_(u'supplier street and number'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('street'))
    supplier_zip = models.CharField(_(u'supplier ZIP'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('zip'))
    supplier_city = models.CharField(_(u'supplier city'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('city'))
    supplier_country = CountryField(_(u'supplier country'), default=lambda: default_supplier('country_code'))
    supplier_registration_id = models.CharField(_(u'supplier Reg. No.'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('registration_id'))
    supplier_tax_id = models.CharField(_(u'supplier Tax No.'), max_length=255,
        blank=True, null=True, default=lambda: default_supplier('tax_id'))
    supplier_vat_id = VATField(_(u'supplier VAT No.'),
        blank=True, null=True, default=lambda: default_supplier('vat_id'))
    supplier_additional_info = JSONField(_(u'supplier additional information'),
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        blank=True, null=True, default=lambda: default_supplier('additional_info'))  # for example www or legal matters
    # TODO:
    #supplier_logo

    # Contact details
    supplier_www = models.CharField(_(u'supplier www'), max_length=255,
        blank=True, null=True, default=None)
    issuer_name = models.CharField(_(u'issuer name'), max_length=255,
        blank=True, null=True, default=None)
    issuer_email = models.EmailField(_(u'issuer email'),
        blank=True, null=True, default=None)
    issuer_phone = models.CharField(_(u'issuer phone'), max_length=255,
        blank=True, null=True, default=None)

    # Customer details
    customer_name = models.CharField(_(u'customer name'), max_length=255)
    customer_street = models.CharField(_(u'customer street and number'), max_length=255,
        blank=True, null=True, default=None)
    customer_zip = models.CharField(_(u'customer ZIP'), max_length=255,
        blank=True, null=True, default=None)
    customer_city = models.CharField(_(u'customer city'), max_length=255,
        blank=True, null=True, default=None)
    customer_country = CountryField(_(u'customer country'))
    customer_registration_id = models.CharField(_(u'customer Reg. No.'), max_length=255,
        blank=True, null=True, default=None)
    customer_tax_id = models.CharField(_(u'customer Tax No.'), max_length=255,
        blank=True, null=True, default=None)
    customer_vat_id = VATField(_(u'customer VAT ID'),
        blank=True, null=True, default=None)
    customer_additional_info = JSONField(_(u'customer additional information'),
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        blank=True, null=True, default=None)

    # Shipping details
    shipping_name = models.CharField(_(u'shipping name'), max_length=255,
        blank=True, null=True, default=None)
    shipping_street = models.CharField(_(u'shipping street and number'), max_length=255,
        blank=True, null=True, default=None)
    shipping_zip = models.CharField(_(u'shipping ZIP'), max_length=255,
        blank=True, null=True, default=None)
    shipping_city = models.CharField(_(u'shipping city'), max_length=255,
        blank=True, null=True, default=None)
    shipping_country = CountryField(_(u'shipping country'),
        blank=True, null=True, default=None)

    # Delivery details
    delivery_method = models.CharField(_(u'delivery method'), choices=DELIVERY_METHODS, max_length=64,
        default=DELIVERY_METHOD_PERSONAL_PICKUP)

    # Other
    created = models.DateTimeField(_(u'created'), auto_now_add=True)
    modified = models.DateTimeField(_(u'modified'), auto_now=True)

    class Meta:
        db_table = 'invoicing_invoices'
        verbose_name = _(u'invoice')
        verbose_name_plural = _(u'invoices')
        ordering = ('date_issue', 'number')

    def __unicode__(self):
        return self.code

    @property
    def code(self):
        if self.prefix not in EMPTY_VALUES:
            return u'%s%s' % (self.prefix, self.number)
        return unicode(self.number)

    def get_absolute_url(self):
        return reverse('invoice_detail', args=(self.pk,))

    @property
    def taxation_policy(self):
        taxation_policy = getattr(settings, 'INVOICING_TAXATION_POLICY', None)
        if taxation_policy is not None:
            return import_name(taxation_policy)

        # Check if supplier is from EU
        if self.supplier_country:
            if EUTaxationPolicy.is_in_EU(self.supplier_country.code):
                return EUTaxationPolicy

        return None

    @property
    def is_overdue(self):
        return self.date_due < now() and self.status != self.STATUS_PAID

    @property
    def payment_term(self):
        return (self.date_due - self.date_issue).days

    def set_supplier_data(self, supplier):
        self.supplier_name = supplier.get('name')
        self.supplier_street = supplier.get('street', None)
        self.supplier_zip = supplier.get('zip', None)
        self.supplier_city = supplier.get('city', None)
        self.supplier_country = supplier.get('country_code')
        self.supplier_registration_id = supplier.get('registration_id', None)
        self.supplier_tax_id = supplier.get('tax_id', None)
        self.supplier_vat_id = supplier.get('vat_id', None)
        self.supplier_additional_info = supplier.get('additional_info', None)

        self.bank = supplier.get('bank')
        self.bank_street = supplier.get('bank_street')
        self.bank_zip = supplier.get('bank_zip')
        self.bank_city = supplier.get('bank_city')
        self.bank_country = supplier.get('bank_country_code')
        self.bank_iban = supplier.get('bank_iban')
        self.bank_swift_bic = supplier.get('bank_swift_bic')

    def set_customer_data(self, customer):
        self.customer_name = customer.get('name')
        self.customer_street = customer.get('street', None)
        self.customer_zip = customer.get('zip', None)
        self.customer_city = customer.get('city', None)
        self.customer_country = customer.get('country_code')
        self.customer_registration_id = customer.get('registration_id', None)
        self.customer_tax_id = customer.get('tax_id', None)
        self.customer_vat_id = customer.get('vat_id', None)
        self.customer_additional_info = customer.get('additional_info', None)
        
    def set_shipping_data(self, shipping):
        self.shipping_name = shipping.get('name', None)
        self.shipping_street = shipping.get('street', None)
        self.shipping_zip = shipping.get('zip', None)
        self.shipping_city = shipping.get('city', None)
        self.shipping_country = shipping.get('country_code', None)

    def is_supplier_vat_id_visible(self):
        # VAT is not 0
        if self.vat != 0:
            return True

        # VAT is 0, check if customer is from EU and from same country
        if self.customer_country:
            is_EU_customer = EUTaxationPolicy.is_in_EU(self.customer_country.code)
        else:
            is_EU_customer = False

        return is_EU_customer and self.supplier_country != self.customer_country

    @property
    def subtotal(self):
        sum = 0
        for item in self.invoiceitem_set.all():
            sum += item.quantity * item.unit_price  # item subtotal
        return sum

    @property
    def vat(self):
        vat = 0
        for item in self.invoiceitem_set.all():
            vat += item.vat
        return vat

    @property
    def total(self):
        total = self.subtotal + self.vat  # subtotal with vat
        total *= ((100 - Decimal(self.discount)) / 100)  # subtract discount amount
        total -= self.credit  # subtract credit
        #total -= self.already_paid  # subtract already paid

        # round to two decimal places
        TWOPLACES = Decimal(10) ** -2
        total = round(total, 2)
        total = Decimal(total).quantize(TWOPLACES)
        return total if total >= 0 else 0


class InvoiceItem(models.Model):
    WEIGHT = [(i, i) for i in range(0, 20)]
    UNIT_EMPTY = 'EMPTY'
    UNIT_PIECES = 'PIECES'
    UNIT_HOURS = 'HOURS'
    UNITS = (
        (UNIT_EMPTY, ''),
        (UNIT_PIECES, _(u'pcs.')),
        (UNIT_HOURS, _(u'hours'))
    )

    invoice = models.ForeignKey(Invoice, verbose_name=_(u'invoice'))
    title = models.CharField(_(u'title'), max_length=255)
    quantity = models.DecimalField(_(u'quantity'), max_digits=10, decimal_places=3, default=1)
    unit = models.CharField(_(u'unit'), choices=UNITS, max_length=64, default=UNIT_PIECES)
    unit_price = models.DecimalField(_(u'unit price'), max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(_(u'tax rate (%)'), max_digits=3, decimal_places=1,
        blank=True, null=True, default=None)
    weight = models.IntegerField(_(u'weight'), choices=WEIGHT, blank=True, null=True, default=0)
    created = models.DateTimeField(_(u'created'), auto_now_add=True)
    modified = models.DateTimeField(_(u'modified'), auto_now=True)

    class Meta:
        db_table = 'invoicing_items'
        verbose_name = _(u'item')
        verbose_name_plural = _(u'items')
        ordering = ('-invoice', 'weight', 'created')

    def __unicode__(self):
        return self.title

    @property
    def price(self):
        return self.unit_price * self.quantity

    @property
    def vat(self):
        return self.price * self.tax_rate / 100 if self.tax_rate else 0

    @property
    def subtotal(self):
        return self.price + self.vat

    def save(self, **kwargs):
        if self.tax_rate in EMPTY_VALUES and self.pk is None:
            if self.invoice.taxation_policy:
                # There is taxation policy -> get tax rate
                customer_country_code = self.invoice.customer_country.code if self.invoice.customer_country else None
                self.tax_rate = self.invoice.taxation_policy.get_tax_rate(self.invoice.customer_vat_id, customer_country_code)
            else:
                # If there is not any special taxation policy, set default tax rate
                self.tax_rate = TaxationPolicy.get_default_tax()
                #self.tax_rate = getattr(settings, 'INVOICING_TAX_RATE')

        return super(InvoiceItem, self).save(**kwargs)
