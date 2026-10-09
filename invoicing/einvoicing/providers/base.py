"""
The interface between invoicing.einvoicing and whoever delivers documents
into Peppol (an Access Point, or "Digital Postman" in Slovakia).

Only ``submit`` is required. Status, validation and reachability are
optional capabilities: SAPI-SK 1.0, for one, has no outbound status call.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OutgoingDocument:
    document_id: str           # our ID of the document, the deterministic document UUID
    idempotency_key: str       # the same for every submission of the same transmission
    sender_id: str             # Peppol participant IDs, e.g. 0245:2020123456
    receiver_id: str
    document_type_id: str
    process_id: str
    payload: str               # the UBL XML
    checksum: str              # SHA-256 (hex) of the UTF-8 payload
    created_at: datetime


@dataclass(frozen=True)
class SubmitResult:
    provider_document_id: str
    accepted: bool = True
    received_at: datetime = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StatusResult:
    status: str                # one of models.TransmissionStatus
    provider_status: str       # the provider's own name for it
    changed_at: datetime = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Reachability:
    registered: bool = None              # None: unknown
    supports_document_type: bool = None  # None: unknown
    reason: str = ''


class ProviderError(Exception):
    """
    The provider did not take the document, or the call failed.

    ``retryable``: the same request may simply be sent again later.
    ``outcome_unknown``: the request may have been processed even so (a
    timeout after sending, a 5xx); only a resubmission with the same
    idempotency key, or a status check, can tell.
    """
    def __init__(self, message, *, code='', retryable=False, outcome_unknown=False, http_status=None,
                 correlation_id='', details=None, retry_after=None, raw=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown
        self.http_status = http_status
        self.correlation_id = correlation_id
        self.details = details or []
        self.retry_after = retry_after
        self.raw = raw

    def as_dict(self):
        return {
            'message': self.message, 'code': self.code, 'retryable': self.retryable,
            'outcome_unknown': self.outcome_unknown, 'http_status': self.http_status,
            'correlation_id': self.correlation_id, 'details': self.details,
        }


class CapabilityNotSupported(NotImplementedError):
    pass


class EInvoiceProvider(ABC):
    name = ''
    environment = ''

    supports_status = False
    supports_validation = False
    supports_reachability = False

    @abstractmethod
    def submit(self, document):
        """Hands the document over; returns a SubmitResult or raises ProviderError."""

    def get_status(self, provider_document_id):
        """Returns a StatusResult."""
        raise CapabilityNotSupported(f'{self.name} cannot report document status')

    def validate(self, xml, receiver_id=None):
        """Returns a validation.ValidationReport of the provider's own checks."""
        raise CapabilityNotSupported(f'{self.name} cannot validate documents')

    def resubmission_blocked_reason(self, previous):
        """
        Why the invoice cannot be submitted to this provider again, after
        ``previous`` (its latest transmission the provider took) ended without
        reaching the recipient; None when it can. Providers differ: some refuse
        a new submission under the same number after certain failures and
        retry those themselves.
        """
        return None

    def check_reachability(self, participant_id, document_type_id):
        """Returns a Reachability."""
        raise CapabilityNotSupported(f'{self.name} cannot look up participants')
