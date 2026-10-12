"""The webhook view, send()/check() with their guards, background jobs and the admin send action."""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib
from django.urls import reverse

from invoicing.einvoicing import services, tasks
from invoicing.einvoicing.models import EInvoiceTransmission, TransmissionStatus as Status
from invoicing.einvoicing.providers.slovakodata import SlovakodataProvider
from invoicing.einvoicing.ubl import Attachment
from invoicing.models import Invoice
from invoicing.tests.einvoicing.test_services import FakeProvider
from invoicing.tests.einvoicing.webhooks import sign


D = Decimal
pytestmark = [pytest.mark.django_db, pytest.mark.urls('invoicing.tests.einvoicing.webhook_urls')]
SECRETS = {}


def slovakodata_resolver(invoice):
    """An account per supplier VAT ID, each with its own webhook secret."""
    return SlovakodataProvider('test', 'client', 'secret', api_key='key', webhook_secret=SECRETS.get(invoice.supplier_vat_id, ''))


def fake_resolver(invoice):
    return fake_resolver.provider


def pdf_attachments(invoice):
    return [Attachment(f'{invoice.number}.pdf', b'%PDF-1.4')]


@pytest.fixture
def slovakodata(settings):
    settings.INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'invoicing.tests.einvoicing.test_sending.slovakodata_resolver'}
    SECRETS.clear()
    SECRETS['SK2020123456'] = 'whsec-mine'


@pytest.fixture
def fake(settings):
    fake_resolver.provider = FakeProvider()
    settings.INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'invoicing.tests.einvoicing.test_sending.fake_resolver'}
    return fake_resolver.provider


def transmission_for(invoice, document_id='doc-1', provider='slovakodata'):
    return EInvoiceTransmission.objects.create(
        invoice=invoice, provider=provider, document_uuid='1780de4f-a87c-50cc-9d8a-f982abe36912', sender_id='0245:2020123456',
        receiver_id='0245:2021654321', document_type_id='t', process_id='p', customization_id='c', profile_id='p',
        xml='<Invoice/>', xml_sha256='0', status=Status.SUBMITTED, provider_document_id=document_id,
    )


class TestWebhook:
    URL = '/einvoicing/webhook/slovakodata/'

    def notify(self, client, body, secret='whsec-mine', url=None, **headers):
        signature, timestamp = sign(body, secret)
        headers = {'HTTP_X_WEBHOOK_SIGNATURE': signature, 'HTTP_X_WEBHOOK_TIMESTAMP': timestamp, **headers}
        return client.post(url or self.URL, body, content_type='application/json', **headers)

    @staticmethod
    def body(document_id='doc-1', event='invoice.delivered'):
        return json.dumps({'event': event, 'data': {'invoice_id': document_id, 'status': 'DELIVERED'}}, indent=2).encode()

    def test_genuine_notification_refreshes_the_status(self, client, einvoice_factory, slovakodata):
        transmission = transmission_for(einvoice_factory([dict(unit_price=D('10'))]))

        with patch.object(tasks, 'dispatch_task') as dispatch:
            assert self.notify(client, self.body()).status_code == 200

        dispatch.assert_called_once_with(tasks.refresh_einvoice, transmission.pk)

    def test_status_comes_from_the_provider(self, client, einvoice_factory, slovakodata):
        transmission = transmission_for(einvoice_factory([dict(unit_price=D('10'))]))

        with responses_lib.RequestsMock() as mock:
            mock.get('https://testpostman.slovakodata.com/api/v1/invoices/doc-1', json={'status': 'ACCEPTED'})
            self.notify(client, self.body())  # claims DELIVERED

        transmission.refresh_from_db()
        assert transmission.status == Status.ACCEPTED

    def test_older_per_account_urls_still_work(self, client, einvoice_factory, slovakodata):
        transmission_for(einvoice_factory([dict(unit_price=D('10'))]))

        with patch.object(tasks, 'dispatch_task'):
            assert self.notify(client, self.body(), url='/legacy/webhook/slovakodata/1/').status_code == 200

    def test_another_accounts_secret_is_refused(self, client, einvoice_factory, slovakodata):
        SECRETS['SK2021999999'] = 'whsec-theirs'
        transmission_for(einvoice_factory([dict(unit_price=D('10'))]))

        with patch.object(tasks, 'dispatch_task') as dispatch:
            assert self.notify(client, self.body(), secret='whsec-theirs').status_code == 401
        dispatch.assert_not_called()

    def test_unsigned_is_refused(self, client, einvoice_factory, slovakodata):
        transmission_for(einvoice_factory([dict(unit_price=D('10'))]))

        assert client.post(self.URL, self.body(), content_type='application/json').status_code == 401

    def test_unknown_document_is_acknowledged(self, client, slovakodata):
        with patch.object(tasks, 'dispatch_task') as dispatch:
            assert self.notify(client, self.body(document_id='incoming', event='invoice.received')).status_code == 200
        dispatch.assert_not_called()

    def test_not_json(self, client, slovakodata):
        assert client.post(self.URL, b'nope', content_type='application/json').status_code == 400

    def test_unknown_provider_and_method(self, client, slovakodata):
        assert client.post('/einvoicing/webhook/other/', b'{}', content_type='application/json').status_code == 404
        assert client.get(self.URL).status_code == 405


