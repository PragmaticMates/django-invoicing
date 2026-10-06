import hashlib
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.utils.timezone import now

from invoicing.einvoicing import services
from invoicing.einvoicing.identifiers import document_uuid
from invoicing.einvoicing.models import EInvoiceTransmission, TransmissionStatus as Status
from invoicing.einvoicing.providers import EInvoiceProvider, ProviderError, StatusResult, SubmitResult
from invoicing.einvoicing.signals import transmission_status_changed
from invoicing.einvoicing.validation import ValidationReport


D = Decimal


class FakeProvider(EInvoiceProvider):
    name = 'fake'
    environment = 'test'
    supports_status = True
    supports_validation = True

    def __init__(self, outcomes=(), statuses=(), validation=None):
        self.outcomes = list(outcomes)
        self.statuses = list(statuses)
        self.validation = validation or ValidationReport()
        self.submitted = []

    def submit(self, document):
        self.submitted.append(document)
        outcome = self.outcomes.pop(0) if self.outcomes else SubmitResult(f'doc-{len(self.submitted)}', received_at=now())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_status(self, provider_document_id):
        return self.statuses.pop(0)

    def validate(self, xml, receiver_id=None):
        return self.validation


@pytest.fixture
def invoice(einvoice_factory):
    return einvoice_factory([dict(unit_price=D('100.00'))])


@pytest.fixture
def provider(settings):
    provider = FakeProvider()
    settings.INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'invoicing.tests.einvoicing.test_services.resolve'}
    resolve.provider = provider
    return provider


def resolve(invoice):
    return resolve.provider


pytestmark = pytest.mark.django_db


class TestPrepare:
    def test_stores_the_validated_xml(self, invoice, provider):
        transmission = services.prepare(invoice)

        assert transmission.status == Status.PREPARED
        assert transmission.provider == 'fake'
        assert transmission.environment == 'test'
        assert transmission.sender_id == '0245:2020123456'
        assert transmission.receiver_id == '0245:2021654321'
        assert transmission.document_uuid == document_uuid('0245', '2020123456', '380', '2026-001', invoice.date_issue)
        assert transmission.xml.startswith("<?xml version='1.0' encoding='UTF-8'?>")
        assert transmission.xml_sha256 == hashlib.sha256(transmission.xml_bytes).hexdigest()
        assert transmission.validation_report['valid'] is True
        assert provider.submitted == []  # nothing goes over the network yet

    def test_returns_the_live_transmission(self, invoice, provider):
        first = services.prepare(invoice)

        assert services.prepare(invoice) == first
        assert EInvoiceTransmission.objects.count() == 1

    def test_invalid_invoice_is_not_stored(self, einvoice_factory, provider):
        invoice = einvoice_factory([dict(unit_price=D('10'))], customer_endpoint_id='')

        with pytest.raises(services.EInvoiceValidationError) as raised:
            services.prepare(invoice)

        assert 'PREFLIGHT-CUSTOMER-ENDPOINT' in {f.rule_id for f in raised.value.report.errors}
        assert not EInvoiceTransmission.objects.exists()

    def test_provider_validation(self, invoice, provider):
        provider.validation.add('SK-R-021', 'Missing 0245 scheme', 'fake')

        with pytest.raises(services.EInvoiceValidationError) as raised:
            services.prepare(invoice)

        assert [f.rule_id for f in raised.value.report.errors] == ['SK-R-021']

    def test_provider_validation_can_be_skipped(self, invoice, provider, settings):
        settings.INVOICING_EINVOICING = {**settings.INVOICING_EINVOICING, 'PREVALIDATE_WITH_PROVIDER': False}
        provider.validation.add('SK-R-021', 'Missing 0245 scheme', 'fake')

        assert services.prepare(invoice).status == Status.PREPARED

    def test_new_transmission_only_after_not_delivered(self, invoice, provider):
        first = services.prepare(invoice)
        first.status = Status.UNDELIVERABLE
        first.save()

        second = services.prepare(invoice)

        assert second != first
        assert second.idempotency_key != first.idempotency_key

    def test_one_live_transmission_is_enforced_by_the_database(self, invoice, provider):
        first = services.prepare(invoice)

        with pytest.raises(IntegrityError), transaction.atomic():
            EInvoiceTransmission.objects.create(
                invoice=invoice, provider='fake', document_uuid=first.document_uuid, sender_id='x', receiver_id='y',
                document_type_id='t', process_id='p', customization_id='c', profile_id='p', xml='<x/>', xml_sha256='0',
            )

    def test_transmitted_invoice_cannot_be_deleted(self, invoice, provider):
        services.prepare(invoice)

        with pytest.raises(ProtectedError):
            invoice.delete()


