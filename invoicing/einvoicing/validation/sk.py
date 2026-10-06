"""
Slovak national requirements on top of Peppol BIS Billing 3.0.

UNOFFICIAL. The Financial Administration publishes these requirements only
as a human-readable table ("Transpozícia štandardu Peppol BIS v podmienkach
slovenskej legislatívy", v1.11 of 2026-09-11, column "Povinná náležitosť
faktúry podľa SK legislatívy"), with no rule identifiers and no Schematron.
These checks are this library's reading of that table; their IDs (SK-LOCAL-*)
are its own.
"""
from lxml import etree

from invoicing.einvoicing.identifiers import SK_SCHEME
from invoicing.einvoicing.validation.report import WARNING, ValidationReport


NS = {
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}


def _text(node, path):
    return (node.findtext(path, default='', namespaces=NS) or '').strip()


def _check_party(report, party, role, prefix):
    if party is None:
        return

    if _text(party, 'cac:PostalAddress/cac:Country/cbc:IdentificationCode') != 'SK':
        return

    endpoint = party.find('cbc:EndpointID', NS)
    if endpoint is None or endpoint.get('schemeID') != SK_SCHEME:
        report.add(f'{prefix}-01', f'A Slovak {role} has to be addressed by scheme {SK_SCHEME} (DIČ)', 'sk')

    missing = [
        label for path, label in (
            ('cac:PostalAddress/cbc:StreetName', 'street'),
            ('cac:PostalAddress/cbc:CityName', 'city'),
            ('cac:PostalAddress/cbc:PostalZone', 'postal code'),
        )
        if not _text(party, path)
    ]
    if missing:
        report.add(f'{prefix}-02', f'The {role} address has to state its {", ".join(missing)}', 'sk')

    if not _text(party, 'cac:PartyLegalEntity/cbc:CompanyID'):
        report.add(f'{prefix}-03', f'The {role} IČO (legal registration identifier) is required when one was assigned', 'sk', WARNING)


def validate(xml):
    report = ValidationReport()
    document = etree.fromstring(xml)

    seller = document.find('cac:AccountingSupplierParty/cac:Party', NS)
    buyer = document.find('cac:AccountingCustomerParty/cac:Party', NS)

    _check_party(report, seller, 'seller', 'SK-LOCAL-SELLER')
    _check_party(report, buyer, 'buyer', 'SK-LOCAL-BUYER')

    if seller is not None and _text(seller, 'cac:PostalAddress/cac:Country/cbc:IdentificationCode') == 'SK':
        if not _text(seller, 'cac:PartyLegalEntity/cbc:CompanyLegalForm'):
            report.add(
                'SK-LOCAL-SELLER-04',
                'The seller legal form and commercial register entry (BT-33) are required for companies',
                'sk', WARNING,
            )

    return report
