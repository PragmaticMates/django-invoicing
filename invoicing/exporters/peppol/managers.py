from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.peppol.list import InvoicePeppolXmlListExporter
from invoicing.models import Invoice


class PeppolManager(InvoiceManagerMixin):
    exporter_class = InvoicePeppolXmlListExporter
    required_origin = Invoice.ORIGIN.ISSUED  # e-invoices are issued, never received ones

    def export_list_peppol(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_list_peppol.short_description = _('Export to Peppol UBL (XML)')
