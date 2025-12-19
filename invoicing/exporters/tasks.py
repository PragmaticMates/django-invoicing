from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives
from django.utils import translation
from django.utils.translation import gettext as _

from invoicing.models import Invoice
from invoicing.utils import get_task_decorator

task = get_task_decorator("exports")

@task
def mail_exported_invoices(exporter_class, creator_id, recipients_ids, invoice_ids, filename, params=None, language=settings.LANGUAGE_CODE):
    """Universal task for exporting invoices via email."""
    creator, recipients, invoice_qs = setup_export_context(creator_id, recipients_ids, invoice_ids, language)

    exporter = exporter_class(user=creator, recipients=recipients, params=params)
    exporter.queryset = invoice_qs

    exporter.export()
    export = exporter.save_export()

    return send_export(
        items=invoice_qs,
        body=exporter.get_message_body(export.total),
        recipients=recipients,
        output_file=exporter.get_output(),
        filename=filename
    )


def setup_export_context(creator_id, recipients_ids, invoice_ids, language=settings.LANGUAGE_CODE):
    """
    Common setup for export tasks.

    Returns:
        tuple: (creator, recipients, invoice_qs)
    """
    translation.activate(language)
    user_model = get_user_model()

    try:
        creator = user_model.objects.get(id=creator_id)
    except ObjectDoesNotExist:
        creator = None

    recipients = user_model.objects.filter(id__in=recipients_ids)
    invoice_qs = Invoice.objects.filter(id__in=invoice_ids)

    return creator, recipients, invoice_qs


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