class TestSubmit:
    def test_submits_the_stored_bytes(self, invoice, provider):
        transmission = services.submit(services.prepare(invoice))

        document = provider.submitted[0]
        assert document.payload == transmission.xml
        assert document.checksum == transmission.xml_sha256
        assert document.idempotency_key == str(transmission.idempotency_key)
        assert document.document_id == str(transmission.document_uuid)
        assert transmission.status == Status.SUBMITTED
        assert transmission.provider_document_id == 'doc-1'
        assert transmission.submitted_at and transmission.provider_received_at
        assert transmission.attempt_count == 1
        assert list(transmission.events.values_list('kind', 'status')) == [('submit', Status.SUBMITTED)]

    def test_submitting_twice_sends_once(self, invoice, provider):
        transmission = services.prepare(invoice)

        services.submit(transmission)
        services.submit(transmission)

        assert len(provider.submitted) == 1

    def test_retry_after_unknown_outcome_resends_identical_request(self, invoice, provider):
        provider.outcomes = [ProviderError('timeout', code='TIMEOUT', retryable=True, outcome_unknown=True)]
        transmission = services.prepare(invoice)

        with pytest.raises(ProviderError):
            services.submit(transmission)
        transmission.refresh_from_db()
        assert transmission.status == Status.SUBMIT_UNKNOWN
        assert transmission.last_error['code'] == 'TIMEOUT'

        services.submit(transmission)

        first, second = provider.submitted
        assert first == second  # same key, same bytes, same metadata
        transmission.refresh_from_db()
        assert transmission.status == Status.SUBMITTED
        assert transmission.attempt_count == 2
        assert transmission.last_error is None

    def test_refusal_allows_a_new_transmission(self, invoice, provider):
        provider.outcomes = [ProviderError('no credit', code='SAPI-PROC-004', http_status=402)]
        transmission = services.submit(services.prepare(invoice))

        assert transmission.status == Status.REFUSED
        assert services.prepare(invoice) != transmission

    def test_rejected_on_receipt_is_a_refusal(self, invoice, provider):
        provider.outcomes = [SubmitResult('doc-1', accepted=False)]

        assert services.submit(services.prepare(invoice)).status == Status.REFUSED

    def test_conflict_needs_a_human(self, invoice, provider):
        provider.outcomes = [ProviderError('duplicate', code='SAPI-PERM-002', http_status=409)]
        transmission = services.submit(services.prepare(invoice))

        assert transmission.status == Status.CONFLICT
        assert services.prepare(invoice) == transmission  # still live: blocks a second document
        assert transmission not in services.transmissions_to_resubmit()
        services.submit(transmission)
        assert len(provider.submitted) == 1

    def test_stale_submitting_is_resubmitted(self, invoice, provider):
        transmission = services.prepare(invoice)
        EInvoiceTransmission.objects.filter(pk=transmission.pk).update(
            status=Status.SUBMITTING, modified=now() - timedelta(hours=1))

        assert transmission in services.transmissions_to_resubmit()
        assert services.submit(transmission).status == Status.SUBMITTED

    def test_fresh_submitting_is_left_alone(self, invoice, provider):
        transmission = services.prepare(invoice)
        EInvoiceTransmission.objects.filter(pk=transmission.pk).update(status=Status.SUBMITTING)

        assert services.submit(transmission).status == Status.SUBMITTING
        assert provider.submitted == []

    def test_wrong_provider(self, invoice, provider):
        transmission = services.prepare(invoice)
        other = FakeProvider()
        other.name = 'other'

        with pytest.raises(services.TransmissionError):
            services.submit(transmission, provider=other)
        transmission.refresh_from_db()
        assert transmission.status == Status.PREPARED


class TestRefreshStatus:
    def test_status_change(self, invoice, provider):
        changes = []
        receiver = lambda sender, transmission, previous_status, **kwargs: changes.append((previous_status, transmission.status))
        transmission_status_changed.connect(receiver)
        provider.statuses = [StatusResult(Status.DELIVERED, 'DELIVERED'), StatusResult(Status.ACCEPTED, 'ACCEPTED')]
        transmission = services.submit(services.prepare(invoice))

        try:
            services.refresh_status(transmission)
            delivered_at = transmission.delivered_at
            assert transmission.status == Status.DELIVERED and delivered_at
            assert transmission in services.transmissions_to_poll()

            services.refresh_status(transmission)
        finally:
            transmission_status_changed.disconnect(receiver)

        assert transmission.status == Status.ACCEPTED
        assert transmission.delivered_at == delivered_at
        assert transmission not in services.transmissions_to_poll()
        assert changes == [
            (Status.SUBMITTING, Status.SUBMITTED),
            (Status.SUBMITTED, Status.DELIVERED),
            (Status.DELIVERED, Status.ACCEPTED),
        ]

    def test_unchanged_status_only_records_the_check(self, invoice, provider):
        provider.statuses = [StatusResult(Status.SUBMITTED, 'ACCEPTED')]
        transmission = services.submit(services.prepare(invoice))
        events = transmission.events.count()

        services.refresh_status(transmission)

        assert transmission.last_status_check_at
        assert transmission.events.count() == events

    def test_not_polled_before_submission(self, invoice, provider):
        transmission = services.prepare(invoice)

        assert services.refresh_status(transmission).status == Status.PREPARED

    def test_old_transmissions_are_not_polled(self, invoice, provider):
        transmission = services.submit(services.prepare(invoice))
        EInvoiceTransmission.objects.filter(pk=transmission.pk).update(submitted_at=now() - timedelta(days=31))

        assert not services.transmissions_to_poll().exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_prepare_creates_one_transmission(einvoice_factory, provider):
    invoice = einvoice_factory([dict(unit_price=D('100.00'))])
    barrier = threading.Barrier(2)
    results, errors = [], []

    def run():
        try:
            barrier.wait()
            results.append(services.prepare(invoice).pk)
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(set(results)) == 1
    assert EInvoiceTransmission.objects.count() == 1
