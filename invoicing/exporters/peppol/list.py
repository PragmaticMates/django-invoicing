from invoicing.einvoicing.ubl import get_builder
from invoicing.einvoicing.validation import preflight, validate
from invoicing.models import Invoice

from outputs.mixins import ExporterMixin
from outputs.models import Export
from pragmatic.utils import compress


class InvoicePeppolXmlListExporter(ExporterMixin):
    """
    The selected invoices as Peppol BIS Billing 3.0 UBL documents: exactly what
    would be sent as e-invoices, but sent nowhere. One XML per invoice, in a
    zip -- or, when the export comes down to a single file, that file alone.

    An invoice that fails the checks (preflight, UBL schema, Peppol rules) is
    left out, and why goes into ``_errors.txt``; warnings do not keep an
    invoice out.
    """
    export_format = Export.FORMAT_XML
    export_context = Export.CONTEXT_LIST
    model = Invoice
    queryset = Invoice.objects.all()
    filename = 'invoices_peppol.zip'
    errors_filename = '_errors.txt'

    def export(self):
        self.write_data(self.output)

    def get_attachments(self, invoice):
        """Documents to embed into the invoice's XML, e.g. its PDF rendering (see ubl.Attachment)."""
        return ()

    def get_filename_for(self, invoice):
        return f'{invoice.number}.xml'

    def build(self, invoice):
        """(xml, ValidationReport); xml is None when the invoice cannot be exported."""
        report = preflight(invoice)
        if not report.is_valid:
            return None, report

        xml = get_builder(invoice, attachments=self.get_attachments(invoice)).build()
        report.extend(validate(xml))
        return (xml if report.is_valid else None), report

    def write_data(self, output):
        export_files, errors = [], []

        for invoice in self.get_queryset():
            xml, report = self.build(invoice)

            if xml is None:
                errors.append(f'{invoice.number or invoice.pk}:\n' + '\n'.join(
                    f'  [{finding.rule_id}] {finding.message}' for finding in report.errors))
                continue

            export_files.append({'name': self.get_filename_for(invoice), 'content': xml})

        if errors:
            export_files.append({'name': self.errors_filename, 'content': '\n\n'.join(errors).encode('utf-8')})

        if len(export_files) == 1:
            # a single invoice: its XML (or why it failed) as is, not zipped
            self.filename = export_files[0]['name']
            output.write(export_files[0]['content'])
        else:
            output.write(compress(export_files).read())
