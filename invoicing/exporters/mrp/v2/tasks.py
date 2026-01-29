import logging

import requests
from django.core.mail import EmailMultiAlternatives
from django.core.validators import EMPTY_VALUES

from django.utils.translation import gettext_lazy as _
from lxml import etree
from outputs.models import Export, ExportItem
from outputs.signals import export_item_changed
from pragmatic.utils import get_task_decorator

from invoicing import settings as invoicing_settings
from invoicing.exporters.mrp.v2.list import InvoiceMrpExporterMixin
from invoicing.managers import MRPManager

from invoicing.utils import setup_export_context

logger = logging.getLogger(__name__)

task = get_task_decorator("exports")


@task
def send_invoices_to_mrp(creator_id, invoices_ids):
    if invoices_ids in EMPTY_VALUES:
        return

    creator, recipients, invoice_qs = setup_export_context(creator_id, [creator_id], invoices_ids)

    logger.info(f"Sending {invoice_qs.count()} invoices to MRP server (one invoice per request)")

    results = []
    exporter = _create_exporter(invoice_qs, creator)
    exporter.export()
    export = exporter.save_export()

    # MRP autonomous mode handles only one invoice per request
    # Process each invoice separately and collect results
    for output in exporter.get_outputs_per_item():
        result = _send_request_per_invoice_item(output['invoice'], output['xml_string'], export)
        results.append(result)

    # update status of export
    export.status = Export.STATUS_FINISHED
    export.save(update_fields=['status'])

    # Send email summary to user
    _send_mail_with_summary(creator, results)


def _send_request_per_invoice_item(invoice, xml_string, export):
    """
    Send a single invoice to MRP server.

    Args:
        invoice: Invoice instance being sent to MRP server
        xml_string: XML string (bytes) for single invoice, wrapped in MRP envelope
        export: Export instance to track the export status

    Returns:
        dict: Result with invoice_number, request_id, status, and optional error
    """
    root = etree.fromstring(xml_string)
    request_id = root.find(".//request").get("requestId")
    export_result = None
    export_detail = ''

    try:
        headers = {
            'Content-Type': f'application/xml; charset={InvoiceMrpExporterMixin.xml_encoding}'
        }
        url = invoicing_settings.INVOICING_MANAGERS.get('MRP')['API_URL']

        logger.debug(f"Sending invoice {invoice.number} to MRP server: {url}")
        response = requests.post(
            url,
            data=xml_string,
            headers=headers,
            timeout=InvoiceMrpExporterMixin.request_timeout
        )
        response.raise_for_status()
        logger.info(f"Received response for invoice {invoice.number}: {response.status_code}")

        # Parse and check response
        response_xml = _parse_response_xml(response)
        error_info = _extract_xml_errors(response_xml, request_id)
        if error_info:
            logger.error(f"Invoice {invoice.number} failed: Request ID: {request_id} - {error_info['error']}")
            export_result, export_detail, result = _handle_error(
                invoice.number,
                request_id,
                error_info['error'],
                error_info.get('error_code'),
                error_info.get('error_class')
            )
        else:
            # Success
            logger.info(f"Successfully sent invoice {invoice.number} to MRP server (request_id: {request_id})")
            export_result = ExportItem.RESULT_SUCCESS
            export_detail = f'request_id: {request_id}, invoice_number: {invoice.number}'
            result = {
                'invoice_number': invoice.number,
                'request_id': str(request_id),
                'status': 'success'
            }

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout when sending invoice {invoice.number}: {e}")
        timeout_msg = f'Request timeout: The MRP server did not respond within {InvoiceMrpExporterMixin.request_timeout} seconds'
        export_result, export_detail, result = _handle_error(invoice.number, request_id, timeout_msg)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when sending invoice {invoice.number}: {e}")
        export_result, export_detail, result = _handle_error(invoice.number, request_id, f'Network error: {str(e)}')
    except Exception as e:
        logger.exception(f"Unexpected error when sending invoice {invoice.number}: {e}")
        export_result, export_detail, result = _handle_error(invoice.number, request_id, f'Unexpected error: {str(e)}')
    finally:
        # Send signal once at the end
        export_item_changed.send(
            sender=MRPManager,
            export_id=export.id,
            object_id=invoice.id,
            result=export_result,
            detail=export_detail,
        )

    return result


def _create_exporter(invoice_qs, user):
    """Create and configure the appropriate MRP exporter."""
    from invoicing.models import Invoice
    from invoicing.exporters.mrp.v2.list import IssuedInvoiceMrpExporter, ReceivedInvoiceMrpExporter

    invoice_origin = invoice_qs.first().origin
    exporter_class = IssuedInvoiceMrpExporter if invoice_origin == Invoice.ORIGIN.ISSUED else ReceivedInvoiceMrpExporter

    exporter = exporter_class(
        user=user,
        recipients=[user],
        output_type=Export.OUTPUT_TYPE_STREAM
    )
    exporter.export_per_item = True
    exporter.queryset = invoice_qs
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
            lines.append(f"• {invoice_number} - {error_clean}")

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


def _error_result(invoice_number, request_id, error_message, error_code=None, error_class=None):
    """Helper method to create error result dictionary."""
    result = {
        'invoice_number': str(invoice_number),
        'request_id': request_id,
        'status': 'error',
        'error': str(error_message)
    }
    if error_code is not None:
        result['error_code'] = str(error_code)
    if error_class is not None:
        result['error_class'] = str(error_class)
    return result


def _handle_error(invoice_number, request_id, error_message, error_code=None, error_class=None):
    """
    Helper function to set up error state consistently.
    
    Returns:
        tuple: (export_result, export_detail, result_dict)
    """
    export_result = ExportItem.RESULT_FAILURE
    export_detail = str(error_message)
    result = _error_result(invoice_number, request_id, error_message, error_code, error_class)
    return export_result, export_detail, result


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
