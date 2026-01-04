import json
import logging
from datetime import datetime

import requests
from django.http import JsonResponse
from django.utils import translation
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe
from django_filters.constants import EMPTY_VALUES

from django.utils.translation import gettext_lazy as _
from lxml import etree

from invoicing import settings as invoicing_settings
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


def get_accounting_software_manager():
    if invoicing_settings.ACCOUNTING_SOFTWARE_MANAGER is not None:
        return import_string(invoicing_settings.ACCOUNTING_SOFTWARE_MANAGER)()

    if invoicing_settings.ACCOUNTING_SOFTWARE not in EMPTY_VALUES:
        # TODO: use title()
        if invoicing_settings.ACCOUNTING_SOFTWARE == 'IKROS':
            return IKrosManager()

        if invoicing_settings.ACCOUNTING_SOFTWARE == 'PROFIT365':
            return Profit365Manager()

        if invoicing_settings.ACCOUNTING_SOFTWARE == 'MRP':
            return MRPManager()

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

class MRPManager(AccountingSoftwareManager):
    # Constants
    COMMAND_INCOMING = "IMPFP0"
    COMMAND_OUTGOING = "IMPFV0"
    XML_ENCODING = 'Windows-1250'
    REQUEST_TIMEOUT = 30

    def __init__(self):
        if invoicing_settings.ACCOUNTING_SOFTWARE_MRP_API_URL in EMPTY_VALUES:
            raise EnvironmentError(_('Missing MRP API url'))

    
    def send_to_accounting_software(self, request: object, queryset: object) -> JsonResponse:
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
            return JsonResponse({
                'success': False,
                'error': 'No invoices selected for export'
            }, status=400)
        
        try:
            user = request.user
            logger.info(f"Sending {queryset.count()} invoices to MRP server (one invoice per request)")
            
            # MRP autonomous mode handles only one invoice per request
            # Process each invoice separately and collect results
            results = []
            for invoice in queryset:
                result = self._send_single_invoice(invoice, user)
                results.append(result)
            
            # Return summary of all processed invoices
            return JsonResponse({
                'success': True,
                'message': f'Processed {len(results)} invoice(s)',
                'results': results,
                'total_count': len(results),
                'success_count': sum(1 for r in results if r['status'] == 'success'),
                'error_count': sum(1 for r in results if r['status'] == 'error')
            })

        except Exception as e:
            logger.exception(f"Unexpected error in send_to_accounting_software: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }, status=500)

    def _send_single_invoice(self, invoice, user):
        """
        Send a single invoice to MRP server.
        
        Args:
            invoice: Single Invoice object
            user: request user
            
        Returns:
            dict: Result with invoice_number, request_id, status, and optional error
        """
        # Create queryset with single invoice
        single_queryset = Invoice.objects.filter(pk=invoice.pk)
        request_id = None
        
        try:
            # Create envelope for this single invoice
            xml_string, request_id = self._create_mrp_envelope(single_queryset, user)
            logger.debug(f"Created MRP envelope for invoice {invoice.number} with request_id: {request_id}")

            headers = {
                'Content-Type': f'application/xml; charset={self.XML_ENCODING}'
            }
            url = invoicing_settings.ACCOUNTING_SOFTWARE_MRP_API_URL

            logger.debug(f"Sending invoice {invoice.number} to MRP server: {url}")
            response = requests.post(
                url,
                data=xml_string,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            logger.info(f"Received response for invoice {invoice.number}: {response.status_code}")

            # Parse and check response
            response_xml = self._parse_response_xml(response)
            error_info = self._extract_xml_errors(response_xml, request_id)
            if error_info:
                logger.error(f"Invoice {invoice.number} failed: {error_info['error']}")
                return self._error_result(
                    invoice,
                    request_id,
                    error_info['error'],
                    error_info.get('error_code'),
                    error_info.get('error_class')
                )
            
            # Success
            logger.info(f"Successfully sent invoice {invoice.number} to MRP server (request_id: {request_id})")
            return {
                'invoice_number': invoice.number,
                'request_id': request_id,
                'status': 'success',
                'status_code': response.status_code
            }
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout when sending invoice {invoice.number}: {e}")
            return self._error_result(
                invoice,
                request_id,
                f'Request timeout: The MRP server did not respond within {self.REQUEST_TIMEOUT} seconds'
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error when sending invoice {invoice.number}: {e}")
            return self._error_result(invoice, request_id, f'Network error: {str(e)}')
        except Exception as e:
            logger.exception(f"Unexpected error when sending invoice {invoice.number}: {e}")
            return self._error_result(invoice, request_id, f'Unexpected error: {str(e)}')


    def _create_mrp_envelope(self, queryset, user):
        """
        Create mrpEnvelope XML structure with MRP data.

        Final structure:
        <mrpEnvelope>
          <body>
            <mrpRequest>
              <request command="IMPFV0" requestId="...">
              </request>
              <data>
                <MRPKSData version="2.0">...</MRPKSData>
              </data>
            </mrpRequest>
          </body>
        </mrpEnvelope>
        
        Args:
            queryset: QuerySet of Invoice objects (must contain exactly one invoice)
            user: request user
            
        Returns:
            tuple: (xml_string, request_id)
            
        Raises:
            ValueError: If queryset is empty
        """
        first_invoice = queryset.first()
        invoice_origin = first_invoice.origin
        
        envelope = etree.Element("mrpEnvelope")
        body = etree.SubElement(envelope, "body")

        mrp_request = etree.SubElement(body, "mrpRequest")
        request_id = f"import-{int(datetime.now().timestamp())}"
        command = self.COMMAND_INCOMING if invoice_origin == Invoice.ORIGIN.INCOMING else self.COMMAND_OUTGOING
        request_elem = etree.SubElement(
            mrp_request,
            "request",
            command=command,
            requestId=request_id,
        )

        # Create exporter and generate MRP data
        exporter = self._create_exporter(queryset, invoice_origin, user)
        mrp_data = exporter.get_mrp_data_element()

        # data is a sibling of request, both inside mrpRequest
        data_elem = etree.SubElement(mrp_request, "data")
        data_elem.append(mrp_data)

        xml_string = etree.tostring(
            envelope, pretty_print=True, xml_declaration=True, encoding=self.XML_ENCODING
        )
        return xml_string, request_id

    def _create_exporter(self, invoices, invoice_origin, user):
        """Create and configure the appropriate MRP exporter."""
        from invoicing.exporters.mrp.v2.list import OutgoingInvoiceMrpExporter, IncomingInvoiceMrpExporter
        exporter_class = OutgoingInvoiceMrpExporter if invoice_origin == Invoice.ORIGIN.OUTGOING else IncomingInvoiceMrpExporter

        exporter = exporter_class(
            user=user,
            recipients=[user]
        )
        exporter.queryset = invoices
        return exporter

    def _error_result(self, invoice, request_id, error_message, error_code=None, error_class=None):
        """Helper method to create error result dictionary."""
        result = {
            'invoice_number': invoice.number,
            'request_id': request_id,
            'status': 'error',
            'error': error_message
        }
        if error_code is not None:
            result['error_code'] = error_code
        if error_class is not None:
            result['error_class'] = error_class
        return result

    def _extract_xml_errors(self, response_xml, request_id):
        """
        Extract error information from XML response.
        
        Args:
            response_xml: Parsed XML response or None
            request_id: Request ID for logging
            
        Returns:
            dict: Error info with 'error', 'error_code', 'error_class' keys, or None if no error
        """
        if response_xml is None:
            return None
        
        error_elem = response_xml.find('.//error')
        if error_elem is None:
            return None
        
        error_code = error_elem.get('errorCode', '')
        error_class = error_elem.get('errorClass', '')
        error_message_elem = error_elem.find('errorMessage')
        error_message = error_message_elem.text if error_message_elem is not None else 'Unknown error'
        
        logger.error(f"MRP server returned error (request_id: {request_id}): {error_message}")
        return {
            'error': error_message,
            'error_code': error_code,
            'error_class': error_class
        }

    def _parse_response_xml(self, response):
        """Parse XML from response if available, return None otherwise."""
        try:
            if response.headers.get('Content-Type', '').startswith('application/xml') or \
                    response.content.strip().startswith(b'<'):
                return etree.fromstring(response.content)
        except (etree.XMLSyntaxError, etree.ParseError, ValueError) as e:
            logger.warning(f"Failed to parse response XML: {e}")
        return None

def get_invoice_details_manager():
    if invoicing_settings.INVOICE_DETAILS_MANAGER is not None:
        return import_string(invoicing_settings.INVOICE_DETAILS_MANAGER)()

    return import_string('invoicing.managers.InvoiceDetailsManager')()


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
