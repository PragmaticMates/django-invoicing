import json

import requests
from django.utils import translation
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe
from django_filters.constants import EMPTY_VALUES
from django.utils.translation import ugettext_lazy as _
from invoicing import settings as invoicing_settings
from invoicing.models import Invoice


def get_accounting_software_manager():
    if invoicing_settings.ACCOUNTING_SOFTWARE_MANAGER is not None:
        return import_string(invoicing_settings.ACCOUNTING_SOFTWARE_MANAGER)()

    if invoicing_settings.ACCOUNTING_SOFTWARE not in EMPTY_VALUES:
        # TODO: use title()
        if invoicing_settings.ACCOUNTING_SOFTWARE == 'IKROS':
            return IKrosManager()

        if invoicing_settings.ACCOUNTING_SOFTWARE == 'PROFIT365':
            return Profit365Manager()

        return NotImplementedError(_('Accounting software %s not implemented') % invoicing_settings.ACCOUNTING_SOFTWARE)

    return None


class AccountingSoftwareManager(object):
    def send_to_accounting_software(self, request, queryset):
        raise NotImplementedError()


class IKrosManager(AccountingSoftwareManager):
    def __init__(self):
        if invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA in EMPTY_VALUES:
            raise EnvironmentError(_('Missing accounting software API key'))

    def send_to_accounting_software(self, request, queryset):
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

        # pprint(invoices_data)  # TODO: logging
        payload = json.dumps(invoices_data)

        url = invoicing_settings.ACCOUNTING_SOFTWARE_IKROS_API_URL
        api_key = invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA['apiKey']
        headers = {
            'Authorization': 'Bearer ' + str(api_key),
            'Content-Type': 'application/json'
        }
        r = requests.post(url=url, data=payload, headers=headers)
        data = r.json()

        # pprint(data)  # TODO: logging

        if data.get('message', None) is not None:
            raise Exception(_('Result code: %d. Message: %s (%s)') % (
                data.get('code', data.get('resultCode')),
                data['message'],
                data.get('errorType', '-')
            ))

        if 'documents' in data:
            if len(data['documents']) > 0:
                download_url = data['documents'][0]['downloadUrl']
                # requests.get(download_url)

                return mark_safe(_('%d invoices sent to accounting software [<a href="%s" target="_blank">Fetch</a>]') % (
                    queryset.count(),
                    download_url
                ))
            else:
                return _('%d invoices sent to accounting software') % (
                    queryset.count(),
                )


class Profit365Manager(AccountingSoftwareManager):
    def __init__(self):
        if invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA in EMPTY_VALUES:
            raise EnvironmentError(_('Missing accounting software API data'))

    def send_to_accounting_software(self, request, queryset):
        results = []

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
                    "bankAccountId": invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA['bankAccountId'],
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

            # pprint(invoice_data)  # TODO: logging
            payload = json.dumps(invoice_data)

            url = invoicing_settings.ACCOUNTING_SOFTWARE_PROFIT365_API_URL
            headers = {
                'Authorization': invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA['Authorization'],
                'ClientID': invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA['ClientID'],
                'ClientSecret': invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA['ClientSecret'],
                'Content-Type': 'application/json'
            }
            if 'CompanyID' in invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA:
                headers['CompanyID'] = invoicing_settings.ACCOUNTING_SOFTWARE_API_DATA

            r = requests.post(url=f'{url}/sales/invoices', data=payload, headers=headers)

            # if r.status_code == 200:
            #     data = r.json()
                # pprint(data)

            results.append({
                'invoice': invoice.number,
                'status_code': r.status_code,
                'reason': r.reason
            })

        return results
