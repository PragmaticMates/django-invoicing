"""
The package without django-outputs: only the exporters need it.

Run with ``pytest --ds=invoicing.tests.test_settings_without_outputs``; with the
default test settings, where outputs is installed, these tests are skipped.
"""
import pytest
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.core.management import call_command
from django.urls import reverse

from invoicing.models import Invoice


pytestmark = [
    pytest.mark.skipif(apps.is_installed('outputs'), reason='needs invoicing.tests.test_settings_without_outputs'),
    pytest.mark.urls('invoicing.tests.einvoicing.admin_urls'),
]


def test_the_system_checks_pass():
    call_command('check')


def test_an_invoice_has_no_export_items():
    with pytest.raises(FieldDoesNotExist):
        Invoice._meta.get_field('export_items')


@pytest.mark.django_db
def test_the_admin_lists_and_shows_invoices(admin_client, sample_invoice):
    assert admin_client.get(reverse('admin:invoicing_invoice_changelist')).status_code == 200
    assert admin_client.get(reverse('admin:invoicing_invoice_change', args=[sample_invoice.pk])).status_code == 200
