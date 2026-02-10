import logging

from django.contrib import messages
from django.core.validators import EMPTY_VALUES
from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.mrp.v2.list import IssuedInvoiceMrpListExporter, ReceivedInvoiceMrpListExporter
from invoicing.models import Invoice

logger = logging.getLogger(__name__)


class MrpApiManagerMixin(InvoiceManagerMixin):
    def _execute_api_export(self, request, queryset, exporter_params=None):
        """
        Handle POST request to send invoices to MRP server.

        Args:
            request: Django request object with user attribute
            queryset: QuerySet of Invoice objects to export
            exporter_params: The params of the exporter
        """
        if self.manager_settings.get('API_URL', None) in EMPTY_VALUES:
            raise EnvironmentError(_('Missing invoicing manager API url'), self.__class__.__name__)

        if exporter_params is None:
            exporter_params = {"user": request.user, "recipients": [request.user], "params": {}}

        if "output_type" not in exporter_params:
            from outputs.models import Export
            exporter_params["output_type"] = Export.OUTPUT_TYPE_STREAM

        exporter = self.exporter_class(**exporter_params)

        if queryset is not None and queryset.exists():
            exporter.items = queryset

        if not self._is_export_qs_valid(request, exporter):
            return

        qs_count = exporter.get_queryset().count()
        logger.info(
            f"User {request.user} (ID: {request.user.id}) executing export with {qs_count} invoice(s)",
            extra={
                'user_id': request.user.id,
                'exporter_class': self.exporter_class,
                'exporter_params': exporter_params
            }
        )

        export = exporter.save_export()

        from invoicing.exporters.mrp.v2.tasks import send_invoices_to_mrp
        send_invoices_to_mrp.delay(export.id, self)

        messages.info(request, _('Export of %d invoice(s) queued for MRP API processing') % exporter.get_queryset().count())


class MrpIssuedManager(MrpApiManagerMixin):
    exporter_class = IssuedInvoiceMrpListExporter
    required_origin = Invoice.ORIGIN.ISSUED

    def export_list_issued_mrp(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_list_issued_mrp.short_description = _('Export issued to MRP v2 (XML)')

    def export_via_api(self, request, queryset=None, exporter_params=None):
        self._execute_api_export(request, queryset, exporter_params)

    export_via_api.short_description = _('Export issued to MRP (API)')


class MrpReceivedManager(MrpApiManagerMixin):
    exporter_class = ReceivedInvoiceMrpListExporter
    required_origin = Invoice.ORIGIN.RECEIVED

    def export_list_received_mrp(self, request, queryset=None, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_list_received_mrp.short_description = _('Export received to MRP v2 (XML)')

    def export_via_api(self, request, queryset=None, exporter_params=None):
        self._execute_api_export(request, queryset, exporter_params)

    export_via_api.short_description = _('Export received to MRP (API)')
