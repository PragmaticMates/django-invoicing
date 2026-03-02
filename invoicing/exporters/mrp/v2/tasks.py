import logging

import requests
from django.core.mail import EmailMultiAlternatives

from django.utils.translation import gettext_lazy as _
from lxml import etree
from outputs.models import Export, ExportItem
from outputs.signals import export_item_changed
from pragmatic.utils import get_task_decorator

from invoicing import settings as invoicing_settings
from invoicing.exporters.mrp.v2.list import InvoiceMrpListExporterMixin

logger = logging.getLogger(__name__)

task = get_task_decorator("exports")


@task
def send_invoices_to_mrp(export_id, manager_class):
    export = Export.objects.get(id=export_id)

    export.status = Export.STATUS_PROCESSING
    export.save(update_fields=['status'])

    logger.info(f"Sending {export.total} invoices to MRP server (one invoice per request)")

    results = []
    fatal_error = None
    exporter = export.exporter

    if not exporter:
        logger.error(f"Sending to MRP failed, no exporter found.")
        export.status = Export.STATUS_FAILED
        export.save(update_fields=['status'])
        _send_mail_with_summary(export.creator, [], fatal_error=_('No exporter found for this export.'))
        return

    try:
        # important - set export_per_item, to split export items to multiple outputs
        exporter.export_per_item = True
        exporter.export()

        # update status of export
        export.status = Export.STATUS_PROCESSING
        export.save(update_fields=['status'])

        manager_class_path = f'{manager_class.__class__.__module__}.{manager_class.__class__.__name__}'
        api_url = invoicing_settings.INVOICING_MANAGERS.get(manager_class_path)['API_URL']

        # MRP autonomous mode handles only one invoice per request
        # Process each invoice separately and collect results
        for output in exporter.get_outputs_per_item():
            invoice = output['invoice']

            if 'error' in output:
                result = _record_validation_failure(invoice, output['error'], export, exporter)
                results.append(result)
                continue

            result = _send_request_per_invoice_item(invoice, output['xml_string'], export, api_url)
            results.append(result)

    except Exception as e:
        logger.exception(f"Fatal error during MRP export: {e}")
        fatal_error = str(e)
    finally:
        # Always update export status
        if fatal_error:
            export.status = Export.STATUS_FAILED
        elif export.items.failed().exists():
            export.status = Export.STATUS_FAILED
        else:
            export.status = Export.STATUS_FINISHED

        export.save(update_fields=['status'])

        # Always send email summary to user
        _send_mail_with_summary(export.creator, results, fatal_error=fatal_error)


def _send_request_per_invoice_item(invoice, xml_string, export, api_url):
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
            'Content-Type': f'application/xml; charset={InvoiceMrpListExporterMixin.xml_encoding}'
        }
        logger.debug(f"Sending invoice {invoice.number} to MRP server: {api_url}")
        response = requests.post(
            api_url,
            data=xml_string,
            headers=headers,
            timeout=InvoiceMrpListExporterMixin.request_timeout
        )
        response.raise_for_status()
        logger.info(f"Received response for invoice {invoice.number}: {response.status_code}")

        # Parse and check response
        response_xml = _parse_response_xml(response)
        error_info = _extract_xml_errors(response_xml, request_id)
        if error_info:
            logger.warning(f"Invoice {invoice.number} failed: Request ID: {request_id} - {error_info['error']}")
            export_result, export_detail, result = _build_failure(
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
        timeout_msg = f'Request timeout: The MRP server did not respond within {InvoiceMrpListExporterMixin.request_timeout} seconds'
        export_result, export_detail, result = _build_failure(invoice.number, request_id, timeout_msg)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when sending invoice {invoice.number}: {e}")
        export_result, export_detail, result = _build_failure(invoice.number, request_id, f'Network error: {str(e)}')
    except Exception as e:
        logger.exception(f"Unexpected error when sending invoice {invoice.number}: {e}")
        export_result, export_detail, result = _build_failure(invoice.number, request_id, f'Unexpected error: {str(e)}')
    finally:
        # Send signal once at the end
        export_item_changed.send(
            sender=export.exporter,
            export_id=export.id,
            content_type=export.content_type,
            object_id=invoice.id,
            result=export_result,
            detail=export_detail,
        )

    return result


def _send_mail_with_summary(user, results, fatal_error=None):
    """
    Send email summary of MRP export results to the user.

    Args:
        user: User object to send email to
        results: List of result dictionaries from invoice processing
        fatal_error: Optional string describing a fatal error that aborted the export
    """
    lines = [
        str(_('MRP export of invoices')),
        "",
    ]

    if fatal_error:
        lines.extend([
            str(_('Export failed with a fatal error:')),
            f"  {fatal_error}",
            "",
        ])

    lines.extend([
        f"{_('Total invoices processed')}: {len(results)}",
        f"{_('Successful')}: {sum(1 for r in results if r['status'] == 'success')}",
        f"{_('Errors')}: {sum(1 for r in results if r['status'] == 'error')}",
    ])

    error_results = [r for r in results if r['status'] == 'error']
    if error_results:
        lines.extend([
            "",
            str(_('Error details:')),
        ])

        for r in error_results:
            invoice_number = r.get('invoice_number')
            error = r.get('error')
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


def _record_validation_failure(invoice, error_msg, export, exporter):
    """
    Record an invoice that failed XML generation/validation.

    Fires the export_item_changed signal and returns an error result dict
    for inclusion in the email summary.
    """
    logger.warning(f"Skipping invoice {invoice.number}: {error_msg}")
    export_item_changed.send(
        sender=exporter,
        export_id=export.id,
        content_type=export.content_type,
        object_id=invoice.id,
        result=ExportItem.RESULT_FAILURE,
        detail=error_msg,
    )
    _, _, result = _build_failure(invoice.number, None, error_msg)
    return result


def _build_failure(invoice_number, request_id, error_message, error_code=None, error_class=None):
    """
    Build a failure tuple for a failed invoice export.

    Returns:
        tuple: (export_result, export_detail, result_dict)
    """
    result = {
        'invoice_number': str(invoice_number),
        'request_id': request_id,
        'status': 'error',
        'error': str(error_message),
    }
    if error_code is not None:
        result['error_code'] = str(error_code)
    if error_class is not None:
        result['error_class'] = str(error_class)
    return ExportItem.RESULT_FAILURE, str(error_message), result


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
