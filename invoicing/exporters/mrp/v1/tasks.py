from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict
from outputs.models import Export
from pragmatic.utils import compress

from invoicing.exporters.mrp.v1.list import InvoiceFakvyXmlMrpExporter, InvoiceFakvypolXmlMrpExporter, InvoiceFvAdresXmlMrpExporter
from invoicing.exporters.tasks import setup_export_context, send_export
from invoicing.managers import MRPManager
from invoicing.models import Invoice, InvoiceExport
from invoicing.signals import invoices_exported
from invoicing.utils import get_task_decorator

task = get_task_decorator("exports")


@task
def mail_exported_invoices_mrp_v1(creator_id, recipients_ids, invoice_ids, export_prefix, filename, params=None, language=settings.LANGUAGE_CODE):
    """MRP v1 export task - combines 3 XML exporters into a single zip file."""
    creator, recipients, invoice_qs, export_id = setup_export_context(creator_id, recipients_ids, invoice_ids, export_prefix, language)

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
    export = Export.objects.create(
        content_type=ContentType.objects.get_for_model(Invoice),
        format=Export.FORMAT_XML_MRP,
        context=Export.CONTEXT_LIST,
        creator=creator,
        query_string=params.urlencode() if params else QueryDict(),
        total=invoice_qs.count()
    )
    export.recipients.add(*list(recipients))
    export.items.add(*list(invoice_qs))

    invoices_exported.send(
        sender=MRPManager,
        invoices=invoice_qs,
        method='export_mrp_v1',
        export_id=export_id,
        result=InvoiceExport.RESULT.SUCCESS,
        detail='',
        creator=creator
    )

    return send_export(
        items=invoice_qs,
        body=exporters[0].get_message_body(export.total),
        recipients=recipients,
        output_file=zip_file,
        filename=filename
    )
