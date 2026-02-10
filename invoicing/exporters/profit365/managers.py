import json
import logging

import requests
from django.contrib import messages
from django.core.validators import EMPTY_VALUES
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


class Profit365Manager(InvoiceManagerMixin):
    def export_via_api(self, request, queryset):
        if self.manager_settings.get('API_URL', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API url'), self.__class__.__name__)

        if self.manager_settings.get('API_DATA', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API data'), self.__class__.__name__)

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

                invoice_data = {
                    "recordNumber": invoice.number,
                    "bankAccountId": self.manager_settings['API_DATA']['bankAccountId'],
                    "partnerAddress": '\r\n'.join(partnerAddress),
                    "phone": invoice.customer_phone,
                    "email": invoice.customer_email,
                    "dateCreated": invoice.date_issue.strftime('%Y-%m-%dT00:00:00'),
                    "dateAccounting": invoice.date_tax_point.strftime('%Y-%m-%dT00:00:00'),
                    "dateValidTo": invoice.date_due.strftime('%Y-%m-%dT00:00:00'),
                    "symbolSpecific": invoice.specific_symbol,
                    "symbolVariable": invoice.variable_symbol,
                    "symbolConstant": invoice.constant_symbol,
                    "localCurrencyID": invoice.currency,
                    "currencyID": invoice.currency,
                    "issuedBy": invoice.issuer_name,
                    "rows": []
                }

                if invoice.status == Invoice.STATUS.CANCELED:
                    invoice_data['description'] = 'STORNO'
                    invoice_data['commentBelowItems'] = 'STORNO 2'
                else:
                    for item in invoice.item_set.all():
                        item_data = {
                            "name": item.title,
                            "price": str(item.unit_price),
                            "quantity": str(item.quantity)
                        }

                        if item.discount > 0:
                            item_data['discountPercent'] = str(item.discount)

                        invoice_data['rows'].append(item_data)

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
