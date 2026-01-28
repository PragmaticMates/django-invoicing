import json
import logging

import requests
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.utils import translation
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe
from django_filters.constants import EMPTY_VALUES

from django.utils.translation import gettext_lazy as _

from invoicing import settings as invoicing_settings
from invoicing.exporters import InvoiceISDOCXmlListExporter, InvoiceXlsxListExporter, InvoicePdfDetailExporter
from invoicing.exporters.mrp.v1.list import InvoiceXmlMrpListExporter
from invoicing.exporters.mrp.v2.list import ReceivedInvoiceMrpExporter, IssuedInvoiceMrpExporter
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


def get_invoice_details_manager():
    invoice_details_manager_class = invoicing_settings.INVOICING_MANAGERS['DETAILS'].get('MANAGER_CLASS', None)
    if invoice_details_manager_class is not None:
        return import_string(invoice_details_manager_class)()

    raise EnvironmentError(_('Missing MANAGER_CLASS for invoice details manager'))


class InvoiceExportMixin(object):

    def _is_export_qs_valid(self, request, exporter):
        """
        Validate queryset to be exported.

        - Ensures there is something to export.
        - Ensures that all exported objects share a single origin.
        """
        queryset = exporter.get_queryset()

        # 1) Check if there is anything to export
        if not queryset.exists():
            messages.warning(request, _("%s: There is no invoice selected to export." % exporter.__class__))
            return False

        # 2) Check if origin is unique across the queryset
        #    (assumes an 'origin' field on the model)
        origins_qs = queryset.values_list("origin", flat=True).distinct()
        if origins_qs.count() != 1:
            messages.warning(request, _("%s: All exported invoices must have the same origin." % exporter.__class__))
            return False

        return True


    def _execute_export(self, request, exporter_class, exporter_params, queryset):
        """
        Common export logic for email-based exports.

        Args:
            request: The HTTP request object
            exporter_class: The exporter class to use
            exporter_params: The params of the exporter
            queryset: The queryset of invoices to export
        """

        logger.info(
            f"User {request.user} (ID: {request.user.id}) executing export with {queryset.count()} invoice(s)",
            extra={
                'user_id': request.user.id,
                'exporter_class': exporter_class,
                'exporter_params': exporter_params
            }
        )

        if exporter_params is None:
            exporter_params = {"user": request.user, "recipients": [request.user], "params": None}

        exporter = exporter_class(**exporter_params)

        # set queryset if provided explicitly
        if queryset is not None and queryset.exists():
            exporter.queryset = queryset

        if not self._is_export_qs_valid(request, exporter):
            return

        from outputs.usecases import execute_export
        execute_export(exporter, language=translation.get_language())
        messages.success(request, _('Export of %d invoice(s) queued and will be sent to email') % queryset.count())