class TestSend:
    def test_send_queues_the_submission(self, einvoice_factory, fake, django_capture_on_commit_callbacks):
        invoice = einvoice_factory([dict(unit_price=D('10'))])

        with django_capture_on_commit_callbacks(execute=True):
            transmission = services.send(invoice)

        transmission.refresh_from_db()
        assert transmission.status == Status.SUBMITTED  # the stubbed dispatch ran the job inline
        assert services.send(invoice) == transmission   # a second send finds the live one

    def test_attachments_from_settings(self, einvoice_factory, fake, settings):
        settings.INVOICING_EINVOICING = {**settings.INVOICING_EINVOICING,
                                         'ATTACHMENTS': 'invoicing.tests.einvoicing.test_sending.pdf_attachments'}
        invoice = einvoice_factory([dict(unit_price=D('10'))])

        xml, report = services.check(invoice)

        assert report.is_valid and b'EmbeddedDocumentBinaryObject' in xml
        assert not EInvoiceTransmission.objects.exists()

    @pytest.mark.parametrize('sendable, status, message', [
        (('NEW',), Invoice.STATUS.PAID, 'Only a new invoice'),
        (('NEW', 'SENT'), Invoice.STATUS.PAID, 'cannot be sent as an e-invoice'),
    ])
    def test_sendable_statuses(self, einvoice_factory, fake, settings, sendable, status, message):
        settings.INVOICING_EINVOICING = {**settings.INVOICING_EINVOICING, 'SENDABLE_STATUSES': sendable}
        invoice = einvoice_factory([dict(unit_price=D('10'))], status=status)

        with pytest.raises(services.SendNotAllowed, match=message):
            services.send(invoice)

    def test_any_status_by_default(self, einvoice_factory, fake):
        assert services.send_blocked_reason(einvoice_factory([dict(unit_price=D('10'))], status=Invoice.STATUS.PAID)) is None

    def test_customer_address_is_required(self, einvoice_factory, fake):
        invoice = einvoice_factory([dict(unit_price=D('10'))], customer_endpoint_id='')

        assert 'no electronic address' in services.send_blocked_reason(invoice)


