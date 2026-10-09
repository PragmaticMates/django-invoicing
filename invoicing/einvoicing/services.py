"""
Sending an invoice as an e-invoice, safely.

    transmission = prepare(invoice, attachments=[...])   # build, validate, store
    submit(transmission)                                  # hand over to the provider
    refresh_status(transmission)                          # later, if the provider can tell

Guarantees:

* The XML is built and validated once, and stored before any network call.
  Every submission of a transmission sends exactly those bytes with the same
  idempotency key, so retrying after a timeout, a crash or a 5xx cannot
  produce a second, different document at the provider.
* An invoice has at most one live or successful transmission (a conditional
  unique constraint). ``prepare`` returns it rather than creating another.
  A new one is possible only after the previous one ended NOT_DELIVERED.
* A transmitted invoice cannot be deleted (PROTECT), so its number, which
  identifies the document in Peppol, can never be reused for another one.
"""
import hashlib
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils.timezone import now

from invoicing.einvoicing import conf
from invoicing.einvoicing.identifiers import (
    CUSTOMIZATION_ID, DOCUMENT_TYPE_IDS, PROCESS_ID, PROFILE_ID, ParticipantId, document_uuid,
)
from invoicing.einvoicing.models import NOT_DELIVERED, POLLABLE, REACHED, EInvoiceTransmission, TransmissionStatus
from invoicing.einvoicing.providers import OutgoingDocument, ProviderError, get_provider
from invoicing.einvoicing.signals import transmission_status_changed
from invoicing.einvoicing.ubl import get_builder
from invoicing.einvoicing.validation import preflight, validate

logger = logging.getLogger(__name__)


class EInvoicingError(Exception):
    pass


class EInvoiceValidationError(EInvoicingError):
    def __init__(self, report):
        self.report = report
        super().__init__(f'The e-invoice is not valid:\n{report}')


class TransmissionError(EInvoicingError):
    pass


class ResubmissionNotAllowed(EInvoicingError):
    pass


def live_transmission(invoice):
    return invoice.einvoice_transmissions.exclude(status__in=NOT_DELIVERED).first()


def resubmission_blocked_reason(invoice, provider):
    """Why ``provider`` would refuse the invoice again (see EInvoiceProvider), or None."""
    previous = invoice.einvoice_transmissions.filter(provider=provider.name) \
        .exclude(provider_document_id='').order_by('-created').first()

    if previous is None or previous.is_live:
        return None

    return provider.resubmission_blocked_reason(previous)


def resolve_conflict(transmission, note):
    """
    Ends a CONFLICT transmission as REFUSED, once a human established that the
    provider did not take this submission (e.g. it only pointed at an earlier
    one). The invoice can then be prepared again.
    """
    with transaction.atomic():
        transmission = EInvoiceTransmission.objects.select_for_update().get(pk=transmission.pk)
        if transmission.status != TransmissionStatus.CONFLICT:
            raise TransmissionError(f'Transmission {transmission.pk} is {transmission.status}, not in conflict')
        _set_status(transmission, TransmissionStatus.REFUSED, message=note)
    return transmission


def build_and_validate(invoice, *, provider=None, attachments=()):
    """(xml bytes, ValidationReport). Raises EInvoiceValidationError on any fatal finding."""
    report = preflight(invoice)
    if not report.is_valid:
        raise EInvoiceValidationError(report)

    xml = get_builder(invoice, attachments=attachments).build()
    report.extend(validate(xml))
    if not report.is_valid:
        raise EInvoiceValidationError(report)

    if provider is not None and provider.supports_validation and conf.get('PREVALIDATE_WITH_PROVIDER'):
        receiver = f'{invoice.customer_endpoint_scheme}:{invoice.customer_endpoint_id}'
        report.extend(provider.validate(xml, receiver_id=receiver))
        if not report.is_valid:
            raise EInvoiceValidationError(report)

    return xml, report


def prepare(invoice, *, provider=None, attachments=()):
    """
    The invoice's live transmission, or a new one with its XML built,
    validated and stored. Raises EInvoiceValidationError when the invoice
    cannot be sent as it is.
    """
    existing = live_transmission(invoice)
    if existing:
        return existing

    provider = provider or get_provider(invoice)

    reason = resubmission_blocked_reason(invoice, provider)
    if reason:
        raise ResubmissionNotAllowed(reason)

    # Built outside the transaction: provider validation goes over the network
    xml, report = build_and_validate(invoice, provider=provider, attachments=attachments)
    type_code = '381' if invoice.type == invoice.TYPE.CREDIT_NOTE else '380'
    sender = ParticipantId(invoice.supplier_endpoint_scheme, invoice.supplier_endpoint_id)
    receiver = ParticipantId(invoice.customer_endpoint_scheme, invoice.customer_endpoint_id)

    try:
        with transaction.atomic():
            # serialises concurrent prepare() calls for the same invoice
            type(invoice).objects.select_for_update().filter(pk=invoice.pk).first()

            existing = live_transmission(invoice)
            if existing:
                return existing

            return EInvoiceTransmission.objects.create(
                invoice=invoice,
                provider=provider.name,
                environment=provider.environment,
                document_uuid=document_uuid(sender.scheme, sender.value, type_code, invoice.number, invoice.date_issue),
                sender_id=str(sender),
                receiver_id=str(receiver),
                document_type_id=DOCUMENT_TYPE_IDS[type_code],
                process_id=PROCESS_ID,
                customization_id=CUSTOMIZATION_ID,
                profile_id=PROFILE_ID,
                xml=xml.decode('utf-8'),
                xml_sha256=hashlib.sha256(xml).hexdigest(),
                validation_report=report.as_dict(),
            )
    except IntegrityError:
        # lost a race the row lock did not cover (e.g. the invoice row was not locked)
        existing = live_transmission(invoice)
        if existing:
            return existing
        raise


