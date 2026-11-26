"""
Peppol identifiers: participant IDs, document type and process IDs, and the
deterministic document UUID used by Slovak eFaktúra.
"""
import re
import uuid
from dataclasses import dataclass


INVOICE_TYPE_CODE = '380'
CREDIT_NOTE_TYPE_CODE = '381'

# Peppol BIS Billing 3.0 (EN 16931:2017 semantics). No version suffix is
# allowed in the CustomizationID itself (PEPPOL-EN16931-R004).
CUSTOMIZATION_ID = 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0'
PROFILE_ID = 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'
PROCESS_ID = PROFILE_ID

DOCUMENT_TYPE_IDS = {
    INVOICE_TYPE_CODE: f'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##{CUSTOMIZATION_ID}::2.1',
    CREDIT_NOTE_TYPE_CODE: f'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##{CUSTOMIZATION_ID}::2.1',
}

# Slovak DIČ (EAS/ICD 0245), mandatory for Slovak participants since Peppol 3.0.20
SK_SCHEME = '0245'

# Namespace of rule ID-BDID-01, Slovak eFaktúra Solution Architecture v1.2, §9.2.3.
# (The FS transposition xlsx v1.11 quotes a different namespace, whose own example
# does not verify; see docs/einvoicing.md.)
DOCUMENT_UUID_NAMESPACE = uuid.UUID('e0bc4ac8-b025-46e5-a76d-0c893fc3027e')

_PARTICIPANT_RE = re.compile(r'^(?:0245:[0-9]{10}|(?!0245:)[0-9]{4}:[A-Za-z0-9.\-_]+)$')


class IdentifierError(ValueError):
    pass


@dataclass(frozen=True)
class ParticipantId:
    scheme: str
    value: str

    def __post_init__(self):
        if not _PARTICIPANT_RE.match(str(self)):
            raise IdentifierError(f'Invalid Peppol participant ID {str(self)!r}')

    def __str__(self):
        return f'{self.scheme}:{self.value}'

    @classmethod
    def parse(cls, participant_id):
        scheme, separator, value = (participant_id or '').strip().partition(':')

        if not separator:
            raise IdentifierError(f'Invalid Peppol participant ID {participant_id!r}')

        return cls(scheme, value)


def sk_participant_id(tax_id):
    """Participant ID of a Slovak business from its DIČ, e.g. ``0245:2020123456``."""
    return ParticipantId(SK_SCHEME, re.sub(r'\s', '', tax_id or ''))


def document_uuid(scheme, endpoint_id, type_code, number, issue_date):
    """
    Deterministic document UUID (Slovak rule ID-BDID-01): UUIDv5 over seller
    endpoint scheme (BT-34-1), seller endpoint (BT-34), type code (BT-3),
    invoice number (BT-1) and issue date (BT-2), joined by single spaces.
    """
    parts = [str(scheme), str(endpoint_id), str(type_code), str(number), issue_date.isoformat()]
    return uuid.uuid5(DOCUMENT_UUID_NAMESPACE, ' '.join(part.strip() for part in parts))
