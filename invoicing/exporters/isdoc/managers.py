from django.utils.translation import gettext_lazy as _

from invoicing.exporters.isdoc.list import InvoiceISDOCXmlListExporter
from invoicing.exporters.mixins import InvoiceManagerMixin


class IsdocManager(InvoiceManagerMixin):
    exporter_class = InvoiceISDOCXmlListExporter

    def export_list_isdoc(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_list_isdoc.short_description = _('Export to ISDOC (XML)')