def _set_status(transmission, status, *, provider_status=None, event_kind='status', **event):
    previous = transmission.status
    transmission.status = status
    if provider_status is not None:
        transmission.provider_status = provider_status
    if status in REACHED and transmission.delivered_at is None:
        transmission.delivered_at = now()
    transmission.save()

    transmission.events.create(kind=event_kind, status=status, **event)

    if previous != status:
        transmission_status_changed.send(sender=EInvoiceTransmission, transmission=transmission, previous_status=previous)


def _document(transmission):
    return OutgoingDocument(
        document_id=str(transmission.document_uuid),
        idempotency_key=str(transmission.idempotency_key),
        sender_id=transmission.sender_id,
        receiver_id=transmission.receiver_id,
        document_type_id=transmission.document_type_id,
        process_id=transmission.process_id,
        payload=transmission.xml,
        checksum=transmission.xml_sha256,
        created_at=transmission.created,
    )


def _claim_for_submission(transmission):
    """Moves the transmission to SUBMITTING, unless it is not (or no longer) due for submission."""
    with transaction.atomic():
        locked = EInvoiceTransmission.objects.select_for_update().get(pk=transmission.pk)

        stale = now() - timedelta(seconds=conf.get('SUBMITTING_TIMEOUT_SECONDS'))
        submittable = locked.status in (TransmissionStatus.PREPARED, TransmissionStatus.SUBMIT_UNKNOWN) or (
            locked.status == TransmissionStatus.SUBMITTING and locked.modified < stale
        )

        if not submittable:
            return locked, False

        locked.status = TransmissionStatus.SUBMITTING
        locked.attempt_count += 1
        locked.save(update_fields=['status', 'attempt_count', 'modified'])
        return locked, True


def submit(transmission, *, provider=None):
    """
    Hands the stored XML to the provider. Safe to call again at any time:
    a transmission already submitted (or being submitted) is returned as is.

    A retryable failure leaves it SUBMIT_UNKNOWN and re-raises the
    ProviderError, so a job queue can retry with backoff. A refusal (the
    provider did not take the document) ends it REFUSED, after which the
    invoice can be prepared again. A conflict (HTTP 409) ends it CONFLICT.
    """
    provider = provider or get_provider(transmission.invoice)
    if provider.name != transmission.provider:
        raise TransmissionError(f'Transmission {transmission.pk} belongs to provider {transmission.provider}, not {provider.name}')

    transmission, claimed = _claim_for_submission(transmission)
    if not claimed:
        return transmission

    try:
        result = provider.submit(_document(transmission))
    except ProviderError as error:
        transmission.last_error = error.as_dict()

        if error.retryable or error.outcome_unknown:
            status = TransmissionStatus.SUBMIT_UNKNOWN
        elif error.http_status == 409:
            # Business duplicate or a key clash: the provider may well hold this document
            # already (e.g. its first response was lost more than a day ago). Neither safe
            # to treat as unsent nor worth resubmitting; needs a human.
            status = TransmissionStatus.CONFLICT
        else:
            status = TransmissionStatus.REFUSED

        _set_status(transmission, status, event_kind='error', http_status=error.http_status,
                    provider_code=error.code, correlation_id=error.correlation_id,
                    message=error.message, payload=error.raw)
        logger.warning('E-invoice transmission %s: %s (%s)', transmission.pk, error.message, error.code)

        if status == TransmissionStatus.SUBMIT_UNKNOWN:
            raise
        return transmission

    transmission.provider_document_id = result.provider_document_id
    transmission.provider_received_at = result.received_at
    transmission.submitted_at = now()
    transmission.last_error = None

    _set_status(
        transmission,
        TransmissionStatus.SUBMITTED if result.accepted else TransmissionStatus.REFUSED,
        provider_status='ACCEPTED' if result.accepted else 'REJECTED',
        event_kind='submit', http_status=202, payload=result.raw,
    )
    return transmission


def refresh_status(transmission, *, provider=None):
    """Asks the provider for news about a submitted transmission, if it can tell."""
    if transmission.status not in POLLABLE or not transmission.provider_document_id:
        return transmission

    provider = provider or get_provider(transmission.invoice)
    if not provider.supports_status:
        return transmission

    result = provider.get_status(transmission.provider_document_id)
    transmission.last_status_check_at = now()

    if result.status == transmission.status and result.provider_status == transmission.provider_status:
        transmission.save(update_fields=['last_status_check_at', 'modified'])
        return transmission

    _set_status(transmission, result.status, provider_status=result.provider_status, payload=result.raw)
    return transmission


def transmissions_to_poll():
    since = now() - timedelta(days=conf.get('STATUS_POLL_DAYS'))
    return EInvoiceTransmission.objects.filter(status__in=POLLABLE, submitted_at__gte=since).exclude(provider_document_id='')


def transmissions_to_resubmit():
    stale = now() - timedelta(seconds=conf.get('SUBMITTING_TIMEOUT_SECONDS'))
    return EInvoiceTransmission.objects.filter(status__in=[TransmissionStatus.PREPARED, TransmissionStatus.SUBMIT_UNKNOWN]) | \
        EInvoiceTransmission.objects.filter(status=TransmissionStatus.SUBMITTING, modified__lt=stale)
