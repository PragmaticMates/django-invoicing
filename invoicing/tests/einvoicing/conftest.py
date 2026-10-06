from datetime import date
from decimal import Decimal

import pytest


SUPPLIER = dict(
    number='2026-001',
    date_issue=date(2026, 10, 1),
    date_tax_point=date(2026, 9, 30),
    date_due=date(2026, 10, 15),
    note='',
    supplier_name='Dodávateľ s.r.o.',
    supplier_street='Hlavná 1',
    supplier_city='Bratislava',
    supplier_zip='811 01',
    supplier_registration_id='12345678',
    supplier_tax_id='2020123456',
    supplier_vat_id='SK2020123456',
    supplier_endpoint_scheme='0245',
    supplier_endpoint_id='2020123456',
    supplier_additional_info={'register': 'Obchodný register Mestského súdu Bratislava III, oddiel Sro, vložka 1/B'},
    issuer_name='Ján Novák',
    issuer_email='jan@dodavatel.sk',
    bank_iban='SK3112000000198742637541',
    bank_swift_bic='TATRSKBX',
    variable_symbol=2026001,
)

CUSTOMER = dict(
    customer_name='Odberateľ a.s.',
    customer_street='Dlhá 22',
    customer_city='Košice',
    customer_zip='040 01',
    customer_registration_id='87654321',
    customer_tax_id='2021654321',
    customer_vat_id='SK2021654321',
    customer_endpoint_scheme='0245',
    customer_endpoint_id='2021654321',
)


@pytest.fixture
def einvoice_factory(invoice_factory, item_factory):
    """An invoice ready to be e-invoiced, with items given as dicts; totals refreshed."""
    def _create(items, **kwargs):
        invoice = invoice_factory(**{**SUPPLIER, **CUSTOMER, **kwargs})
        for item in items:
            item_factory(invoice, **{'quantity': Decimal('1'), 'tax_rate': Decimal('23'), **item})
        invoice.refresh_from_db()
        return invoice
    return _create