class TestJobs:
    def test_maintenance_resubmits_and_polls(self, einvoice_factory, fake):
        from invoicing.einvoicing.providers import StatusResult
        fake.statuses = [StatusResult(Status.DELIVERED, 'DELIVERED')]
        unsent = services.prepare(einvoice_factory([dict(unit_price=D('10'))]))

        tasks.einvoicing_maintenance()

        unsent.refresh_from_db()
        assert unsent.status == Status.DELIVERED  # submitted, then polled

    def test_maintenance_gives_up_after_max_attempts(self, einvoice_factory, fake, settings):
        settings.INVOICING_EINVOICING = {**settings.INVOICING_EINVOICING, 'MAX_SUBMIT_ATTEMPTS': 2}
        transmission = services.prepare(einvoice_factory([dict(unit_price=D('10'))]))
        EInvoiceTransmission.objects.filter(pk=transmission.pk).update(status=Status.SUBMIT_UNKNOWN, attempt_count=2)

        tasks.einvoicing_maintenance()

        assert fake.submitted == []

    def test_schedule_jobs(self, settings):
        from django.apps import apps
        scheduler = MagicMock()
        fake_rq = MagicMock(get_scheduler=MagicMock(return_value=scheduler))

        with patch.dict('sys.modules', {'django_rq': fake_rq}):
            apps.get_app_config('invoicing_einvoicing').schedule_jobs()
            settings.INVOICING_EINVOICING = {'MAINTENANCE_CRON': None}
            apps.get_app_config('invoicing_einvoicing').schedule_jobs()

        fake_rq.get_scheduler.assert_called_once_with('cron')
        args, kwargs = scheduler.cron.call_args
        assert args == ('*/15 * * * *',)
        assert kwargs['func'] == 'invoicing.einvoicing.tasks.einvoicing_maintenance'
        assert kwargs['queue_name'] == 'cron'


class TestAdmin:
    CHANGELIST = 'admin:invoicing_invoice_changelist'

    def test_send_action_asks_first(self, admin_client, einvoice_factory, fake, settings):
        settings.INVOICING_MANAGERS = {'invoicing.exporters.einvoicing.managers.EInvoicingManager': {}}
        ready = einvoice_factory([dict(unit_price=D('10'))])
        no_address = einvoice_factory([dict(unit_price=D('10'))], number='2026-002', customer_endpoint_id='')

        with patch('invoicing.admin.invoicing_settings.INVOICING_MANAGERS', settings.INVOICING_MANAGERS):
            page = admin_client.post(reverse(self.CHANGELIST), {
                'action': 'einvoicingmanager_export_via_api', '_selected_action': [ready.pk, no_address.pk]})

        assert page.status_code == 200
        assert page.templates[0].name == 'admin/invoicing/einvoicing/send_confirmation.html'
        content = page.content.decode()
        assert 'will be sent' in content and 'no electronic address' in content
        assert not EInvoiceTransmission.objects.exists()  # nothing sent before confirming

    def test_confirmed_send(self, admin_client, einvoice_factory, fake, settings, django_capture_on_commit_callbacks):
        settings.INVOICING_MANAGERS = {'invoicing.exporters.einvoicing.managers.EInvoicingManager': {}}
        ready = einvoice_factory([dict(unit_price=D('10'))])
        no_address = einvoice_factory([dict(unit_price=D('10'))], number='2026-002', customer_endpoint_id='')

        with patch('invoicing.admin.invoicing_settings.INVOICING_MANAGERS', settings.INVOICING_MANAGERS), \
                django_capture_on_commit_callbacks(execute=True):
            response = admin_client.post(reverse(self.CHANGELIST), {
                'action': 'einvoicingmanager_export_via_api', '_selected_action': [ready.pk, no_address.pk],
                'confirm': 'yes'}, follow=True)

        assert response.status_code == 200
        assert list(EInvoiceTransmission.objects.values_list('invoice__number', flat=True)) == ['2026-001']
        messages = [str(message) for message in response.context['messages']]
        assert any('1 invoice(s) queued' in message for message in messages)
        assert any('2026-002' in message for message in messages)

    def test_status_column(self, admin_client, einvoice_factory, fake):
        sent = einvoice_factory([dict(unit_price=D('10'))])
        transmission_for(sent, provider='fake')
        einvoice_factory([dict(unit_price=D('10'))], number='2026-002')

        content = admin_client.get(reverse(self.CHANGELIST)).content.decode()

        assert 'column-einvoice_status' in content
        assert 'Submitted' in content
        assert reverse('admin:invoicing_einvoicing_einvoicetransmission_change', args=[sent.einvoice_transmissions.get().pk]) in content
