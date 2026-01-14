import logging

import requests
from datetime import datetime
from django.core.mail import EmailMultiAlternatives
from django_filters.constants import EMPTY_VALUES

from django.utils.translation import gettext_lazy as _
from lxml import etree

from invoicing import settings as invoicing_settings
from invoicing.exporters.tasks import setup_export_context
from invoicing.managers import MRPManager
from invoicing.signals import invoices_exported
from invoicing.utils import generate_export_id, get_task_decorator

logger = logging.getLogger(__name__)

COMMAND_INCOMING = "IMPFP0"
COMMAND_OUTGOING = "IMPFV0"
XML_ENCODING = 'Windows-1250'
REQUEST_TIMEOUT = 30
task = get_task_decorator("invoicing")

@task
def send_invoices_to_mrp(creator_id, invoices_ids, export_prefix):
    if invoices_ids in EMPTY_VALUES:
        return

    creator, recipients, invoice_qs, export_id = setup_export_context(creator_id, None, invoices_ids, export_prefix)

    logger.info(f"Sending {invoice_qs.count()} invoices to MRP server (one invoice per request)")

    # MRP autonomous mode handles only one invoice per request
    # Process each invoice separately and collect results
    results = []
    for invoice in invoice_qs:
        result = _send_single_invoice(invoice, creator, export_id)
        results.append(result)

    # Send email summary to user
    _send_mail_with_summary(creator, results)

