import logging

from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from invoicing import settings as invoicing_settings

logger = logging.getLogger(__name__)


class InvoiceManagerMixin(object):
    required_origin = None

    @property
    def manager_settings(self):
        """Get the settings for this manager from INVOICING_MANAGERS config."""
        key = f"{self.__module__}.{self.__class__.__name__}"
        return invoicing_settings.INVOICING_MANAGERS.get(key, {})

    def _is_export_qs_valid(self, request, exporter):
        """
        Validate queryset to be exported.

        - Ensures there is something to export.
        - Ensures that all exported objects share a single origin.
        """
        queryset = exporter.get_queryset()

        # 1) Check if there is anything to export
        if queryset is None or not queryset.exists():
            messages.warning(request, _("%s: There is no invoice selected to export." % exporter.__class__.__name__))
            return False

        # 2) Check origin in one go: single DB hit for distinct origins, then validate
        #    (assumes an 'origin' field on the model). order_by() clears default ordering
        #    so distinct() applies only to origin (otherwise we get one row per invoice).
        origins = list(queryset.values_list("origin", flat=True).order_by().distinct())
        if len(origins) != 1:
            messages.warning(request, _("%s: All exported invoices must have the same origin." % exporter.__class__.__name__))
            return False

        # 3) If manager requires a specific origin, ensure the queryset's (single) origin matches
        if self.required_origin is not None and origins[0] != self.required_origin:
            messages.warning(request, _("%s: All exported invoices must have the expected origin." % exporter.__class__.__name__))
            return False

        return True

    def _execute_export(self, request, exporter_class, exporter_params, queryset):
        """
        Common export logic for email-based exports.

        Args:
            request: The HTTP request object
            exporter_class: The exporter class to use
            exporter_params: The params of the exporter
            queryset: The queryset of invoices to export
        """
        if exporter_params is None:
            exporter_params = {"user": request.user, "recipients": [request.user], "params": {}}

        exporter = exporter_class(**exporter_params)

        # set queryset if provided explicitly
        if queryset is not None and queryset.exists():
            exporter.items = queryset

        if not self._is_export_qs_valid(request, exporter):
            return

        qs_count = exporter.get_queryset().count()
        logger.info(
            f"User {request.user} (ID: {request.user.id}) executing export with {qs_count} invoice(s)",
            extra={
                'user_id': request.user.id,
                'exporter_class': exporter_class,
                'exporter_params': exporter_params
            }
        )

        from outputs.usecases import execute_export
        from django.utils import translation
        execute_export(exporter, language=translation.get_language())
        messages.info(request, _('Export of %d invoice(s) queued and will be sent to email') % qs_count)
