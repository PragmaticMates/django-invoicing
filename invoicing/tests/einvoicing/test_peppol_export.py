import io
import zipfile
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from lxml import etree

from invoicing.einvoicing.ubl import Attachment
from invoicing.einvoicing.validation import validate
from invoicing.exporters.peppol import list as peppol_list
from invoicing.exporters.peppol.list import InvoicePeppolXmlListExporter
from invoicing.exporters.peppol.managers import PeppolManager
from invoicing.models import Invoice


D = Decimal
pytestmark = pytest.mark.django_db


def real_compress(files):
    """pragmatic.utils.compress, which the test conftest stubs out."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode='w') as archive:
        for file in files:
            archive.writestr(file['name'], file['content'])
    buffer.seek(0)
    return buffer


def exporter_for(user, invoices, exporter_class=InvoicePeppolXmlListExporter):
    return exporter_class(user=user, recipients=[user], queryset=Invoice.objects.filter(pk__in=[i.pk for i in invoices]))


def run(exporter):
    output = io.BytesIO()
    with patch.object(peppol_list, 'compress', real_compress):
        exporter.write_data(output)
    return zipfile.ZipFile(io.BytesIO(output.getvalue()))


def test_exports_valid_invoices_and_explains_the_rest(einvoice_factory, admin_user):
    good = einvoice_factory([dict(unit_price=D('100.00'))])
    credit_note = einvoice_factory([dict(unit_price=D('10.00'))], number='2026-D01', type=Invoice.TYPE.CREDIT_NOTE,
                                   related_document='2026-001')
    no_address = einvoice_factory([dict(unit_price=D('10.00'))], number='2026-002', customer_endpoint_id='')

    archive = run(exporter_for(admin_user, [good, credit_note, no_address]))

    assert sorted(archive.namelist()) == ['2026-001.xml', '2026-D01.xml', '_errors.txt']
    for name in ('2026-001.xml', '2026-D01.xml'):
        assert validate(archive.read(name)).is_valid
    assert etree.QName(etree.fromstring(archive.read('2026-D01.xml'))).localname == 'CreditNote'
    errors = archive.read('_errors.txt').decode()
    assert '2026-002' in errors and 'PREFLIGHT-CUSTOMER-ENDPOINT' in errors


def test_no_errors_file_when_everything_is_valid(einvoice_factory, admin_user):
    invoice = einvoice_factory([dict(unit_price=D('100.00'))])

    archive = run(exporter_for(admin_user, [invoice]))

    assert archive.namelist() == ['2026-001.xml']


def test_attachments_hook(einvoice_factory, admin_user):
    class WithPdf(InvoicePeppolXmlListExporter):
        def get_attachments(self, invoice):
            return [Attachment(f'{invoice.number}.pdf', b'%PDF-1.4')]

    invoice = einvoice_factory([dict(unit_price=D('100.00'))])

    archive = run(exporter_for(admin_user, [invoice], WithPdf))

    assert b'EmbeddedDocumentBinaryObject' in archive.read('2026-001.xml')


def test_manager_action(einvoice_factory, admin_user):
    invoice = einvoice_factory([dict(unit_price=D('100.00'))])
    request = RequestFactory().post('/')
    request.user = admin_user

    with patch.object(PeppolManager, '_execute_export') as execute:
        PeppolManager().export_list_peppol(request, queryset=Invoice.objects.filter(pk=invoice.pk))

    assert execute.call_args.args[1] is InvoicePeppolXmlListExporter
    assert PeppolManager.required_origin == Invoice.ORIGIN.ISSUED
    assert str(PeppolManager.export_list_peppol.short_description) == 'Export to Peppol UBL (XML)'