def _send_single_invoice(invoice, user, export_id):
    """
    Send a single invoice to MRP server.

    Args:
        invoice: Single Invoice object
        user: request user

    Returns:
        dict: Result with invoice_number, request_id, status, and optional error
    """
    from invoicing.models import Invoice, InvoiceExport

    # Create queryset with single invoice
    single_queryset = Invoice.objects.filter(pk=invoice.pk)
    request_id = None
    export_result = None
    export_detail = ''

    try:
        # Create envelope for this single invoice
        xml_string, request_id = _create_mrp_envelope(single_queryset, user)
        logger.debug(f"Created MRP envelope for invoice {invoice.number} with request_id: {request_id}")

        headers = {
            'Content-Type': f'application/xml; charset={XML_ENCODING}'
        }
        url = invoicing_settings.INVOICING_MANAGERS.get('MRP')['API_URL']

        logger.debug(f"Sending invoice {invoice.number} to MRP server: {url}")
        response = requests.post(
            url,
            data=xml_string,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Received response for invoice {invoice.number}: {response.status_code}")

        # Parse and check response
        response_xml = _parse_response_xml(response)
        error_info = _extract_xml_errors(response_xml, request_id)
        if error_info:
            logger.error(f"Invoice {invoice.number} failed: {error_info['error']}")
            export_result = InvoiceExport.RESULT.FAIL
            export_detail = error_info['error']
            result = _error_result(
                invoice,
                request_id,
                error_info['error'],
                error_info.get('error_code'),
                error_info.get('error_class')
            )
        else:
            # Success
            logger.info(f"Successfully sent invoice {invoice.number} to MRP server (request_id: {request_id})")
            export_result = InvoiceExport.RESULT.SUCCESS
            export_detail = f'request_id: {request_id}'
            result = {
                'invoice_number': invoice.number,
                'request_id': str(request_id),
                'status': 'success'
            }

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout when sending invoice {invoice.number}: {e}")
        export_result = InvoiceExport.RESULT.FAIL
        export_detail = f'Request timeout: {REQUEST_TIMEOUT}s'
        result = _error_result(
            invoice,
            request_id,
            f'Request timeout: The MRP server did not respond within {REQUEST_TIMEOUT} seconds'
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when sending invoice {invoice.number}: {e}")
        export_result = InvoiceExport.RESULT.FAIL
        export_detail = f'Network error: {str(e)}'
        result = _error_result(invoice, request_id, f'Network error: {str(e)}')
    except Exception as e:
        logger.exception(f"Unexpected error when sending invoice {invoice.number}: {e}")
        export_result = InvoiceExport.RESULT.FAIL
        export_detail = f'Unexpected error: {str(e)}'
        result = _error_result(invoice, request_id, f'Unexpected error: {str(e)}')
    finally:
        # Send signal once at the end
        if export_result is not None:
            invoices_exported.send(
                sender=MRPManager,
                invoices=[invoice],
                method='export_via_api',
                export_id=export_id,
                result=export_result,
                detail=export_detail,
                creator=user
            )

    return result


def _create_mrp_envelope(queryset, user):
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
    from invoicing.models import Invoice

    first_invoice = queryset.first()
    invoice_origin = first_invoice.origin

    envelope = etree.Element("mrpEnvelope")
    body = etree.SubElement(envelope, "body")

    mrp_request = etree.SubElement(body, "mrpRequest")
    request_id = f"import-{int(datetime.now().timestamp())}"
    command = COMMAND_INCOMING if invoice_origin == Invoice.ORIGIN.INCOMING else COMMAND_OUTGOING
    request_elem = etree.SubElement(
        mrp_request,
        "request",
        command=command,
        requestId=request_id,
    )

    # Create exporter and generate MRP data
    exporter = _create_exporter(queryset, invoice_origin, user)
    mrp_data = exporter.get_mrp_data_element()

    # data is a sibling of request, both inside mrpRequest
    data_elem = etree.SubElement(mrp_request, "data")
    data_elem.append(mrp_data)

    xml_string = etree.tostring(
        envelope, pretty_print=True, xml_declaration=True, encoding=XML_ENCODING
    )
    return xml_string, request_id


def _create_exporter(invoices, invoice_origin, user):
    """Create and configure the appropriate MRP exporter."""
    from invoicing.models import Invoice
    from invoicing.exporters.mrp.v2.list import OutgoingInvoiceMrpExporter, IncomingInvoiceMrpExporter
    exporter_class = OutgoingInvoiceMrpExporter if invoice_origin == Invoice.ORIGIN.OUTGOING else IncomingInvoiceMrpExporter

    exporter = exporter_class(
        user=user,
        recipients=[user]
    )
    exporter.queryset = invoices
    return exporter


def _send_mail_with_summary(user, results):
    """
    Send email summary of MRP export results to the user.

    Args:
        user: User object to send email to
        results: List of result dictionaries from invoice processing
    """
    lines = [
        str(_('MRP export of invoices')),
        "",
        f"{_('Total invoices processed')}: {len(results)}",
        f"{_('Successful')}: {sum(1 for r in results if r['status'] == 'success')}",
        f"{_('Errors')}: {sum(1 for r in results if r['status'] == 'error')}",
        "",
        str(_('Error details:')),
    ]

    for r in results:
        invoice_number = r.get('invoice_number')
        status = r.get('status')
        error = r.get('error')

        if status == 'error':
            error_clean = ' '.join(str(error).strip().split())
            lines.append(f"  • {invoice_number} - {error_clean}")

    email_body = "\n".join(lines)

    # Send email to user if email is available
    creator_email = getattr(user, "email", None)
    if creator_email:
        subject = _('MRP export of invoices')
        message = EmailMultiAlternatives(
            subject=subject,
            body=email_body,
            to=[creator_email],
        )
        message.send(fail_silently=False)


def _error_result(invoice, request_id, error_message, error_code=None, error_class=None):
    """Helper method to create error result dictionary."""
    result = {
        'invoice_number': str(invoice.number),
        'request_id': request_id,
        'status': 'error',
        'error': str(error_message)
    }
    if error_code is not None:
        result['error_code'] = str(error_code)
    if error_class is not None:
        result['error_class'] = str(error_class)
    return result


def _extract_xml_errors(response_xml, request_id):
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


def _parse_response_xml(response):
    """Parse XML from response if available, return None otherwise."""
    try:
        if response.headers.get('Content-Type', '').startswith('application/xml') or \
                response.content.strip().startswith(b'<'):
            logger.info(f"Received xml response: {response.content}")
            return etree.fromstring(response.content)
    except (etree.XMLSyntaxError, etree.ParseError, ValueError) as e:
        logger.warning(f"Failed to parse response XML: {e}")
    return None