class InvoiceExportApiMixin(object):
    manager_name = ""

    def __init__(self):
        if self.manager_settings.get('API_URL', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API url'), self.manager_name)

    def export_via_api(self, request, queryset):
        raise NotImplementedError()

    @property
    def manager_settings(self):
        """Get the settings for this manager from INVOICING_MANAGERS config."""
        return invoicing_settings.INVOICING_MANAGERS.get(self.manager_name, None)


class PdfExportManager(InvoiceExportMixin):
    manager_name = 'PDF'
    exporter_class = InvoicePdfDetailExporter

    def export_detail_pdf(self, request, queryset=None, exporter_params=None):
        self._execute_export(request,  self.__class__.exporter_class, exporter_params, queryset)

    export_detail_pdf.short_description = _('Export to PDF')


class XlsxExportManager(InvoiceExportMixin):
    manager_name = 'XLSX'
    exporter_class = InvoiceXlsxListExporter

    def export_list_xlsx(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.__class__.exporter_class, exporter_params, queryset)

    export_list_xlsx.short_description = _('Export to xlsx')


class ISDOCManager(InvoiceExportMixin):
    manager_name = 'ISDOC'
    exporter_class = InvoiceISDOCXmlListExporter

    def export_list_isdoc(self, request, queryset=None, exporter_params=None):
        self._execute_export(request,  self.__class__.exporter_class, exporter_params, queryset)

    export_list_isdoc.short_description = _('Export to ISDOC (XML)')


class IKrosManager(InvoiceExportApiMixin):
    manager_name = 'IKROS'

    def __init__(self):
        super().__init__()
        if self.manager_settings.get('API_KEY', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API key'), self.manager_name)

    def export_via_api(self, request, queryset):
        invoices_data = []

        for invoice in queryset:
            invoice_data = {
                "documentNumber": invoice.number,
                "createDate": invoice.date_issue.strftime('%Y-%m-%dT00:00:00'),
                "dueDate": invoice.date_due.strftime('%Y-%m-%dT00:00:00'),
                "completionDate": invoice.date_tax_point.strftime('%Y-%m-%dT00:00:00'),
                "clientName": invoice.customer_name,
                "clientStreet": invoice.customer_street,
                "clientPostCode": invoice.customer_zip,
                "clientTown": invoice.customer_city,
                "clientCountry": invoice.get_customer_country_display(),
                "clientRegistrationId": invoice.customer_registration_id,
                "clientTaxId": invoice.customer_tax_id,
                "clientVatId": invoice.customer_vat_id,
                "clientPhone": invoice.customer_phone,
                "clientEmail": invoice.customer_email,
                "variableSymbol": invoice.variable_symbol,
                "paymentType": invoice.get_payment_method_display(),
                "deliveryType": invoice.get_delivery_method_display(),
                "senderContactName": invoice.issuer_name,
                "clientPostalName": invoice.shipping_name,
                "clientPostalStreet": invoice.shipping_street,
                "clientPostalPostCode": invoice.shipping_zip,
                "clientPostalTown": invoice.shipping_city,
                "clientPostalCountry": invoice.get_shipping_country_display(),
                "clientInternalId": f'{invoice.customer_country}001',  # TODO: custom mapping
                # "clientHasDifferentPostalAddress": True,
                "currency": invoice.currency,
                # "orderNumber": invoice.variable_symbol,
                "items": []
            }

            for item in invoice.item_set.all():
                item_data = {
                    "name": item.title,
                    "count": str(item.quantity),
                    "measureType": item.get_unit_display(),
                    "unitPrice": str(item.unit_price),
                    "vat": item.vat
                }

                if invoice.status == Invoice.STATUS.CANCELED:
                    item_data['count'] = 0  # not working actually (min value = 1)
                    item_data['unitPrice'] = 0
                    # item_data['description'] = 'STORNO'

                invoice_data['items'].append(item_data)

            if invoice.status == Invoice.STATUS.CANCELED:
                invoice_data['closingText'] = 'STORNO'

            if invoice.credit != 0:
                invoice_data['items'][0]['hasDiscount'] = True
                invoice_data['items'][0]['discountValue'] = str(invoice.credit * -1)  # TODO: substract VAT
                # invoice_data['items'][0]['discountValueWithVat'] = str(invoice.credit * -1)

            invoices_data.append(invoice_data)

        logger.info("IKROS payload invoices data: %s", invoices_data)
        try:
            payload = json.dumps(invoices_data)

            url = self.manager_settings['API_URL']
            api_key = self.manager_settings['API_KEY']
            headers = {
                'Authorization': 'Bearer ' + str(api_key),
                'Content-Type': 'application/json'
            }
            r = requests.post(url=url, data=payload, headers=headers)
            data = r.json()

            logger.info("IKROS response data: %s", data)

            if data.get('message', None) is not None:
                error_msg = _('Result code: %d. Message: %s (%s)') % (
                    data.get('code', data.get('resultCode')),
                    data['message'],
                    data.get('errorType', '-')
                )
                messages.error(request, error_msg)
                raise Exception(error_msg)

            if 'documents' in data:
                # Batch export succeeded - trigger signal

                if len(data['documents']) > 0:
                    download_url = data['documents'][0]['downloadUrl']
                    # requests.get(download_url)

                    result = mark_safe(_('%d invoices sent to IKROS accounting software [<a href="%s" target="_blank">Fetch</a>]') % (
                        queryset.count(),
                        download_url
                    ))
                else:
                    result = _('%d invoices sent to IKROS accounting software') % (
                        queryset.count(),
                    )
                messages.success(request, result)
                return result

        except Exception as e:
            # Batch export failed - trigger signal with failure

            messages.error(request, str(e))
            return str(e)

    export_via_api.short_description = _('Export to IKROS (API)')


class Profit365Manager(InvoiceExportApiMixin):
    manager_name = 'PROFIT365'

    def __init__(self):
        super().__init__()
        if self.manager_settings.get('API_DATA', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API data'), self.manager_name)

    def export_via_api(self, request, queryset):
        from invoicing.models import Invoice

        results = []

        logger.info(f"Sending {queryset.count()} invoices to Profit365 server (one invoice per request)")
        for invoice in queryset:
            with translation.override(invoice.language):
                partnerAddress = [
                    invoice.customer_name,
                    invoice.customer_street,
                    invoice.customer_zip,
                    invoice.customer_city,
                    invoice.get_customer_country_display()
                ]

                if invoice.customer_registration_id:
                    partnerAddress += [
                        '%s: %s' % (_('Reg. No.'), invoice.customer_registration_id),
                    ]

                if invoice.customer_tax_id:
                    partnerAddress += [
                        '%s: %s' % (_('Tax No.'), invoice.customer_tax_id),
                    ]

                if invoice.customer_vat_id:
                    partnerAddress += [
                        '%s: %s' % (_('VAT No.'), invoice.customer_vat_id),
                    ]

                # "clientEmail": invoice.customer_email,  # partner email

                invoice_data = {
                    "recordNumber": invoice.number,
                    "bankAccountId": self.manager_settings['API_DATA']['bankAccountId'],
                    # "ordnerID": "VYF",  # TODO: setting
                    # "warehouseID": "TODO", # TODO: setting
                    # "partnerDetail": "Firma s.r.o.\r\nLesná 123\r\nBratislava\r\nIČO: test",
                    "partnerAddress": '\r\n'.join(partnerAddress),  # delivery address
                    # "partnerId": "TODO",  # TODO: find partner by externalId
                    "phone": invoice.customer_phone,
                    "email": invoice.customer_email,
                    "dateCreated": invoice.date_issue.strftime('%Y-%m-%dT00:00:00'),
                    "dateAccounting": invoice.date_tax_point.strftime('%Y-%m-%dT00:00:00'),
                    # "dateDelivery": "2020-07-20",
                    "dateValidTo": invoice.date_due.strftime('%Y-%m-%dT00:00:00'),  # due date
                    # "orderRecordNo": invoice.variable_symbol,  # TODO: order number
                    "symbolSpecific": invoice.specific_symbol,
                    "symbolVariable": invoice.variable_symbol,
                    "symbolConstant": invoice.constant_symbol,
                    "localCurrencyID": invoice.currency,
                    "currencyID": invoice.currency,
                    "issuedBy": invoice.issuer_name,
                    # "bonusPercent": invoice.credit, # TODO: calculate
                    # "deliveryTypeId": postou  # TODO: invoice.delivery_method
                    # "paymentTypeId": prevod / kartou  # TODO: invoice.payment_method

                    # "paymentType": invoice.get_payment_method_display(),
                    # "deliveryType": invoice.get_delivery_method_display(),

                    # "clientPostalName": invoice.shipping_name,
                    # "clientPostalStreet": invoice.shipping_street,
                    # "clientPostalPostCode": invoice.shipping_zip,
                    # "clientPostalTown": invoice.shipping_city,
                    # "clientPostalCountry": invoice.get_shipping_country_display(),
                    # "clientInternalId": f'{invoice.customer_country}001',  # TODO: partner: external Id
                    # "clientHasDifferentPostalAddress": True,
                    "rows": []
                }

                if invoice.status == Invoice.STATUS.CANCELED:
                    invoice_data['description'] = 'STORNO'
                    invoice_data['commentBelowItems'] = 'STORNO 2'
                else:
                    for item in invoice.item_set.all():
                        item_data = {
                            # "itemId": "808497a7-c5cb-4d7e-a3d2-6c7e49735831",  # TODO: find by external Id
                            "name": item.title,
                            "price": str(item.unit_price),
                            "quantity": str(item.quantity)
                            # "measureType": item.get_unit_display(),
                            # "vat": item.vat
                        }

                        if item.discount > 0:
                            item_data['discountPercent'] = str(item.discount)

                        # if invoice.status == Invoice.STATUS.CANCELED:
                        #     item_data['quantity'] = 0  # not working actually (min value = 1)
                        #     item_data['price'] = 0
                        #     invoice_data['description'] = 'STORNO 1'
                        #     invoice_data['commentBelowItems'] = 'STORNO 2'

                        invoice_data['rows'].append(item_data)

                # if invoice.status == Invoice.STATUS.CANCELED:
                #     invoice_data['closingText'] = 'STORNO'

                # if invoice.credit != 0:
                #     invoice_data['items'][0]['hasDiscount'] = True
                #     invoice_data['items'][0]['discountValue'] = str(invoice.credit * -1)  # TODO: substract VAT
                    ## invoice_data['items'][0]['discountValueWithVat'] = str(invoice.credit * -1)

            payload = json.dumps(invoice_data)

            url = self.manager_settings['API_URL']
            headers = {
                'Authorization': self.manager_settings['API_DATA']['Authorization'],
                'ClientID': self.manager_settings['API_DATA']['ClientID'],
                'ClientSecret': self.manager_settings['API_DATA']['ClientSecret'],
                'Content-Type': 'application/json'
            }
            if 'CompanyID' in self.manager_settings['API_DATA']:
                headers['CompanyID'] = self.manager_settings['API_DATA']['CompanyID']

            logger.debug(f"Profit365: Created payload {payload} for invoice {invoice.number}")
            r = requests.post(url=f'{url}/sales/invoices', data=payload, headers=headers)

            if r.status_code == 200:
                logger.info(f"Received success response for invoice {invoice.number}: {r.status_code}")
            else:
                logger.error(f"Received error response for invoice {invoice.number}: {r.status_code} {r.reason}")

            results.append({
                'invoice': invoice.number,
                'status_code': r.status_code,
                'reason': r.reason
            })

        # Show messages for results
        success_count = 0
        for r in results:
            if r['status_code'] == 200:
                success_count += 1
            else:
                messages.error(request, f"[{r['invoice']}]: {r['status_code']} ({r['reason']})")

        if success_count > 0:
            messages.success(request, _('%d invoices sent to Profit365 accounting software') % success_count)

        return results

    export_via_api.short_description = _('Export to Profit365 (API)')

class MRPManager(InvoiceExportMixin, InvoiceExportApiMixin):
    manager_name = 'MRP'
    exporter_classes = {
        'v1': InvoiceXmlMrpListExporter,
        'v2': {
            Invoice.ORIGIN.RECEIVED: ReceivedInvoiceMrpExporter,
            Invoice.ORIGIN.ISSUED: IssuedInvoiceMrpExporter,
        }
    }

    def export_list_mrp_v2(self, request, queryset=None, exporter_params=None):
        if not queryset.exists():
            messages.info(request, _('%s: No invoice selected to export.' % 'export_mrp_v2'))
            return
        else:
            origin = queryset.first().origin
            exporter_class = self.__class__.exporter_classes.get('v2', {}).get(origin)
            if exporter_class is None:
                raise ImproperlyConfigured(
                    _("Unsupported invoice origin '%s' for MRP v2 export.") % origin
                )

        self._execute_export(request, exporter_class, exporter_params, queryset)

    export_list_mrp_v2.short_description = _('Export to MRP v2 (XML)')

    def export_list_mrp_v1(self, request, queryset=None, exporter_params=None):
        """Legacy MRP XML export (v1) - returns direct response instead of email."""

        if exporter_params is None:
            exporter_params = {"user": request.user, "recipients": [request.user], "params": None}

        exporter_class = self.__class__.exporter_classes['v1']
        if exporter_class is None:
            raise ImproperlyConfigured(_("Undefined exporter class for MRP v1 export."))
        
        exporter = exporter_class(**exporter_params)

        # set queryset if provided explicitly
        if queryset is not None and queryset.exists():
            exporter.queryset = queryset

        if not self._is_export_qs_valid(request, exporter):
            return

        creator_id = request.user.id
        recipients_ids = [creator_id]
        invoice_ids = list(exporter.get_queryset().values_list("id", flat=True))

        from invoicing.exporters.mrp.v1.tasks import mail_exported_invoices_mrp_v1
        mail_exported_invoices_mrp_v1.delay(
            creator_id, recipients_ids, invoice_ids, exporter_class.filename, request.GET
        )

        messages.success(request, _('Export of %d invoice(s) queued and will be sent to email') % exporter.get_queryset().count())

    export_list_mrp_v1.short_description = _('Export to MRP v1 (XML)')


    def export_via_api(self, request, queryset):
        """
        Handle POST request to send invoices to MRP server.
        
        Args:
            request: Django request object with user attribute
            queryset: QuerySet of Invoice objects to export

        Returns:
            JsonResponse with success status and response data
        """
        # Input validation
        if queryset is None or not queryset.exists():
            messages.error(request, _('No invoices selected for export'))
            return

        logger.info(
            f"User {request.user} (ID: {request.user.id}) queuing MRP API export for {queryset.count()} invoice(s)",
            extra={
                'user_id': request.user.id,
                'manager': 'MRPManager',
                'method': 'export_via_api',
                'invoice_count': queryset.count(),
            }
        )

        creator_id = request.user.id
        invoice_ids = list(queryset.values_list("id", flat=True))

        from invoicing.exporters.mrp.v2.tasks import send_invoices_to_mrp
        send_invoices_to_mrp.delay(creator_id, invoice_ids)

        messages.success(request, _('Export of %d invoice(s) queued for MRP API processing') % queryset.count())

    export_via_api.short_description = _('Export to MRP (API)')

class InvoiceDetailsManager(object):
    @staticmethod
    def vat_type(invoice):
        return ''

    # cislo zakaznika
    @staticmethod
    def customer_number(invoice):
        return ''

    # predkontacia
    @staticmethod
    def advance_notice(invoice):
        return ''

    # kod plnenia
    @staticmethod
    def fulfillment_code(invoice):
        return ''

    # stredisko
    @staticmethod
    def center(invoice):
        return ''
