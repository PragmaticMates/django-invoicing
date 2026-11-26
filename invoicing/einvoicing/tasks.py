"""
Background jobs for e-invoicing, through django-pragmatic's task decorator
(``PRAGMATIC_TASK_DECORATOR``, e.g. ``django_rq.job``), as the exporters use.
Without django-pragmatic they run synchronously.

* ``submit_einvoice``: hands a prepared transmission to its provider
* ``refresh_einvoice``: asks the provider for news (after a webhook, say)
* ``einvoicing_maintenance``: resubmits what is unsent and polls what is under
  way; ``EInvoicingConfig.schedule_jobs()`` runs it on
  ``INVOICING_EINVOICING['MAINTENANCE_CRON']`` with django-pragmatic's
  ``rqscheduler``
"""
import logging

from django.db import transaction

from invoicing.einvoicing import conf
from invoicing.einvoicing import services
from invoicing.einvoicing.models import EInvoiceTransmission
from invoicing.einvoicing.providers import ProviderError

logger = logging.getLogger(__name__)

try:
    from pragmatic.utils import dispatch_task, get_task_decorator
    task = get_task_decorator(conf.get('QUEUE'))
except ImportError:  # no django-pragmatic: run synchronously
    def task(function):
        return function

    def dispatch_task(function, *args, **kwargs):
        return function(*args, **kwargs)


@task
def submit_einvoice(transmission_id):
    services.submit(EInvoiceTransmission.objects.select_related('invoice').get(pk=transmission_id))


@task
def refresh_einvoice(transmission_id):
    services.refresh_status(EInvoiceTransmission.objects.select_related('invoice').get(pk=transmission_id))


@task
def einvoicing_maintenance():
    """Resubmits unsent transmissions (up to MAX_SUBMIT_ATTEMPTS) and polls those under way."""
    for transmission in services.transmissions_to_resubmit().filter(attempt_count__lt=conf.get('MAX_SUBMIT_ATTEMPTS')):
        try:
            services.submit(transmission)
        except ProviderError as error:
            logger.warning('E-invoice transmission %s still unsent: %s', transmission.pk, error)
        except Exception:
            logger.exception('E-invoice transmission %s could not be submitted', transmission.pk)

    for transmission in services.transmissions_to_poll():
        try:
            services.refresh_status(transmission)
        except Exception:
            logger.exception('Status of e-invoice transmission %s could not be refreshed', transmission.pk)


def queue_submission(transmission):
    """Submits the transmission in the background once the current transaction commits."""
    transaction.on_commit(lambda: dispatch_task(submit_einvoice, transmission.pk))


def queue_refresh(transmission):
    dispatch_task(refresh_einvoice, transmission.pk)
