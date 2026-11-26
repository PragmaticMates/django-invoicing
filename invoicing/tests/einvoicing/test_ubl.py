"""
UBL output, checked two ways: byte-for-byte against reviewed golden files,
and against the real validation artefacts (UBL XSD + Peppol Schematron).

Regenerate the golden files after an intended change with
``EINVOICING_REGENERATE_GOLDEN=1 pytest invoicing/tests/einvoicing`` and
review the diff.
"""
import base64
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from invoicing.einvoicing.ubl import Attachment, PeppolBIS3Builder, get_builder
from invoicing.einvoicing.validation import validate
from invoicing.models import Invoice


D = Decimal
GOLDEN = Path(__file__).parent / 'golden'
NS = {
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}

pytestmark = pytest.mark.django_db


def assert_golden(name, xml):
    path = GOLDEN / f'{name}.xml'

    if os.environ.get('EINVOICING_REGENERATE_GOLDEN'):
        path.write_bytes(xml)

    assert xml == path.read_bytes(), f'{name}.xml differs; regenerate and review if intended'


def assert_valid(xml):
    report = validate(xml)
    assert report.is_valid, str(report)
    assert not report.warnings, str(report)


SCENARIOS = {
    'invoice-multirate': dict(
        items=[
            dict(title='Vývoj softvéru\nseptember 2026', quantity=D('12.5'), unit='HOURS', unit_price=D('60.00')),
            dict(title='Kniha', unit_price=D('19.99'), tax_rate=D('5'), discount=D('10')),
            dict(title='Licencia', quantity=D('3'), unit_price=D('33.33'), tax_rate=D('19')),
        ],
    ),
    'invoice-not-vat-payer': dict(
        items=[dict(title='Konzultácia', quantity=D('2'), unit='HOURS', unit_price=D('45.00'), tax_rate=None)],
        supplier_vat_id='',
    ),
    'invoice-reverse-charge': dict(
        items=[dict(title='Stavebné práce', unit_price=D('1000.00'), tax_rate=None, vat_category='AE')],
        vat_exemption_reason='Prenesenie daňovej povinnosti',
    ),
    'invoice-exempt': dict(
        items=[dict(title='Poistenie', unit_price=D('250.00'), tax_rate=None, vat_category='E')],
        vat_exemption_reason='Oslobodené od dane podľa § 37 zákona o DPH',
    ),
    'invoice-prepaid': dict(
        items=[dict(title='Služba', unit_price=D('100.00'))],
        already_paid=D('50.00'),
    ),
}


@pytest.mark.parametrize('name', SCENARIOS)
def test_invoice(name, einvoice_factory):
    scenario = dict(SCENARIOS[name])
    invoice = einvoice_factory(scenario.pop('items'), **scenario)

    xml = PeppolBIS3Builder(invoice).build()

    assert_valid(xml)
    assert_golden(name, xml)


def test_credit_note(einvoice_factory):
    original = einvoice_factory([dict(title='Služba', unit_price=D('100.00'))])
    credit_note = einvoice_factory(
        [dict(title='Dobropis za službu', unit_price=D('20.00'))],
        type=Invoice.TYPE.CREDIT_NOTE, number='2026-D001', date_issue=date(2026, 10, 5), date_tax_point=date(2026, 10, 5),
    )
    credit_note.related_invoices.add(original)

    xml = PeppolBIS3Builder(credit_note).build()

    assert_valid(xml)
    assert_golden('credit-note', xml)
    document = etree.fromstring(xml)
    assert etree.QName(document).localname == 'CreditNote'
    assert document.findtext('cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID', namespaces=NS) == '2026-001'


def test_credit_note_with_free_text_reference(einvoice_factory):
    credit_note = einvoice_factory(
        [dict(unit_price=D('20.00'))], type=Invoice.TYPE.CREDIT_NOTE, related_document='2025-117',
    )

    xml = PeppolBIS3Builder(credit_note).build()

    assert_valid(xml)
    assert b'<cbc:ID>2025-117</cbc:ID>' in xml


def test_embedded_pdf(einvoice_factory):
    invoice = einvoice_factory([dict(unit_price=D('100.00'))])
    pdf = b'%PDF-1.4 fake'

    xml = get_builder(invoice, attachments=[Attachment('2026-001.pdf', pdf, description='Faktúra')]).build()

    assert_valid(xml)
    embedded = etree.fromstring(xml).find('cac:AdditionalDocumentReference/cac:Attachment/cbc:EmbeddedDocumentBinaryObject', NS)
    assert embedded.get('mimeCode') == 'application/pdf'
    assert embedded.get('filename') == '2026-001.pdf'
    assert base64.b64decode(embedded.text) == pdf


def test_build_is_deterministic(einvoice_factory):
    invoice = einvoice_factory([dict(unit_price=D('10.00')), dict(unit_price=D('5.55'), tax_rate=D('5'))])

    assert PeppolBIS3Builder(invoice).build() == PeppolBIS3Builder(invoice).build()


def test_tax_point_date_is_left_out_when_equal_to_issue_date(einvoice_factory):
    invoice = einvoice_factory([dict(unit_price=D('10.00'))], date_tax_point=date(2026, 10, 1))

    assert b'TaxPointDate' not in PeppolBIS3Builder(invoice).build()


def test_buyer_reference(einvoice_factory):
    invoice = einvoice_factory([dict(unit_price=D('10.00'))], buyer_reference='PO-778')
    document = etree.fromstring(PeppolBIS3Builder(invoice).build())

    assert document.findtext('cbc:BuyerReference', namespaces=NS) == 'PO-778'


def test_unit_codes_are_configurable(einvoice_factory, settings):
    settings.INVOICING_EINVOICING = {'UNIT_CODES': {'PIECES': 'C62'}}
    invoice = einvoice_factory([dict(unit_price=D('10.00'))])
    document = etree.fromstring(PeppolBIS3Builder(invoice).build())

    assert document.find('cac:InvoiceLine/cbc:InvoicedQuantity', NS).get('unitCode') == 'C62'
