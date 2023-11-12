from collections import OrderedDict

from invoicing.models import Invoice
from invoicing.utils import get_invoices_in_pdf

from django.utils.translation import gettext_lazy as _, gettext

from outputs.mixins import ExporterMixin, ExcelExporterMixin, FilterExporterMixin
from outputs.models import Export
from pragmatic.utils import compress


# TODO: inherit from filterexporter mixin?
# class InvoiceXlsxListExporter(FilterExporterMixin, ExcelExporterMixin):
class InvoiceXlsxListExporter(ExcelExporterMixin):
    # filter_class = InvoiceFilter
    model = Invoice
    queryset = None
    filename = _('invoices.xlsx')

    @classmethod
    def get_model(cls):
        return cls.queryset.model if cls.queryset is not None else cls.model

    @classmethod
    def get_app_and_model(cls):
        return cls.get_model()._meta.label.split('.')

    @staticmethod
    def selectable_fields():
        # attribute, label, width, format (self.FORMATS), value
        return OrderedDict({
            gettext('Details'): [
                ('id', gettext('ID'), 7, 'integer'),
                ('created', gettext('Created'), 20, 'datetime'),
                ('get_type_display', gettext('Type'), 10, None, lambda value: value()),
                ('sequence', gettext('Sequence'), 10),
                ('number', gettext('Number'), 15),
                ('get_status_display', gettext('Status'), 10, None, lambda value: value()),
                ('subtitle', gettext('Subtitle'), 20),
                ('get_language_display', gettext('Language'), 10, None, lambda value: value()),
                ('note', gettext('Note'), 30),
            ],
            gettext('Dates'): [
                ('date_issue', gettext('Issue date'), 15, 'date'),
                ('date_tax_point', gettext('Tax point date'), 15, 'date'),
                ('date_due', gettext('Due date'), 15, 'date'),
                ('date_sent', gettext('Sent (date)'), 15, 'date'),
                ('date_paid', gettext('Date of payment'), 15, 'date', lambda value: value.date() if value else None),
                ('payment_term', gettext('Payment term (days)'), 15, 'integer'),
                ('overdue_days', gettext('Overdue (days)'), 15, 'integer', lambda value, obj: (
                    '=IF(TODAY()<=%(date_due)d, "", _xlfn.DAYS(TODAY(),%(date_due)d))' % {
                        'date_due': ExcelExporterMixin.to_excel_datetime(obj.date_due)
                    } if obj.status not in [Invoice.STATUS.PAID, Invoice.STATUS.CANCELED] else '', obj.overdue_days if obj.is_overdue else '')),
            ],
            gettext('Payment'): [
                ('total', gettext('Total'), 10),
                ('vat', gettext('VAT'), 10),
                ('get_currency_display', gettext('Currency'), 10, None, lambda value: value()),
                ('credit', gettext('Credit'), 10),
                ('get_payment_method_display', gettext('Payment method'), 20, None, lambda value: value()),
                ('constant_symbol', gettext('Constant symbol'), 20),
                ('variable_symbol', gettext('Variable symbol'), 20),
                ('specific_symbol', gettext('Specific symbol'), 20),
                ('reference', gettext('Reference'), 20),
                ('bank_name', gettext('Bank name'), 20),
                # ('bank_street', gettext('Bank street'), 20),
                # ('bank_zip', gettext('Bank zip'), 15),
                # ('bank_city', gettext('Bank city'), 20),
                # ('get_bank_country_display', gettext('Bank country'), 20, None, lambda value: value()),
                ('bank_iban', gettext('IBAN'), 30),
                ('bank_swift_bic', gettext('SWIFT/BIC'), 15),
            ],
            gettext('Issuer'): [
                ('supplier_name', gettext('Supplier name'), 20),
                ('supplier_street', gettext('Supplier street'), 20),
                ('supplier_zip', gettext('Supplier zip'), 15),
                ('supplier_city', gettext('Supplier city'), 15),
                ('get_supplier_country_display', gettext('Supplier country'), 20, None, lambda value: value()),
                ('supplier_registration_id', gettext('Supplier reg. ID'), 20),
                ('supplier_tax_id', gettext('Supplier tax ID'), 20),
                ('supplier_vat_id', gettext('Supplier VAT ID'), 20),
                ('supplier_additional_info', gettext('Supplier additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('issuer_name', gettext('Issuer name'), 20),
                ('issuer_email', gettext('Issuer email'), 30),
                ('issuer_phone', gettext('Issuer phone'), 30),
            ],
            gettext('Customer'): [
                ('customer_name', gettext('Customer name'), 20),
                ('customer_street', gettext('Customer street'), 20),
                ('customer_zip', gettext('Customer zip'), 15),
                ('customer_city', gettext('Customer city'), 20),
                ('get_customer_country_display', gettext('Customer country'), 20, None, lambda value: value()),
                ('customer_registration_id', gettext('Customer reg. ID'), 20),
                ('customer_tax_id', gettext('Customer tax ID'), 20),
                ('customer_vat_id', gettext('Customer VAT ID'), 20),
                ('customer_additional_info', gettext('Customer additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('customer_email', gettext('Customer email'), 30),
                ('customer_phone', gettext('Customer phone'), 30),
            ],
            # gettext('Shipping'): [
            #     ('shipping_name', gettext('Shipping name'), 20),
            #     ('shipping_street', gettext('Shipping street'), 20),
            #     ('shipping_zip', gettext('Shipping zip'), 15),
            #     ('shipping_city', gettext('Shipping city'), 20),
            #     ('get_shipping_country_display', gettext('Shipping country'), 20, None, lambda value: value()),
            #     ('get_delivery_method_display', gettext('Delivery method'), 20, None, lambda value: value()),
            # ],
        })

    # def get_whole_queryset(self, params):
    #     return super().get_whole_queryset(params) \
    #         .order_by('-created').distinct()
    #         # .prefetch_related(Prefetch('item_set', queryset=Item.objects.all())) \

    def get_worksheet_title(self, index=0):
        return gettext('Invoices')

    def get_queryset(self):
        return self.queryset


class InvoicePdfDetailExporter(ExporterMixin):
    queryset = Invoice.objects.all()
    export_format = Export.FORMAT_PDF
    export_context = Export.CONTEXT_DETAIL
    filename = _('invoices.zip')

    def get_queryset(self):
        return self.queryset

    def export(self):
        self.write_data(self.output)

    def write_data(self, output):
        export_files = get_invoices_in_pdf(self.get_queryset())

        if len(export_files) == 1:
            # directly export 1 PDF file
            file_data = export_files[0]
            self.filename = file_data['name']
            output.write(file_data['content'])
        else:
            # compress all invoices into single archive file
            output.write(compress(export_files).read())
