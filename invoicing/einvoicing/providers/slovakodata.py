"""
SLOVAKODATA ePostman, a Slovak Digital Postman.

Documents go out through its standard SAPI-SK interface (SapiSkProvider);
status, validation, participant lookups and webhooks, which SAPI-SK 1.0
lacks, come from its proprietary Enterprise API (``X-Api-Key``).

The provider takes its credentials as arguments and stores nothing. Where they
come from is the project's choice, through
``INVOICING_EINVOICING['PROVIDER_RESOLVER']``:

* one account for the whole project: ``from_settings`` below, reading
  ``INVOICING_EINVOICING['SLOVAKODATA']``;
* an account per supplier (or anything else): a resolver of the project's own
  that builds ``SlovakodataProvider(...)`` from wherever it keeps them.
"""
import hashlib
import hmac
from datetime import timedelta

import requests
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now as django_now
from django.utils.translation import gettext

from invoicing.einvoicing import conf
from invoicing.einvoicing.identifiers import CREDIT_NOTE_TYPE_CODE, DOCUMENT_TYPE_IDS
from invoicing.einvoicing.models import TransmissionStatus as Status
from invoicing.einvoicing.providers.base import ProviderError, Reachability, StatusResult
from invoicing.einvoicing.providers.sapi_sk import SapiSkProvider
from invoicing.einvoicing.validation import FATAL, WARNING, ValidationReport


HOSTS = {
    'test': 'https://testpostman.slovakodata.com',
    'production': 'https://postman.slovakodata.com',
}

# ePostman invoice status -> transmission status
STATUSES = {
    'PENDING': Status.SUBMITTED,
    'VALIDATING': Status.SUBMITTED,
    'VALIDATED': Status.SUBMITTED,
    'READY': Status.SUBMITTED,
    'SENDING': Status.SUBMITTED,
    'VALIDATION_FAILED': Status.REJECTED,
    'DELIVERED': Status.DELIVERED,
    'DELIVERED_NON_PEPPOL': Status.DELIVERED_NON_PEPPOL,
    'ACCEPTED': Status.ACCEPTED,
    'UNCONFIRMED': Status.UNCONFIRMED,
    'REJECTED': Status.REJECTED,
    'UNDELIVERABLE': Status.UNDELIVERABLE,
    'FAILED': Status.FAILED,
    'CANCELLED': Status.CANCELLED,
}

# What a webhook for every outcome subscribes to (ePostman "Webhooky"); the portal offers fewer
WEBHOOK_EVENTS = [
    'invoice.submitted', 'invoice.delivered', 'invoice.accepted', 'invoice.rejected', 'invoice.unconfirmed',
    'invoice.failed', 'invoice.undeliverable', 'mls.received', 'mls.nok',
]


def verify_signature(raw_body, signature, timestamp, secret, now=None, max_age=timedelta(minutes=5)):
    """
    True when X-Webhook-Signature is the hex HMAC-SHA256 of
    "{X-Webhook-Timestamp}.{raw body}" with ``secret``, and the timestamp
    (ISO 8601) is at most ``max_age`` off, so a captured notification cannot be
    replayed later.
    """
    if not (secret and signature and timestamp):
        return False

    sent_at = parse_datetime(timestamp.replace('Z', '+00:00'))
    if sent_at is None or sent_at.tzinfo is None:
        return False
    if abs((now or django_now()) - sent_at) > max_age:
        return False

    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


