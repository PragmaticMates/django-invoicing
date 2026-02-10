from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.xlsx.list import InvoiceXlsxListExporter


class XlsxManager(InvoiceManagerMixin):
    exporter_class = InvoiceXlsxListExporter

    def export_list_xlsx(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_list_xlsx.short_description = _('Export to xlsx')
