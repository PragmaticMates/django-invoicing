from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Max
from django.template import Template, Context

from invoicing.models import Invoice


def sequence_generator(type, important_date, number_prefix=None, related_invoices=None):
    """
    Returns next invoice sequence based on ``settings.INVOICING_COUNTER_PERIOD``.

    .. warning::

        This is only used to prepopulate ``sequence`` field on saving new invoice.
        To get invoice sequence always use ``sequence`` field.

    .. note::

        To get invoice number use ``number`` field.

    :return: string (generated next sequence)
    """
    with transaction.atomic():
        Invoice.objects.lock()

        invoice_counter_reset = getattr(settings, 'INVOICING_COUNTER_PERIOD', Invoice.COUNTER_PERIOD.YEARLY)

        if related_invoices is None:
            related_invoices = Invoice.objects.all()

        if invoice_counter_reset == Invoice.COUNTER_PERIOD.DAILY:
            related_invoices = related_invoices.filter(date_issue=important_date)

        elif invoice_counter_reset == Invoice.COUNTER_PERIOD.YEARLY:
            related_invoices = related_invoices.filter(date_issue__year=important_date.year)

        elif invoice_counter_reset == Invoice.COUNTER_PERIOD.MONTHLY:
            related_invoices = related_invoices.filter(date_issue__year=important_date.year, date_issue__month=important_date.month)

        else:
            raise ImproperlyConfigured("INVOICING_COUNTER_PERIOD can be set only to these values: DAILY, MONTHLY, YEARLY.")

        invoice_counter_per_type = getattr(settings, 'INVOICING_COUNTER_PER_TYPE', False)

        if invoice_counter_per_type:
            related_invoices = related_invoices.filter(type=type)

        if number_prefix is not None:
            related_invoices = related_invoices.filter(number__startswith=number_prefix)

        start_from = getattr(settings, 'INVOICING_NUMBER_START_FROM', 1)
        last_sequence = related_invoices.aggregate(Max('sequence'))['sequence__max'] or start_from - 1

        return last_sequence + 1


def number_formatter(invoice, number_format=None):
    """
    Generates on the fly invoice number from template provided by ``settings.INVOICING_NUMBER_FORMAT``.
    ``Invoice`` object is provided as ``invoice`` variable to the template, therefore all object fields
    can be used to generate number format.

    .. warning::

        This is only used to prepopulate ``number`` field on saving new invoice.
        To get invoice number always use ``number`` field.

    :return: string (generated number)
    """
    if not number_format:
        number_format = getattr(settings, "INVOICING_NUMBER_FORMAT", "{{ invoice.date_tax_point|date:'Y' }}/{{ invoice.sequence }}")
    return Template(number_format).render(Context({'invoice': invoice}))
