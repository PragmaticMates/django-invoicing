import json
import logging

import requests
from django.contrib import messages
from django.core.validators import EMPTY_VALUES
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


class IKrosManager(InvoiceManagerMixin):
    def export_via_api(self, request, queryset):
        if self.manager_settings.get('API_URL', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API url'), self.__class__.__name__)

        if self.manager_settings.get('API_KEY', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API key'), self.__class__.__name__)

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
                "currency": invoice.currency,
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
                    item_data['count'] = 0
                    item_data['unitPrice'] = 0

                invoice_data['items'].append(item_data)

            if invoice.status == Invoice.STATUS.CANCELED:
                invoice_data['closingText'] = 'STORNO'

            if invoice.credit != 0:
                invoice_data['items'][0]['hasDiscount'] = True
                invoice_data['items'][0]['discountValue'] = str(invoice.credit * -1)

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
                if len(data['documents']) > 0:
                    download_url = data['documents'][0]['downloadUrl']
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
            messages.error(request, str(e))
            return str(e)

    export_via_api.short_description = _('Export to IKROS (API)')
