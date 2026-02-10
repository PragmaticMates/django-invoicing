from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.pdf.detail import InvoicePdfDetailExporter


class PdfManager(InvoiceManagerMixin):
    exporter_class = InvoicePdfDetailExporter

    def export_detail_pdf(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_detail_pdf.short_description = _('Export to PDF')
