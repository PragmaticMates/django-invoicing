import uuid

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class TransmissionStatus(models.TextChoices):
    PREPARED = 'PREPARED', _('Prepared')
    SUBMITTING = 'SUBMITTING', _('Submitting')
    SUBMIT_UNKNOWN = 'SUBMIT_UNKNOWN', _('Submission outcome unknown')
    CONFLICT = 'CONFLICT', _('Conflict at provider')  # it may hold the document already; needs a human
    REFUSED = 'REFUSED', _('Refused by provider')
    SUBMITTED = 'SUBMITTED', _('Submitted')
    DELIVERED = 'DELIVERED', _('Delivered')
    DELIVERED_NON_PEPPOL = 'DELIVERED_NON_PEPPOL', _('Delivered outside Peppol')
    ACCEPTED = 'ACCEPTED', _('Accepted by recipient')
    UNCONFIRMED = 'UNCONFIRMED', _('Delivered, unconfirmed')
    REJECTED = 'REJECTED', _('Rejected')
    UNDELIVERABLE = 'UNDELIVERABLE', _('Undeliverable')
    FAILED = 'FAILED', _('Failed')
    CANCELLED = 'CANCELLED', _('Cancelled')


# Ended without the document reaching the recipient: the invoice may be sent again,
# as a new transmission (the XML may have been corrected in the meantime)
NOT_DELIVERED = frozenset({
    TransmissionStatus.REFUSED, TransmissionStatus.REJECTED, TransmissionStatus.UNDELIVERABLE,
    TransmissionStatus.FAILED, TransmissionStatus.CANCELLED,
})

# The provider has the document and may still report progress
POLLABLE = frozenset({TransmissionStatus.SUBMITTED, TransmissionStatus.DELIVERED})

# Reached the recipient (or, for DELIVERED_NON_PEPPOL, the tax authority instead)
REACHED = frozenset({
    TransmissionStatus.DELIVERED, TransmissionStatus.DELIVERED_NON_PEPPOL,
    TransmissionStatus.ACCEPTED, TransmissionStatus.UNCONFIRMED,
})


class EInvoiceTransmission(models.Model):
    """
    One attempt to send an invoice as a structured e-invoice.

    The XML is built once, stored here before anything goes over the network,
    and never rebuilt: every (re)submission sends these exact bytes with the
    same idempotency key. At most one transmission per invoice can be live or
    successful; a new one is possible only after one ended NOT_DELIVERED.
    """
    Status = TransmissionStatus

    invoice = models.ForeignKey('invoicing.Invoice', verbose_name=_('invoice'), on_delete=models.PROTECT,
                                related_name='einvoice_transmissions')
    provider = models.CharField(_('provider'), max_length=64)
    environment = models.CharField(_('environment'), max_length=32, blank=True)

    document_uuid = models.UUIDField(_('document UUID'), db_index=True)
    idempotency_key = models.UUIDField(_('idempotency key'), unique=True, default=uuid.uuid4, editable=False)
    sender_id = models.CharField(_('sender'), max_length=64)
    receiver_id = models.CharField(_('receiver'), max_length=64)
    document_type_id = models.CharField(_('document type'), max_length=500)
    process_id = models.CharField(_('process'), max_length=255)
    customization_id = models.CharField(_('customization'), max_length=255)
    profile_id = models.CharField(_('profile'), max_length=255)

    xml = models.TextField(_('XML'), editable=False)
    xml_sha256 = models.CharField(_('XML SHA-256'), max_length=64, editable=False)
    validation_report = models.JSONField(_('validation report'), default=dict, blank=True)

    status = models.CharField(_('status'), max_length=32, choices=TransmissionStatus.choices,
                              default=TransmissionStatus.PREPARED, db_index=True)
    provider_document_id = models.CharField(_('provider document ID'), max_length=255, blank=True, db_index=True)
    provider_status = models.CharField(_('provider status'), max_length=64, blank=True)
    last_error = models.JSONField(_('last error'), null=True, blank=True)
    attempt_count = models.PositiveIntegerField(_('submission attempts'), default=0)

    created = models.DateTimeField(_('created'), auto_now_add=True)
    modified = models.DateTimeField(_('modified'), auto_now=True)
    submitted_at = models.DateTimeField(_('submitted at'), null=True, blank=True)
    provider_received_at = models.DateTimeField(_('received by provider at'), null=True, blank=True)
    delivered_at = models.DateTimeField(_('delivered at'), null=True, blank=True)
    last_status_check_at = models.DateTimeField(_('status last checked at'), null=True, blank=True)

    class Meta:
        verbose_name = _('e-invoice transmission')
        verbose_name_plural = _('e-invoice transmissions')
        ordering = ('-created',)
        constraints = [
            models.UniqueConstraint(
                fields=['invoice'], condition=~Q(status__in=sorted(NOT_DELIVERED)),
                name='einvoice_one_live_transmission_per_invoice',
            ),
        ]

    def __str__(self):
        return f'{self.invoice} → {self.receiver_id} ({self.get_status_display()})'

    @property
    def xml_bytes(self):
        return self.xml.encode('utf-8')

    @property
    def is_live(self):
        return self.status not in NOT_DELIVERED

    @property
    def has_reached_recipient(self):
        return self.status in REACHED


class EInvoiceTransmissionEvent(models.Model):
    """Append-only log of everything that happened to a transmission."""
    KIND_SUBMIT = 'submit'
    KIND_STATUS = 'status'
    KIND_ERROR = 'error'
    KINDS = (
        (KIND_SUBMIT, _('submission')),
        (KIND_STATUS, _('status change')),
        (KIND_ERROR, _('error')),
    )

    transmission = models.ForeignKey(EInvoiceTransmission, verbose_name=_('transmission'), on_delete=models.CASCADE,
                                     related_name='events')
    created = models.DateTimeField(_('created'), auto_now_add=True)
    kind = models.CharField(_('kind'), max_length=16, choices=KINDS)
    status = models.CharField(_('status'), max_length=32, blank=True)
    http_status = models.PositiveSmallIntegerField(_('HTTP status'), null=True, blank=True)
    provider_code = models.CharField(_('provider code'), max_length=64, blank=True)
    correlation_id = models.CharField(_('correlation ID'), max_length=255, blank=True)
    message = models.TextField(_('message'), blank=True)
    payload = models.JSONField(_('payload'), null=True, blank=True)

    class Meta:
        verbose_name = _('e-invoice transmission event')
        verbose_name_plural = _('e-invoice transmission events')
        ordering = ('created', 'pk')

    def __str__(self):
        return f'{self.get_kind_display()} {self.status} {self.provider_code}'.strip()
