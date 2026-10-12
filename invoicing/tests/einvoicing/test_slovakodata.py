import json
from datetime import timedelta

import pytest
import responses

from invoicing.einvoicing.models import TransmissionStatus as Status
from invoicing.einvoicing.providers.slovakodata import (
    WEBHOOK_EVENTS, SlovakodataProvider, from_settings, verify_signature,
)
from invoicing.tests.einvoicing.webhooks import sign


ENTERPRISE = 'https://testpostman.slovakodata.com/api/v1'


@pytest.fixture
def provider():
    return SlovakodataProvider('test', 'client', 'secret', api_key='api-key', webhook_secret='whsec')


def validation_response(errors=(), registered=True):
    return {
        'valid': not errors, 'overall_severity': 'error' if errors else 'none', 'validation_levels': {},
        'errors': list(errors), 'warnings': [], 'truncated': False, 'total_findings': len(errors),
        'document': {}, 'duration_ms': 5,
        'receiver': {'peppol_id': '0245:2021654321', 'registered': registered, 'supports_document_type': registered,
                     'reason': None if registered else 'NOT_REGISTERED', 'checked_at': '2026-10-01T12:00:00Z'},
    }


class TestProvider:
    def test_hosts(self):
        assert SlovakodataProvider('test', 'c', 's').base_url == 'https://testpostman.slovakodata.com/sapi'
        assert SlovakodataProvider('production', 'c', 's').base_url == 'https://postman.slovakodata.com/sapi'

    def test_capabilities_follow_the_credentials(self, provider):
        assert provider.supports_status and provider.supports_validation and provider.supports_reachability
        assert provider.supports_webhooks

        bare = SlovakodataProvider('test', 'c', 's')
        assert not (bare.supports_status or bare.supports_validation or bare.supports_reachability or bare.supports_webhooks)

    @pytest.mark.parametrize('provider_status, status', [
        ('PENDING', Status.SUBMITTED), ('READY', Status.SUBMITTED), ('SENDING', Status.SUBMITTED),
        ('VALIDATION_FAILED', Status.REJECTED), ('DELIVERED', Status.DELIVERED), ('ACCEPTED', Status.ACCEPTED),
        ('DELIVERED_NON_PEPPOL', Status.DELIVERED_NON_PEPPOL), ('UNCONFIRMED', Status.UNCONFIRMED),
        ('UNDELIVERABLE', Status.UNDELIVERABLE), ('FAILED', Status.FAILED), ('SOMETHING_NEW', Status.SUBMITTED),
    ])
    @responses.activate
    def test_status(self, provider, provider_status, status):
        responses.get(f'{ENTERPRISE}/invoices/doc-1', json={'id': 'doc-1', 'status': provider_status})

        result = provider.get_status('doc-1')

        assert (result.status, result.provider_status) == (status, provider_status)
        assert responses.calls[0].request.headers['X-Api-Key'] == 'api-key'

    @responses.activate
    def test_validate(self, provider):
        responses.post(f'{ENTERPRISE}/documents/validate', json=validation_response(errors=[{
            'rule_id': 'SK-R-021', 'rule_set': 'L5_sk', 'level': 5, 'severity': 'fatal', 'raw_message': 'raw',
            'raw_location': '/Invoice', 'title': 'Chýba schéma 0245', 'explanation': 'Vysvetlenie.', 'fix': 'Oprava.',
            'location': 'Dodávateľ', 'localized': True}]))

        report = provider.validate(b'<Invoice/>', receiver_id='0245:2021654321')

        assert [(f.rule_id, f.severity, f.source) for f in report.findings] == [('SK-R-021', 'fatal', 'slovakodata')]
        assert json.loads(responses.calls[0].request.body) == {'xml_content': '<Invoice/>', 'receiver_peppol_id': '0245:2021654321'}

    @responses.activate
    def test_unregistered_receiver_is_fatal(self, provider):
        responses.post(f'{ENTERPRISE}/documents/validate', json=validation_response(registered=False))

        assert [f.rule_id for f in provider.validate(b'<Invoice/>', receiver_id='0245:2021654321').errors] == ['RECEIVER']

    @responses.activate
    def test_reachability(self, provider):
        responses.get(f'{ENTERPRISE}/participants/0245:2021654321/reachability', json={
            'peppol_id': '0245:2021654321', 'registered': True, 'supports_document_type': True, 'reason': None,
            'checked_at': '2026-10-01T12:00:00Z'})

        result = provider.check_reachability('0245:2021654321', 'x')

        assert result.registered and result.supports_document_type
        assert responses.calls[0].request.url.endswith('document_type=INVOICE')

    def test_resubmission_after_failure(self, provider):
        class Previous:
            status = Status.FAILED
            provider_document_id = 'doc-1'

        assert 'podpora@postman.slovakodata.com' in provider.resubmission_blocked_reason(Previous)
        Previous.status = Status.UNDELIVERABLE
        assert provider.resubmission_blocked_reason(Previous) is None

    @responses.activate
    def test_webhook_management(self, provider):
        create = responses.post(f'{ENTERPRISE}/webhooks', json={'id': 'wh-1', 'secret': 'whsec_new'}, status=201)
        responses.get(f'{ENTERPRISE}/webhooks', json=[{'id': 'wh-1'}])
        responses.delete(f'{ENTERPRISE}/webhooks/wh-1', json={})
        responses.post(f'{ENTERPRISE}/webhooks/wh-1/test', json={'http_status': 200})

        assert provider.create_webhook('https://example.com/einvoicing/webhook/slovakodata/')['secret'] == 'whsec_new'
        body = json.loads(create.calls[0].request.body)
        assert body == {'url': 'https://example.com/einvoicing/webhook/slovakodata/', 'events': WEBHOOK_EVENTS,
                        'timeout_seconds': 30, 'retry_count': 5}
        assert provider.list_webhooks() == [{'id': 'wh-1'}]
        assert provider.test_webhook('wh-1') == {'http_status': 200}
        provider.delete_webhook('wh-1')

    def test_webhook_document_id(self):
        assert SlovakodataProvider.webhook_document_id({'data': {'invoice_id': 'doc-1'}}) == 'doc-1'
        assert SlovakodataProvider.webhook_document_id({'event': 'test'}) is None


