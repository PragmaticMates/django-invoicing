"""
Tests for the MRP v2 list exporters (invoicing/exporters/mrp/v2/list.py).
"""
import pytest
from lxml import etree

from invoicing.exporters.mrp.v2.list import (
    IssuedInvoiceMrpListExporter,
    ReceivedInvoiceMrpListExporter,
)
from invoicing.models import Invoice


EXPORTERS = [
    pytest.param(IssuedInvoiceMrpListExporter, Invoice.ORIGIN.ISSUED, id="issued"),
    pytest.param(ReceivedInvoiceMrpListExporter, Invoice.ORIGIN.RECEIVED, id="received"),
]


def build_validated_invoice_element(exporter_class, invoice):
    """Build the <Invoice> element and validate it against the exporter's XSD."""
    exporter = exporter_class(user=None, recipients=[])
    invoice_elem = exporter.get_invoice_element(invoice)

    mrpks_data = etree.Element("MRPKSData", version="2.0")
    container = etree.SubElement(mrpks_data, exporter.get_invoice_root_element())
    container.append(invoice_elem)
    exporter.validate_xml(mrpks_data)

    return invoice_elem


@pytest.mark.exporters
@pytest.mark.django_db
class TestMrpV2InvoiceNote:
    """Invoice.note goes to <Note>; <HeadNote> is only for Vizuální účetní systém."""

    @pytest.mark.parametrize("exporter_class, origin", EXPORTERS)
    def test_note_exported_to_note_element_untruncated(self, exporter_class, origin, invoice_factory, item_factory):
        note = "Payment by bank transfer only.\nPlease quote the variable symbol. " + "x" * 150
        invoice = invoice_factory(origin=origin, note=note)
        item_factory(invoice=invoice)

        invoice_elem = build_validated_invoice_element(exporter_class, invoice)

        assert invoice_elem.find("HeadNote") is None
        assert invoice_elem.findtext("Note") == note

    @pytest.mark.parametrize("exporter_class, origin", EXPORTERS)
    def test_note_forbidden_chars_removed(self, exporter_class, origin, invoice_factory, item_factory):
        invoice = invoice_factory(origin=origin, note="Order #42 | it's\tdone")
        item_factory(invoice=invoice)

        invoice_elem = build_validated_invoice_element(exporter_class, invoice)

        assert invoice_elem.findtext("Note") == "Order 42  itsdone"

    @pytest.mark.parametrize("exporter_class, origin", EXPORTERS)
    @pytest.mark.parametrize("note", ["", "   \n  "])
    def test_blank_note_not_exported(self, exporter_class, origin, note, invoice_factory, item_factory):
        invoice = invoice_factory(origin=origin, note=note)
        item_factory(invoice=invoice)

        invoice_elem = build_validated_invoice_element(exporter_class, invoice)

        assert invoice_elem.find("Note") is None
        assert invoice_elem.find("HeadNote") is None
