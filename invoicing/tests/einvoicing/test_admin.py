from decimal import Decimal

import pytest
from django.urls import reverse

from invoicing.einvoicing import services
from invoicing.tests.einvoicing.test_services import FakeProvider, resolve


pytestmark = [pytest.mark.django_db, pytest.mark.urls('invoicing.tests.einvoicing.admin_urls')]


@pytest.fixture
def transmission(einvoice_factory, settings):
    settings.INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'invoicing.tests.einvoicing.test_services.resolve'}
    resolve.provider = FakeProvider()
    invoice = einvoice_factory([dict(unit_price=Decimal('100.00'))])
    return services.submit(services.prepare(invoice))


def test_change_view_and_xml_download(admin_client, transmission):
    response = admin_client.get(reverse('admin:invoicing_einvoicing_einvoicetransmission_change', args=[transmission.pk]))
    assert response.status_code == 200
    assert transmission.xml_sha256 in response.content.decode()

    response = admin_client.get(reverse('admin:invoicing_einvoicing_transmission_xml', args=[transmission.pk]))
    assert response.status_code == 200
    assert response.content == transmission.xml_bytes
    assert response['Content-Disposition'] == f'attachment; filename="2026-001-{transmission.pk}.xml"'


def test_changelist(admin_client, transmission):
    response = admin_client.get(reverse('admin:invoicing_einvoicing_einvoicetransmission_changelist'))
    assert response.status_code == 200


def test_transmissions_are_read_only(admin_client, transmission):
    url = reverse('admin:invoicing_einvoicing_einvoicetransmission_delete', args=[transmission.pk])
    assert admin_client.post(url, {'post': 'yes'}).status_code == 403


def test_resolve_conflict_action(admin_client, einvoice_factory, settings):
    from invoicing.einvoicing.models import EInvoiceTransmission
    from invoicing.einvoicing.providers import ProviderError
    settings.INVOICING_EINVOICING = {'PROVIDER_RESOLVER': 'invoicing.tests.einvoicing.test_services.resolve'}
    resolve.provider = FakeProvider(outcomes=[ProviderError('duplicate', code='SAPI-PERM-002', http_status=409)])
    conflict = services.submit(services.prepare(einvoice_factory([dict(unit_price=Decimal('10'))])))
    other = services.prepare(einvoice_factory([dict(unit_price=Decimal('10'))], number='2026-002'))

    response = admin_client.post(reverse('admin:invoicing_einvoicing_einvoicetransmission_changelist'), {
        'action': 'resolve_conflict_as_refused', '_selected_action': [conflict.pk, other.pk],
    }, follow=True)

    assert response.status_code == 200
    conflict.refresh_from_db(); other.refresh_from_db()
    assert (conflict.status, other.status) == ('REFUSED', 'PREPARED')


def invoice_admin_page(admin_client, invoice):
    return admin_client.get(reverse('admin:invoicing_invoice_change', args=[invoice.pk]))


def test_invoice_admin_shows_e_invoicing_fields(admin_client, einvoice_factory):
    invoice = einvoice_factory([dict(unit_price=Decimal('10'))], buyer_reference='PO-1')

    response = invoice_admin_page(admin_client, invoice)

    form = response.context['adminform'].form
    for name in ('buyer_reference', 'supplier_endpoint_scheme', 'supplier_endpoint_id', 'customer_endpoint_scheme',
                 'customer_endpoint_id', 'vat_exemption_reason', 'vat_exemption_reason_code', 'customer_email'):
        assert name in form.fields, name
    assert 'vat_category' in response.context['inline_admin_formsets'][0].formset.forms[0].fields


def test_sent_invoice_is_read_only_in_admin(admin_client, transmission):
    invoice = transmission.invoice

    response = invoice_admin_page(admin_client, invoice)

    form = response.context['adminform'].form
    assert set(form.fields) == {'status', 'date_paid', 'already_paid'}  # only its life after issuing
    items, transmissions = response.context['inline_admin_formsets']
    assert not items.has_add_permission and not items.has_change_permission and not items.has_delete_permission
    assert str(transmission.pk) in response.content.decode()
    assert transmissions.formset.model.__name__ == 'EInvoiceTransmission'


def test_status_of_a_sent_invoice_can_still_change(admin_client, transmission):
    invoice = transmission.invoice
    url = reverse('admin:invoicing_invoice_change', args=[invoice.pk])
    page = invoice_admin_page(admin_client, invoice)
    data = {name: field.value() for name, field in [(bf.name, bf) for bf in page.context['adminform'].form]}
    data.update(status='PAID', date_paid='', already_paid='0')
    for formset in page.context['inline_admin_formsets']:
        management = formset.formset.management_form
        data.update({f'{management.prefix}-{key}': value for key, value in management.initial.items()})
        data[f'{management.prefix}-TOTAL_FORMS'] = management.initial['INITIAL_FORMS']

    response = admin_client.post(url, {k: v for k, v in data.items() if v is not None})

    assert response.status_code == 302, response.context['adminform'].form.errors if response.context else ''
    invoice.refresh_from_db()
    assert invoice.status == 'PAID'
    assert invoice.number == '2026-001'
