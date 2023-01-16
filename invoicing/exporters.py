import binascii
from collections import OrderedDict

from invoicing.models import Invoice

from requests_futures import sessions

from django.conf import settings
from django.utils.translation import ugettext_lazy as _, ugettext

from invoicing.utils import import_name

from outputs.mixins import ExporterMixin, ExcelExporterMixin, FilterExporterMixin
from outputs.models import Export
from pragmatic.utils import compress


class InvoiceXlsxListExporter(FilterExporterMixin, ExcelExporterMixin):
    # filter_class = InvoiceFilter
    model = Invoice
    queryset = None
    filename = _('invoices.xlsx')

    @staticmethod
    def selectable_fields():
        # attribute, label, width, format (self.FORMATS), value
        return OrderedDict({
            ugettext('Details'): [
                ('id', ugettext('ID'), 7, 'integer'),
                ('created', ugettext('Created'), 20, 'datetime'),
                ('get_type_display', ugettext('Type'), 10, None, lambda value: value()),
                ('sequence', ugettext('Sequence'), 10),
                ('number', ugettext('Number'), 15),
                ('get_status_display', ugettext('Status'), 10, None, lambda value: value()),
                ('subtitle', ugettext('Subtitle'), 20),
                ('get_language_display', ugettext('Language'), 10, None, lambda value: value()),
                ('note', ugettext('Note'), 30),
            ],
            ugettext('Dates'): [
                ('date_issue', ugettext('Issue date'), 15, 'date'),
                ('date_tax_point', ugettext('Tax point date'), 15, 'date'),
                ('date_due', ugettext('Due date'), 15, 'date'),
                ('date_sent', ugettext('Sent (date)'), 15, 'date'),
                ('date_paid', ugettext('Date of payment'), 15, 'date', lambda value: value.date() if value else None),
                ('payment_term', ugettext('Payment term (days)'), 15, 'integer'),
                ('overdue_days', ugettext('Overdue (days)'), 15, 'integer', lambda value, obj: (
                    '=IF(TODAY()<=%(date_due)d, "", _xlfn.DAYS(TODAY(),%(date_due)d))' % {
                        'date_due': ExcelExporterMixin.to_excel_datetime(obj.date_due)
                    } if obj.status not in [Invoice.STATUS.PAID, Invoice.STATUS.CANCELED] else '', obj.overdue_days if obj.is_overdue else '')),
            ],
            ugettext('Payment'): [
                ('total', ugettext('Total'), 10),
                ('vat', ugettext('VAT'), 10),
                ('get_currency_display', ugettext('Currency'), 10, None, lambda value: value()),
                ('credit', ugettext('Credit'), 10),
                ('get_payment_method_display', ugettext('Payment method'), 20, None, lambda value: value()),
                ('constant_symbol', ugettext('Constant symbol'), 20),
                ('variable_symbol', ugettext('Variable symbol'), 20),
                ('specific_symbol', ugettext('Specific symbol'), 20),
                ('reference', ugettext('Reference'), 20),
                ('bank_name', ugettext('Bank name'), 20),
                # ('bank_street', ugettext('Bank street'), 20),
                # ('bank_zip', ugettext('Bank zip'), 15),
                # ('bank_city', ugettext('Bank city'), 20),
                # ('get_bank_country_display', ugettext('Bank country'), 20, None, lambda value: value()),
                ('bank_iban', ugettext('IBAN'), 30),
                ('bank_swift_bic', ugettext('SWIFT/BIC'), 15),
            ],
            ugettext('Issuer'): [
                ('supplier_name', ugettext('Supplier name'), 20),
                ('supplier_street', ugettext('Supplier street'), 20),
                ('supplier_zip', ugettext('Supplier zip'), 15),
                ('supplier_city', ugettext('Supplier city'), 15),
                ('get_supplier_country_display', ugettext('Supplier country'), 20, None, lambda value: value()),
                ('supplier_registration_id', ugettext('Supplier reg. ID'), 20),
                ('supplier_tax_id', ugettext('Supplier tax ID'), 20),
                ('supplier_vat_id', ugettext('Supplier VAT ID'), 20),
                ('supplier_additional_info', ugettext('Supplier additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('issuer_name', ugettext('Issuer name'), 20),
                ('issuer_email', ugettext('Issuer email'), 30),
                ('issuer_phone', ugettext('Issuer phone'), 30),
            ],
            ugettext('Customer'): [
                ('customer_name', ugettext('Customer name'), 20),
                ('customer_street', ugettext('Customer street'), 20),
                ('customer_zip', ugettext('Customer zip'), 15),
                ('customer_city', ugettext('Customer city'), 20),
                ('get_customer_country_display', ugettext('Customer country'), 20, None, lambda value: value()),
                ('customer_registration_id', ugettext('Customer reg. ID'), 20),
                ('customer_tax_id', ugettext('Customer tax ID'), 20),
                ('customer_vat_id', ugettext('Customer VAT ID'), 20),
                ('customer_additional_info', ugettext('Customer additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('customer_email', ugettext('Customer email'), 30),
                ('customer_phone', ugettext('Customer phone'), 30),
            ],
            # ugettext('Shipping'): [
            #     ('shipping_name', ugettext('Shipping name'), 20),
            #     ('shipping_street', ugettext('Shipping street'), 20),
            #     ('shipping_zip', ugettext('Shipping zip'), 15),
            #     ('shipping_city', ugettext('Shipping city'), 20),
            #     ('get_shipping_country_display', ugettext('Shipping country'), 20, None, lambda value: value()),
            #     ('get_delivery_method_display', ugettext('Delivery method'), 20, None, lambda value: value()),
            # ],
        })

    # def get_whole_queryset(self, params):
    #     return super().get_whole_queryset(params) \
    #         .order_by('-created').distinct()
    #         # .prefetch_related(Prefetch('item_set', queryset=Item.objects.all())) \

    def get_worksheet_title(self, index=0):
        return ugettext('Invoices')

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
        invoicing_formatter = getattr(settings, 'INVOICING_FORMATTER', 'invoicing.formatters.html.BootstrapHTMLFormatter')
        formatter_class = import_name(invoicing_formatter)
        print_api_url = getattr(settings, 'HTML_TO_PDF_API', None)
        requests = []
        export_files = []

        invoices = self.get_queryset()

        for invoice in invoices:
            formatter = formatter_class(invoice)
            invoice_content = formatter.get_response().content

            hex_4_bytes = binascii.hexlify(invoice_content)[0:8]

            # Look at the first 4 bytes of the file.
            # PDF has "%PDF" (hex 25 50 44 46) and ZIP has hex 50 4B 03 04.
            is_pdf = hex_4_bytes == b'25504446'

            if is_pdf:
                export_files.append({'name': str(invoice) + '.pdf', 'content': invoice_content})
            else:
                if print_api_url is None:
                    raise NotImplementedError('Invoice content is not PDF and HTML_TO_PDF_API is not set.')
                else:
                    requests.append({'invoice': str(invoice), 'html_content': invoice_content})

        if len(requests) > 0:
            session = sessions.FuturesSession(max_workers=3)
            futures = [{'invoice': request.get('invoice'), 'future': session.post(print_api_url, data=request.get('html_content'))} for request in requests]

            for f in futures:
                file_name = f.get('invoice')
                result = f.get('future').result()
                export_files.append({'name': file_name + '.pdf', 'content': result.content})

        if len(export_files) == 1:
            # directly export 1 PDF file
            file_data = export_files[0]
            self.filename = file_data['name']
            output.write(file_data['content'])
        else:
            # compress all invoices into single archive file
            output.write(compress(export_files).read())
