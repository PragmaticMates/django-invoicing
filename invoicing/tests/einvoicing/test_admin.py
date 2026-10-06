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
