import uuid
from datetime import date
from decimal import Decimal

import pytest

from invoicing.einvoicing.identifiers import (
    DOCUMENT_TYPE_IDS, IdentifierError, ParticipantId, document_uuid, sk_participant_id,
)
from invoicing.einvoicing.vat import VatCategory, VatCategoryError, category_rate, resolve_category


class TestResolveCategory:
    @pytest.mark.parametrize('tax_rate, has_vat_id, expected', [
        (Decimal('23'), True, 'S'),
        (Decimal('5'), True, 'S'),
        (Decimal('0'), True, 'Z'),
        (None, False, 'O'),
    ])
    def test_inferred(self, tax_rate, has_vat_id, expected):
        assert resolve_category(tax_rate=tax_rate, supplier_has_vat_id=has_vat_id) == expected

    def test_vat_payer_without_rate_is_ambiguous(self):
        with pytest.raises(VatCategoryError):
            resolve_category(tax_rate=None, supplier_has_vat_id=True)

    @pytest.mark.parametrize('explicit, tax_rate', [
        ('AE', None), ('E', None), ('K', Decimal('0')), ('G', None), ('O', None), ('S', Decimal('23')), ('Z', Decimal('0')),
    ])
    def test_explicit(self, explicit, tax_rate):
        assert resolve_category(tax_rate=tax_rate, supplier_has_vat_id=True, explicit=explicit) == explicit

    @pytest.mark.parametrize('explicit, tax_rate', [
        ('S', None), ('S', Decimal('0')), ('AE', Decimal('23')), ('Z', None), ('XX', None),
    ])
    def test_explicit_contradicting_rate(self, explicit, tax_rate):
        with pytest.raises(VatCategoryError):
            resolve_category(tax_rate=tax_rate, supplier_has_vat_id=True, explicit=explicit)

    def test_category_rate(self):
        assert category_rate(VatCategory.STANDARD, Decimal('23')) == Decimal('23')
        assert category_rate(VatCategory.REVERSE_CHARGE, None) == Decimal('0')
        assert category_rate(VatCategory.NOT_SUBJECT, None) is None


class TestIdentifiers:
    def test_document_uuid_matches_fs_example(self):
        # Slovak eFaktúra Solution Architecture v1.2, §9.2.3
        result = document_uuid('0088', '5060012349998', '380', '33445566', date(2026, 1, 13))

        assert result == uuid.UUID('1780de4f-a87c-50cc-9d8a-f982abe36912')

    def test_document_uuid_trims_fields(self):
        assert document_uuid(' 0088', '5060012349998 ', '380', ' 33445566 ', date(2026, 1, 13)) == \
            uuid.UUID('1780de4f-a87c-50cc-9d8a-f982abe36912')

    def test_document_uuid_depends_on_type_code(self):
        args = ('0245', '2020123456')
        assert document_uuid(*args, '380', '2026-001', date(2026, 1, 1)) != \
            document_uuid(*args, '381', '2026-001', date(2026, 1, 1))

    def test_sk_participant_id(self):
        assert str(sk_participant_id('2020 123 456')) == '0245:2020123456'

    @pytest.mark.parametrize('tax_id', ['', '123', '20201234567', 'SK2020123456'])
    def test_sk_participant_id_needs_ten_digits(self, tax_id):
        with pytest.raises(IdentifierError):
            sk_participant_id(tax_id)

    def test_parse(self):
        assert ParticipantId.parse('9915:abc-1') == ParticipantId('9915', 'abc-1')
        with pytest.raises(IdentifierError):
            ParticipantId.parse('no-scheme')

    def test_document_type_ids(self):
        assert DOCUMENT_TYPE_IDS['380'].startswith('urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##')
        assert DOCUMENT_TYPE_IDS['381'].endswith('billing:3.0::2.1')