class SlovakodataProvider(SapiSkProvider):
    name = 'slovakodata'

    def __init__(self, environment, client_id, client_secret, api_key='', webhook_secret='', **kwargs):
        self.host = HOSTS[environment]
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        super().__init__(f'{self.host}/sapi', client_id, client_secret, environment=environment, **kwargs)

    # The Enterprise API needs the API key; without it, the provider can only send

    @property
    def supports_status(self):
        return bool(self.api_key)

    @property
    def supports_validation(self):
        return bool(self.api_key)

    @property
    def supports_reachability(self):
        return bool(self.api_key)

    @property
    def supports_webhooks(self):
        return bool(self.webhook_secret)

    def enterprise_request(self, method, path, *, json=None, params=None):
        try:
            response = self.session.request(
                method, f'{self.host}{path}', json=json, params=params, timeout=self.timeout,
                headers={'X-Api-Key': self.api_key, 'Accept': 'application/json', 'Accept-Language': 'sk'},
            )
        except requests.RequestException as error:
            raise ProviderError(f'Cannot reach {self.host}: {error}', code='CONNECTION', retryable=True) from error

        if response.status_code >= 400:
            raise self.error_from_response(response)

        return response.json()

    def get_status(self, provider_document_id):
        data = self.enterprise_request('GET', f'/api/v1/invoices/{provider_document_id}')
        provider_status = data.get('status', '')

        return StatusResult(
            # an unknown status keeps the transmission polled rather than guessing
            status=STATUSES.get(provider_status, Status.SUBMITTED),
            provider_status=provider_status,
            changed_at=parse_datetime(data['updatedAt']) if data.get('updatedAt') else None,
            raw={key: data.get(key) for key in ('id', 'status', 'mlsC3Status', 'mlsC5Status', 'invoiceNumber', 'updatedAt')},
        )

    def validate(self, xml, receiver_id=None):
        body = {'xml_content': xml.decode('utf-8') if isinstance(xml, bytes) else xml}
        if receiver_id:
            body['receiver_peppol_id'] = receiver_id

        data = self.enterprise_request('POST', '/api/v1/documents/validate', json=body)
        report = ValidationReport()

        for severity, findings in ((FATAL, data.get('errors', [])), (WARNING, data.get('warnings', []))):
            for finding in findings:
                message = ' '.join(part for part in (finding.get('title'), finding.get('explanation'), finding.get('fix')) if part)
                report.add(finding.get('rule_id', ''), message or finding.get('raw_message', ''), self.name,
                           severity=severity, location=finding.get('location') or finding.get('raw_location') or '')

        receiver = data.get('receiver') or {}
        if receiver.get('registered') is False or receiver.get('supports_document_type') is False:
            report.add('RECEIVER', f'{receiver_id} cannot receive this document in Peppol ({receiver.get("reason")}); '
                                   f'send the invoice by e-mail instead', self.name)
        elif receiver_id and receiver.get('registered') is None:
            report.add('RECEIVER', f'Whether {receiver_id} can receive e-invoices could not be checked', self.name, WARNING)

        return report

    def check_reachability(self, participant_id, document_type_id):
        document_type = 'CREDIT_NOTE' if document_type_id == DOCUMENT_TYPE_IDS[CREDIT_NOTE_TYPE_CODE] else 'INVOICE'
        data = self.enterprise_request('GET', f'/api/v1/participants/{participant_id}/reachability',
                                       params={'document_type': document_type})
        return Reachability(
            registered=data.get('registered'),
            supports_document_type=data.get('supports_document_type'),
            reason=data.get('reason') or '',
        )

    def resubmission_blocked_reason(self, previous):
        # ePostman ("Odosielanie", business key table): once it started the transfer and it
        # failed, any new submission under the same number gets 409, changed or not;
        # its support repeats the transfer instead.
        if previous.status == Status.FAILED:
            return gettext(
                'SLOVAKODATA started sending this invoice and the transfer failed (document %(document)s). '
                'It refuses another submission under the same number: ask its support '
                '(podpora@postman.slovakodata.com) to repeat the transfer, or issue the invoice under a new number.'
            ) % {'document': previous.provider_document_id}
        return None

    # Webhooks

    @classmethod
    def webhook_document_id(cls, payload):
        return ((payload or {}).get('data') or {}).get('invoice_id') or None

    def verify_webhook(self, raw_body, headers):
        return verify_signature(raw_body, headers.get('X-Webhook-Signature', ''),
                                headers.get('X-Webhook-Timestamp', ''), self.webhook_secret)

    def create_webhook(self, url, events=None, timeout_seconds=30, retry_count=5):
        """
        Registers a webhook for ``url`` and returns ePostman's answer, including
        its ``secret`` -- the only time ePostman shows it (its portal does not):
        store it as this account's webhook secret.
        """
        return self.enterprise_request('POST', '/api/v1/webhooks', json={
            'url': url, 'events': list(events or WEBHOOK_EVENTS),
            'timeout_seconds': timeout_seconds, 'retry_count': retry_count,
        })

    def list_webhooks(self):
        data = self.enterprise_request('GET', '/api/v1/webhooks')
        return data if isinstance(data, list) else data.get('data', [])

    def delete_webhook(self, webhook_id):
        return self.enterprise_request('DELETE', f'/api/v1/webhooks/{webhook_id}')

    def test_webhook(self, webhook_id):
        return self.enterprise_request('POST', f'/api/v1/webhooks/{webhook_id}/test')


def from_settings(invoice=None):
    """
    PROVIDER_RESOLVER for a project with one SLOVAKODATA account, from
    ``INVOICING_EINVOICING['SLOVAKODATA']``; None when it is not configured.
    """
    config = conf.get('SLOVAKODATA')
    if not config:
        return None

    return SlovakodataProvider(
        config.get('ENVIRONMENT', 'test'), config['CLIENT_ID'], config['CLIENT_SECRET'],
        api_key=config.get('API_KEY', ''), webhook_secret=config.get('WEBHOOK_SECRET', ''),
    )
