from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta

try:
    # older Django
    from django.utils.translation import ugettext_lazy as _
except ImportError:
    # Django >= 3
    from django.utils.translation import gettext_lazy as _


class Config(AppConfig):
    name = 'invoicing'
    verbose_name = _('Invoicing')

    def ready(self):
        from invoicing.models import Invoice

        counter_period = getattr(settings, "INVOICING_COUNTER_PERIOD")
        sequence = 1
        date = now()
        invoice1 = Invoice(date_issue=date, sequence=sequence)

        if counter_period == Invoice.COUNTER_PERIOD.DAILY:
            date += relativedelta(days=1)
        elif counter_period == Invoice.COUNTER_PERIOD.MONTHLY:
            date += relativedelta(months=1)
        elif counter_period == Invoice.COUNTER_PERIOD.YEARLY:
            date += relativedelta(years=1)
        elif counter_period == Invoice.COUNTER_PERIOD.INFINITE:
            sequence += 1

        invoice2 = Invoice(date_issue=date, sequence=sequence)

        if invoice1._get_number() == invoice2._get_number():
            raise ImproperlyConfigured("The INVOICING_NUMBER_FORMAT is incorrect for the current INVOICING_COUNTER_PERIOD")
