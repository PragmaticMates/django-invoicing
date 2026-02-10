import logging

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.mrp.v1.list import (
    InvoiceFakvypolXmlMrpExporter,
    InvoiceFakvyXmlMrpExporter,
    InvoiceFvAdresXmlMrpExporter,
    InvoiceXmlMrpListExporter,
)
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


class MrpV1Manager(InvoiceManagerMixin):
    exporter_class = InvoiceXmlMrpListExporter
    exporter_subclasses = [InvoiceFakvyXmlMrpExporter, InvoiceFakvypolXmlMrpExporter, InvoiceFvAdresXmlMrpExporter]
    required_origin = Invoice.ORIGIN.ISSUED

    def export_list_mrp(self, request, queryset=None, exporter_params=None):
        """Legacy MRP XML export (v1) - returns direct response instead of email."""

        if exporter_params is None:
            exporter_params = {"user": request.user, "recipients": [request.user], "params": {}}

        if self.exporter_class is None:
            raise ImproperlyConfigured(_("Undefined exporter class for MRP v1 export."))

        exporter = self.exporter_class(**exporter_params)

        if queryset is not None and queryset.exists():
            exporter.items = queryset

        if not self._is_export_qs_valid(request, exporter):
            return

        export = exporter.save_export()
        logger.info(f"Export created: export_id={export.id}, total_items={export.total}")

        exporter_subclass_paths = None
        if self.exporter_subclasses:
            exporter_subclass_paths = [
                f"{cls.__module__}.{cls.__qualname__}" for cls in self.exporter_subclasses
            ]
        from invoicing.exporters.mrp.v1.tasks import mail_exported_invoices_mrp_v1
        mail_exported_invoices_mrp_v1.delay(export.id, exporter_subclass_paths=exporter_subclass_paths)

    export_list_mrp.short_description = _('Export to MRP v1 (XML)')
