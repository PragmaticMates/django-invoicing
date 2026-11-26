from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from invoicing.einvoicing.validation import preflight, schematron, sk, validate, xsd
from invoicing.models import Invoice


D = Decimal
EXAMPLES = Path(__file__).parent / 'peppol-examples'  # from BIS Billing 3.0.21, BIS-Billing3-Examples.zip


def rule_ids(report):
    return {finding.rule_id for finding in report.errors}


class TestArtefacts:
    @pytest.mark.parametrize('example', ['base-example.xml', 'vat-category-O.xml'])
    def test_official_examples_pass(self, example):
        xml = (EXAMPLES / example).read_bytes()

        assert xsd.validate(xml).is_valid
        assert schematron.validate(xml).is_valid

    def test_cen_rules_run(self):
        xml = (EXAMPLES / 'base-example.xml').read_bytes()
        broken = xml.replace(b'<cbc:PayableAmount currencyID="EUR">1656.25', b'<cbc:PayableAmount currencyID="EUR">1.00')

        assert 'BR-CO-16' in rule_ids(schematron.validate(broken))

    def test_peppol_rules_run(self):
        xml = (EXAMPLES / 'base-example.xml').read_bytes()
        broken = xml.replace(b'billing:3.0</cbc:CustomizationID>', b'billing:3.0::2.1</cbc:CustomizationID>')

        assert 'PEPPOL-EN16931-R004' in rule_ids(schematron.validate(broken))

    def test_xsd_rejects_unknown_elements(self):
        xml = (EXAMPLES / 'base-example.xml').read_bytes()
        broken = xml.replace(b'<cbc:BuyerReference>', b'<cbc:Unknown/><cbc:BuyerReference>')

        report = validate(broken)
        assert rule_ids(report) == {'XSD'}

    def test_not_xml(self):
        assert rule_ids(validate(b'<Invoice')) == {'XML'}

    def test_not_ubl(self):
        assert rule_ids(validate(b'<Order/>')) == {'UBL'}

    def test_schematron_can_be_switched_off(self, settings):
        settings.INVOICING_EINVOICING = {'SCHEMATRON': False}
        xml = (EXAMPLES / 'base-example.xml').read_bytes()
        broken = xml.replace(b'<cbc:PayableAmount currencyID="EUR">1656.25', b'<cbc:PayableAmount currencyID="EUR">1.00')

        assert validate(broken).is_valid


@pytest.mark.django_db
class TestSlovakRules:
    def test_sk_party_needs_scheme_0245(self, einvoice_factory):
        from invoicing.einvoicing.ubl import PeppolBIS3Builder
        invoice = einvoice_factory([dict(unit_price=D('10'))], customer_endpoint_scheme='9950', customer_endpoint_id='SK2021654321')

        report = sk.validate(PeppolBIS3Builder(invoice).build())

        assert rule_ids(report) == {'SK-LOCAL-BUYER-01'}

    def test_sk_address_has_to_be_complete(self, einvoice_factory):
        from invoicing.einvoicing.ubl import PeppolBIS3Builder
        invoice = einvoice_factory([dict(unit_price=D('10'))], supplier_zip='', supplier_street='')

        report = sk.validate(PeppolBIS3Builder(invoice).build())

        assert rule_ids(report) == {'SK-LOCAL-SELLER-02'}
        assert 'street, postal code' in report.errors[0].message

    def test_missing_legal_form_is_a_warning(self, einvoice_factory):
        from invoicing.einvoicing.ubl import PeppolBIS3Builder
        invoice = einvoice_factory([dict(unit_price=D('10'))], supplier_additional_info=None)

        report = sk.validate(PeppolBIS3Builder(invoice).build())

        assert report.is_valid
        assert [finding.rule_id for finding in report.warnings] == ['SK-LOCAL-SELLER-04']

    def test_foreign_parties_are_not_checked(self):
        assert sk.validate((EXAMPLES / 'base-example.xml').read_bytes()).findings == []


@pytest.mark.django_db
class TestPreflight:
    def test_ready_invoice(self, einvoice_factory):
        invoice = einvoice_factory([dict(unit_price=D('10'))])

        assert preflight(invoice).findings == []

    @pytest.mark.parametrize('kwargs, rule', [
        (dict(type=Invoice.TYPE.PROFORMA), 'PREFLIGHT-TYPE'),
        (dict(type=Invoice.TYPE.ADVANCE), 'PREFLIGHT-TYPE'),
        (dict(currency='USD'), 'PREFLIGHT-CURRENCY'),
        (dict(credit=D('5')), 'PREFLIGHT-CREDIT'),
        (dict(customer_endpoint_id=''), 'PREFLIGHT-CUSTOMER-ENDPOINT'),
        (dict(supplier_endpoint_id='123'), 'PREFLIGHT-SUPPLIER-ENDPOINT'),
        (dict(type=Invoice.TYPE.CREDIT_NOTE), 'PREFLIGHT-CREDIT-NOTE-REFERENCE'),
    ])
    def test_refusals(self, einvoice_factory, kwargs, rule):
        invoice = einvoice_factory([dict(unit_price=D('10'))], **kwargs)

        assert rule in rule_ids(preflight(invoice))

    def test_customer_country_restriction(self, einvoice_factory, settings):
        settings.INVOICING_EINVOICING = {'ALLOWED_CUSTOMER_COUNTRIES': ('SK',)}
        invoice = einvoice_factory([dict(unit_price=D('10'))], customer_country='CZ')

        assert rule_ids(preflight(invoice)) == {'PREFLIGHT-COUNTRY'}

    def test_no_items(self, einvoice_factory):
        assert rule_ids(preflight(einvoice_factory([]))) == {'PREFLIGHT-ITEMS'}

    def test_ambiguous_vat_category(self, einvoice_factory):
        invoice = einvoice_factory([dict(unit_price=D('10'), tax_rate=None)])

        assert rule_ids(preflight(invoice)) == {'PREFLIGHT-VAT-CATEGORY'}

    def test_not_subject_to_vat_cannot_be_mixed(self, einvoice_factory):
        invoice = einvoice_factory([
            dict(unit_price=D('10')),
            dict(unit_price=D('10'), tax_rate=None, vat_category='O'),
        ], vat_exemption_reason_code='VATEX-EU-O')

        assert 'PREFLIGHT-VAT-CATEGORY' in rule_ids(preflight(invoice))

    def test_exempt_needs_reason(self, einvoice_factory):
        invoice = einvoice_factory([dict(unit_price=D('10'), tax_rate=None, vat_category='E')])

        assert rule_ids(preflight(invoice)) == {'PREFLIGHT-EXEMPTION-REASON'}

    def test_one_reason_for_several_categories(self, einvoice_factory):
        invoice = einvoice_factory([
            dict(unit_price=D('10'), tax_rate=None, vat_category='E'),
            dict(unit_price=D('10'), tax_rate=None, vat_category='AE'),
        ], vat_exemption_reason='§ 37')

        assert rule_ids(preflight(invoice)) == {'PREFLIGHT-EXEMPTION-REASON'}

    def test_totals_have_to_match(self, einvoice_factory):
        invoice = einvoice_factory([dict(quantity=D('0.5'), unit_price=D('0.01'))] * 3)

        assert rule_ids(preflight(invoice)) == {'PREFLIGHT-TOTALS'}

    def test_credit_note_with_reference(self, einvoice_factory):
        invoice = einvoice_factory([dict(unit_price=D('10'))], type=Invoice.TYPE.CREDIT_NOTE,
                                   related_document='2025-117', date_issue=date(2026, 10, 1))

        assert preflight(invoice).is_valid
