import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.http import QueryDict
from django.utils.translation import gettext as _
from outputs.models import Export, ExportItem
from pragmatic.utils import compress, get_task_decorator

from invoicing.exporters.mrp.v1.list import InvoiceFakvyXmlMrpExporter, InvoiceFakvypolXmlMrpExporter, InvoiceFvAdresXmlMrpExporter
from invoicing.models import Invoice
from invoicing.utils import setup_export_context

logger = logging.getLogger(__name__)

task = get_task_decorator("exports")


@task
def mail_exported_invoices_mrp_v1(creator_id, recipients_ids, invoice_ids, filename, params=None, language=settings.LANGUAGE_CODE):
    """MRP v1 export task - combines 3 XML exporters into a single zip file."""
    creator, recipients, invoice_qs = setup_export_context(creator_id, recipients_ids, invoice_ids, language)

    logger.info(f"Exporting {invoice_qs.count()} invoices via export_mrp_v1.")

    # Initialize and run all exporters
    exporters = [
        InvoiceFakvyXmlMrpExporter(user=creator, recipients=recipients, params=params),
        InvoiceFakvypolXmlMrpExporter(user=creator, recipients=recipients, params=params),
        InvoiceFvAdresXmlMrpExporter(user=creator, recipients=recipients, params=params),
    ]

    for exporter in exporters:
        exporter.queryset = invoice_qs
        exporter.export()

    # Combine into zip
    export_files = [
        {'name': exporter.get_filename(), 'content': exporter.get_output()}
        for exporter in exporters
    ]
    zip_file = compress(export_files)
    zip_file.seek(0)

    # Track export
    content_type = ContentType.objects.get_for_model(Invoice)
    export = Export.objects.create(
        content_type=content_type,
        format=Export.FORMAT_XML,
        context=Export.CONTEXT_LIST,
        creator=creator,
        query_string=params.urlencode() if params else QueryDict(),
        total=invoice_qs.count()
    )
    export.recipients.add(*list(recipients))

    export_items = [
        ExportItem(
            export=export,
            object_id=invoice.id,
            content_type=content_type,
            result=ExportItem.RESULT_SUCCESS,
            detail=invoice,
        )
        for invoice in invoice_qs
    ]

    created_items = ExportItem.objects.bulk_create(export_items)

    # update status of export
    export.status = Export.STATUS_FINISHED
    export.save(update_fields=['status'])

    logger.info(
        f"Created {len(created_items)} Export items record(s) for export {export.id}",
    )

    return send_export(
        items=invoice_qs,
        body=exporters[0].get_message_body(export.total),
        recipients=recipients,
        output_file=zip_file,
        filename=filename
    )

def send_export(items, body, recipients, output_file, filename):
    """Send exported invoices via email."""
    subject = _('Export of invoices')

    body = f'{body}<br>'
    body = '{}{}:<br>'.format(body, _('Invoices'))

    for invoice in items:
        body += f'{invoice.number}<br>'

    # prepare message
    message = EmailMultiAlternatives(subject=subject, to=recipients.values_list('email', flat=True))
    message.attach_alternative(body, "text/html")

    # attach file
    message.attach(
        filename,
        output_file,
        'application/force-download'
    )

    return message.send(fail_silently=False)