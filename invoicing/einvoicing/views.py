import json
import logging

from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from invoicing.einvoicing import conf
from invoicing.einvoicing.models import EInvoiceTransmission
from invoicing.einvoicing.providers import get_provider
from invoicing.einvoicing.tasks import queue_refresh

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    """
    Event notifications from a provider (INVOICING_EINVOICING['WEBHOOK_PROVIDERS']).

    1. The notification names a provider document; that finds the transmission,
       and so the invoice. Nothing is trusted yet: this only picks the account.
    2. The resolver gives that invoice's provider -- with its webhook secret --
       which verifies the notification (401 if it does not).
    3. The status is then asked from the provider in the background
       (refresh_status), never taken from the notification, so a forged,
       replayed or out-of-order one changes nothing.

    Notifications about documents that are not ours (incoming invoices,
    documents sent from the provider's portal) are acknowledged and ignored, so
    the provider does not keep retrying them. Extra URL arguments are ignored,
    so older per-account webhook URLs keep working.
    """
    http_method_names = ['post']

    def post(self, request, provider, **kwargs):
        try:
            provider_class = import_string(conf.get('WEBHOOK_PROVIDERS')[provider])
        except KeyError:
            raise Http404(f'No webhooks from {provider}')

        try:
            payload = json.loads(request.body)
        except ValueError:
            return HttpResponse(status=400)

        document_id = provider_class.webhook_document_id(payload)
        transmission = EInvoiceTransmission.objects.select_related('invoice').filter(
            provider=provider_class.name, provider_document_id=document_id,
        ).first() if document_id else None

        if transmission is None:
            logger.info('E-invoice webhook %s for unknown document %s', payload.get('event'), document_id)
            return HttpResponse(status=200)

        try:
            account = get_provider(transmission.invoice)
        except ImproperlyConfigured:
            account = None

        if account is None or account.name != provider_class.name or not account.verify_webhook(request.body, request.headers):
            logger.warning('E-invoice webhook for transmission %s: invalid signature or stale timestamp', transmission.pk)
            return HttpResponse(status=401)

        queue_refresh(transmission)
        return HttpResponse(status=200)
