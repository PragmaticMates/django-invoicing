from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from invoicing.einvoicing.models import EInvoiceTransmission, EInvoiceTransmissionEvent


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EventInline(ReadOnlyMixin, admin.TabularInline):
    model = EInvoiceTransmissionEvent
    extra = 0
    fields = ('created', 'kind', 'status', 'http_status', 'provider_code', 'correlation_id', 'message')
    readonly_fields = fields


@admin.register(EInvoiceTransmission)
class EInvoiceTransmissionAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ('invoice', 'receiver_id', 'status', 'provider', 'environment', 'created', 'submitted_at', 'delivered_at')
    list_filter = ('status', 'provider', 'environment')
    search_fields = ('invoice__number', 'receiver_id', 'provider_document_id', 'document_uuid')
    readonly_fields = [field.name for field in EInvoiceTransmission._meta.fields] + ['xml_download']
    exclude = ('xml',)
    inlines = [EventInline]

    def get_urls(self):
        return [
            path('<int:pk>/xml/', self.admin_site.admin_view(self.download_xml), name='invoicing_einvoicing_transmission_xml'),
        ] + super().get_urls()

    def download_xml(self, request, pk):
        if not self.has_view_permission(request):
            return HttpResponse(status=403)

        transmission = get_object_or_404(EInvoiceTransmission, pk=pk)
        response = HttpResponse(transmission.xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{transmission.invoice.number}-{transmission.pk}.xml"'
        return response

    @admin.display(description=_('XML'))
    def xml_download(self, obj):
        url = reverse('admin:invoicing_einvoicing_transmission_xml', args=[obj.pk])
        return format_html('<a href="{}">{}</a> (SHA-256 {})', url, _('Download transmitted XML'), obj.xml_sha256)
