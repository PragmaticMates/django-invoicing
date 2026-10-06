import pytest

from invoicing.models import Invoice


SUPPLIER = {
    'name': 'Supplier s.r.o.', 'country_code': 'SK', 'tax_id': '2020123456',
    'endpoint_scheme': '0245', 'endpoint_id': '2020123456',
    'bank': {'iban': 'SK0000000000000000000028'},
}
CUSTOMER = {
    'name': 'Customer a.s.', 'country_code': 'SK', 'tax_id': '2021654321',
    'endpoint_scheme': '0245', 'endpoint_id': '2021654321',
}


def test_set_data_copies_endpoints():
    invoice = Invoice()
    invoice.set_supplier_data(SUPPLIER)
    invoice.set_customer_data(CUSTOMER)

    assert (invoice.supplier_endpoint_scheme, invoice.supplier_endpoint_id) == ('0245', '2020123456')
    assert (invoice.customer_endpoint_scheme, invoice.customer_endpoint_id) == ('0245', '2021654321')


def test_set_data_without_endpoints_keeps_working():
    invoice = Invoice()
    invoice.set_supplier_data({key: value for key, value in SUPPLIER.items() if not key.startswith('endpoint')})
    invoice.set_customer_data({'name': 'Customer', 'country_code': 'SK'})

    assert invoice.supplier_endpoint_id == ''
    assert invoice.customer_endpoint_scheme == ''


@pytest.mark.django_db
def test_new_fields_default_to_blank(invoice_factory, item_factory):
    invoice = invoice_factory()
    item = item_factory(invoice)
    invoice.refresh_from_db()

    assert invoice.buyer_reference == invoice.vat_exemption_reason == invoice.vat_exemption_reason_code == ''
    assert item.vat_category == ''