class TestSignature:
    BODY = b'{"event": "invoice.delivered"}'

    def test_genuine(self):
        assert verify_signature(self.BODY, *sign(self.BODY, 'whsec'), 'whsec')

    @pytest.mark.parametrize('case', ['wrong secret', 'other body', 'stale', 'future', 'garbage', 'no secret'])
    def test_refused(self, case):
        from django.utils.timezone import now
        signature, timestamp = sign(self.BODY, 'whsec')
        body, secret = self.BODY, 'whsec'

        if case == 'wrong secret':
            secret = 'other'
        elif case == 'other body':
            body = b'{}'
        elif case in ('stale', 'future'):
            signature, timestamp = sign(self.BODY, 'whsec', now() + timedelta(minutes=6) * (-1 if case == 'stale' else 1))
        elif case == 'garbage':
            timestamp = 'yesterday'
        elif case == 'no secret':
            secret = ''

        assert not verify_signature(body, signature, timestamp, secret)


class TestFromSettings:
    def test_not_configured(self, settings):
        settings.INVOICING_EINVOICING = {}

        assert from_settings() is None

    def test_configured(self, settings):
        settings.INVOICING_EINVOICING = {'SLOVAKODATA': {
            'ENVIRONMENT': 'production', 'CLIENT_ID': 'c', 'CLIENT_SECRET': 's', 'API_KEY': 'k', 'WEBHOOK_SECRET': 'w'}}

        provider = from_settings(invoice=None)

        assert provider.base_url == 'https://postman.slovakodata.com/sapi'
        assert (provider.client_id, provider.client_secret, provider.api_key, provider.webhook_secret) == ('c', 's', 'k', 'w')
