from django.contrib import messages
from django.contrib.admin import helpers
from django.core.exceptions import ImproperlyConfigured
from django.template.response import TemplateResponse
from django.utils.translation import gettext, gettext_lazy as _

from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.models import Invoice


class EInvoicingManager(InvoiceManagerMixin):
    """
    E-invoicing actions in the invoice admin, through each invoice's provider
    (INVOICING_EINVOICING['PROVIDER_RESOLVER']):

    * "Check e-invoice": every check, as services.check() does -- the local
      ones and the provider's own (with whether the customer can receive it);
      a page with the findings per invoice. Stores and sends nothing.
    * "Send as e-invoice (API)": as services.send() does, after a confirmation
      page listing what will be sent and what will not, and why -- a sent
      e-invoice cannot be taken back.

    Needs 'invoicing.einvoicing' in INSTALLED_APPS.
    """
    required_origin = Invoice.ORIGIN.ISSUED
    confirmation_template = 'admin/invoicing/einvoicing/send_confirmation.html'
    check_template = 'admin/invoicing/einvoicing/check_results.html'

    def export_check(self, request, queryset=None, exporter_params=None):
        from invoicing.einvoicing import services
        from invoicing.einvoicing.providers import ProviderError, get_provider

        rows = []
        for invoice in queryset.order_by('date_issue', 'number'):
            row = {'invoice': invoice, 'provider': '', 'valid': False, 'errors': [], 'warnings': [], 'problem': None}
            try:
                provider = get_provider(invoice)
            except ImproperlyConfigured:
                provider = None

            try:
                xml, report = services.check(invoice, provider=provider) if provider else services.check_locally(invoice)
            except ProviderError as error:
                row['problem'] = gettext('The provider could not check it: %(error)s') % {'error': error.message}
            else:
                row.update(provider=provider.name if provider else '', valid=xml is not None,
                           errors=report.errors, warnings=report.warnings)
                if provider is None:
                    row['problem'] = gettext('No e-invoicing provider is configured: checked locally only.')
            rows.append(row)

        return TemplateResponse(request, self.check_template, {
            'title': gettext('E-invoice check'),
            'opts': Invoice._meta,
            'rows': rows,
            'valid_count': sum(1 for row in rows if row['valid']),
        })

    export_check.short_description = _('Check e-invoice')

    def export_via_api(self, request, queryset=None, exporter_params=None):
        if request.POST.get('confirm') == 'yes':
            return self.send(request, queryset)
        return self.confirmation(request, queryset)

    export_via_api.short_description = _('Send as e-invoice (API)')

    def assess(self, invoice):
        """(provider name, None) when the invoice can be sent, else (provider name or '', reason)."""
        from invoicing.einvoicing import services
        from invoicing.einvoicing.providers import get_provider
        from invoicing.einvoicing.validation import preflight

        if invoice.origin != Invoice.ORIGIN.ISSUED:
            return '', gettext('Only issued invoices can be sent.')

        live = services.live_transmission(invoice)
        if live is not None:
            return live.provider, gettext('Already sent as an e-invoice (%(status)s).') % {'status': live.get_status_display()}

        try:
            provider = get_provider(invoice)
        except ImproperlyConfigured:
            provider = None
        if provider is None:
            return '', gettext('No e-invoicing provider is configured for this invoice.')

        reason = services.send_blocked_reason(invoice, provider)
        if reason:
            return provider.name, reason

        report = preflight(invoice)
        if not report.is_valid:
            return provider.name, '; '.join(finding.message for finding in report.errors)

        return provider.name, None

    def confirmation(self, request, queryset):
        rows = []
        for invoice in queryset.order_by('date_issue', 'number'):
            provider, reason = self.assess(invoice)
            rows.append({'invoice': invoice, 'provider': provider, 'reason': reason})

        opts = Invoice._meta
        return TemplateResponse(request, self.confirmation_template, {
            'title': gettext('Send as e-invoice'),
            'opts': opts,
            'rows': rows,
            'sendable': [row for row in rows if row['reason'] is None],
            'action': request.POST.get('action', ''),
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'selected': [str(invoice.pk) for invoice in queryset],
        })

    def send(self, request, queryset):
        from invoicing.einvoicing import services
        from invoicing.einvoicing.providers import ProviderError

        sent = 0
        for invoice in queryset:
            provider, reason = self.assess(invoice)
            if reason:
                messages.warning(request, f'{invoice}: {reason}')
                continue

            try:
                services.send(invoice)
            except services.EInvoiceValidationError as error:
                messages.error(request, f'{invoice}: ' + '; '.join(finding.message for finding in error.report.errors))
            except (services.SendNotAllowed, services.ResubmissionNotAllowed) as error:
                messages.warning(request, f'{invoice}: {error}')
            except ProviderError as error:
                messages.error(request, f'{invoice}: {error.message}')
            else:
                sent += 1

        if sent:
            messages.success(request, gettext('%(count)d invoice(s) queued for sending as e-invoices.') % {'count': sent})
