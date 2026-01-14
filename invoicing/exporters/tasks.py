from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives
from django.utils import translation
from django.utils.translation import gettext as _

from invoicing.models import Invoice, InvoiceExport
from invoicing.signals import invoices_exported
from invoicing.utils import get_task_decorator, generate_export_id

task = get_task_decorator("exports")

@task
def mail_exported_invoices(exporter_class, creator_id, recipients_ids, invoice_ids, export_prefix, filename, manager_class, method_name=None, params=None, language=settings.LANGUAGE_CODE):
    """Universal task for exporting invoices via email.
    
    Args:
        exporter_class: The exporter class to use
        creator_id: ID of user who initiated export
        recipients_ids: List of recipient user IDs
        invoice_ids: List of invoice IDs to export
        export_prefix: Prefix for export_id generation
        filename: Name of the exported file
        manager_class: Manager class that initiated the export
        method_name: Name of the manager method (e.g., 'export_pdf'), defaults to exporter class name
        params: Optional parameters for exporter
        language: Language code for translation
    """
    creator, recipients, invoice_qs, export_id = setup_export_context(creator_id, recipients_ids, invoice_ids, export_prefix, language)

    exporter = exporter_class(user=creator, recipients=recipients, params=params)
    exporter.queryset = invoice_qs

    exporter.export()
    export = exporter.save_export()

    invoices_exported.send(
        sender=manager_class,
        invoices=invoice_qs,
        method=method_name or exporter_class.__name__,
        export_id=export_id,
        result=InvoiceExport.RESULT.SUCCESS,
        detail='',
        creator=creator
    )

    return send_export(
        items=invoice_qs,
        body=exporter.get_message_body(export.total),
        recipients=recipients,
        output_file=exporter.get_output(),
        filename=filename
    )


def setup_export_context(creator_id, recipients_ids, invoice_ids, export_prefix='', language=settings.LANGUAGE_CODE):
    """
    Common setup for export tasks.

    Returns:
        tuple: (creator, recipients, invoice_qs, export_id)
    """
    translation.activate(language)
    user_model = get_user_model()

    try:
        creator = user_model.objects.get(id=creator_id)
    except ObjectDoesNotExist:
        creator = None

    recipients = user_model.objects.filter(id__in=recipients_ids) if recipients_ids else []
    invoice_qs = Invoice.objects.filter(id__in=invoice_ids) if invoice_ids else []
    export_id = generate_export_id(export_prefix)

    return creator, recipients, invoice_qs, export_id


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

