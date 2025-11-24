from invoicing.models import Invoice
from invoicing.utils import get_invoices_in_pdf

from django.utils.translation import gettext_lazy as _

from outputs.mixins import ExporterMixin
from outputs.models import Export
from pragmatic.utils import compress


class InvoicePdfDetailExporter(ExporterMixin):
    queryset = Invoice.objects.all()
    export_format = Export.FORMAT_PDF
    export_context = Export.CONTEXT_DETAIL
    filename = _('invoices.zip')

    def get_queryset(self):
        return self.queryset

    def export(self):
        self.write_data(self.output)

    def write_data(self, output):
        export_files = get_invoices_in_pdf(self.get_queryset())

        if len(export_files) == 1:
            # directly export 1 PDF file
            file_data = export_files[0]
            self.filename = file_data['name']
            output.write(file_data['content'])
        else:
            # compress all invoices into single archive file
            output.write(compress(export_files).read())
