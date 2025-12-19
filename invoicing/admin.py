from django.contrib import admin, messages
from django.db.models import F, DecimalField
from django.db.models.functions import Coalesce
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from invoicing.exporters.mrp.v1.tasks import mail_exported_invoices_mrp_v1
from invoicing.exporters.tasks import mail_exported_invoices
from invoicing.managers import get_accounting_software_manager
from invoicing.models import Invoice, Item


class ItemInline(admin.TabularInline):
    fieldsets = (
        (
            None,
            {
                'fields': ('title', 'quantity', 'unit', 'unit_price', 'discount', 'tax_rate', 'weight')
            }
        ),
    )
    model = Item
    extra = 0


class OverdueFilter(admin.SimpleListFilter):
    title = _('overdue')
    parameter_name = 'overdue'

    def lookups(self, request, model_admin):
        return (
            ('no', _('no')),
            ('yes', _('yes')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'no':
            return queryset.not_overdue()
        if self.value() == 'yes':
            return queryset.overdue()


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_issue'
    ordering = ['-date_issue', '-sequence']
    actions = ['recalculate_tax', 'send_to_accounting_software']
    list_display = ['pk', 'type', 'number', 'status',
                    'supplier_info', 'customer_info',
                    'annotated_subtotal', 'vat', 'total',
                    'currency', 'date_issue', 'payment_term_days', 'is_overdue_boolean', 'is_paid']
    list_editable = ['status']
    list_filter = ['origin', 'type', 'status', 'payment_method', 'delivery_method', OverdueFilter, 'language', 'currency']
    search_fields = ['number', 'subtitle', 'note', 'supplier_name', 'customer_name', 'shipping_name']
    inlines = (ItemInline, )
    autocomplete_fields = ('related_invoices',)
    fieldsets = (
        (_(u'General information'), {
            'fields': (
                'type', 'status', 'language', ('sequence', 'number'), 'subtitle', 'related_document', 'related_invoices',
                'date_issue', 'date_tax_point', 'date_due', 'date_sent', 'date_paid',
                'note'
            )
        }),
        (_(u'Contact details'), {
            'fields': (
                'issuer_name', 'issuer_email', 'issuer_phone'
            )
        }),
        (_(u'Payment details'), {
            'fields': (
                'currency', 'credit', 'already_paid',
                ('payment_method', 'delivery_method'),
                ('constant_symbol', 'variable_symbol', 'specific_symbol', 'reference'),
                'bank_name', 'bank_country', 'bank_city', 'bank_street', 'bank_zip', 'bank_iban', 'bank_swift_bic'
            )
        }),
        (_(u'Supplier details'), {
            'fields': (
                'supplier_name', 'supplier_street', 'supplier_zip', 'supplier_city', 'supplier_country',
                'supplier_registration_id', 'supplier_tax_id', 'supplier_vat_id',
                'supplier_additional_info'

            )
        }),
        (_(u'Customer details'), {
            'fields': (
                'customer_name', 'customer_street', 'customer_zip', 'customer_city', 'customer_country',
                'customer_registration_id', 'customer_tax_id', 'customer_vat_id', 'customer_additional_info',
            )
        }),
        (_(u'Shipping details'), {
            'fields': (
                'shipping_name', 'shipping_street', 'shipping_zip', 'shipping_city', 'shipping_country'
            )
        })
    )

    def get_actions(self, request):
        """
        Return only explicitly listed actions plus all export-related actions.
        """
        actions = super().get_actions(request)

        # Keep only actions explicitly listed on the ModelAdmin
        explicit = set(self.actions or [])
        actions = {
            name: action for name, action in actions.items()
            if name in explicit
        }

        # Add export actions explicitly
        export_actions = {
            'export_xlsx': (InvoiceAdmin.export_xlsx, 'export_xlsx', self.export_xlsx.short_description),
            'export_pdf': (InvoiceAdmin.export_pdf, 'export_pdf', self.export_pdf.short_description),
            'export_isdoc': (InvoiceAdmin.export_isdoc, 'export_isdoc', self.export_isdoc.short_description),
            'export_mrp_v1': (InvoiceAdmin.export_mrp_v1, 'export_mrp_v1', self.export_mrp_v1.short_description),
            'export_mrp_v2_outgoing': (
                InvoiceAdmin.export_mrp_v2_outgoing,
                'export_mrp_v2_outgoing',
                self.export_mrp_v2_outgoing.short_description
            ),
            'export_mrp_v2_incoming': (
                InvoiceAdmin.export_mrp_v2_incoming,
                'export_mrp_v2_incoming',
                self.export_mrp_v2_incoming.short_description
            ),
        }

        actions.update(export_actions)
        return actions

    def get_queryset(self, request):
        return self.model.objects.annotate(annotated_subtotal=F('total')-Coalesce(F('vat'), 0, output_field=DecimalField()))

    def annotated_subtotal(self, invoice):
        return invoice.annotated_subtotal
    annotated_subtotal.short_description = _(u'subtotal')

    def supplier_info(self, invoice):
        return mark_safe(u'%s<br>%s' % (invoice.supplier_name, invoice.supplier_country.name))
    supplier_info.short_description = _(u'supplier')

    def customer_info(self, invoice):
        return mark_safe(u'%s<br>%s' % (invoice.customer_name, invoice.customer_country.name))
    customer_info.short_description = _(u'customer')

    def payment_term_days(self, invoice):
        return u'%s days' % invoice.payment_term
    payment_term_days.short_description = _(u'payment term')

    def is_overdue_boolean(self, invoice):
        return invoice.is_overdue
    is_overdue_boolean.boolean = True
    is_overdue_boolean.short_description = _(u'is overdue')

    def is_paid(self, invoice):
        return invoice.status == Invoice.STATUS.PAID
    is_paid.boolean = True
    is_paid.short_description = _(u'is paid')

    def recalculate_tax(self, request, queryset):
        for invoice in queryset:
            invoice.recalculate_tax()

    def send_to_accounting_software(self, request, queryset):
        manager = get_accounting_software_manager()

        if manager is None:
            messages.error(request, _('Missing specification of accounting software'))
            return

        try:
            result = manager.send_to_accounting_software(request, queryset)

            if isinstance(result, str):
                messages.success(request, result)
            elif isinstance(result, list):
                success = 0

                for r in result:
                    if r['status_code'] == 200:
                        success += 1
                    else:
                        messages.error(request, f"[{r['invoice']}]: {r['status_code']} ({r['reason']})")

                if success > 0:
                    messages.success(request, _('%d invoices sent to accounting software') % success)

        except Exception as e:
            messages.error(request, e)

    send_to_accounting_software.short_description = _('Send to accounting software')

    def _export_and_email(self, request, queryset, exporter_class):
        """
        Common export logic for email-based exports.
        
        Args:
            request: The HTTP request object
            queryset: The queryset of invoices to export
            exporter_class: The exporter class to use
        """
        creator_id = request.user.id
        recipients_ids = [creator_id]
        invoice_ids = queryset.values_list("id", flat=True)

        mail_exported_invoices.delay(
            exporter_class, creator_id, recipients_ids, invoice_ids, exporter_class.filename
        )

        messages.success(request, _('Export %d invoices sent to email') % queryset.count())

    def export_xlsx(self, request, queryset):
        from invoicing.exporters import InvoiceXlsxListExporter
        self._export_and_email(request, queryset, InvoiceXlsxListExporter)

    export_xlsx.short_description = _('Export to xlsx')

    def export_pdf(self, request, queryset):
        from invoicing.exporters import InvoicePdfDetailExporter
        self._export_and_email(request, queryset, InvoicePdfDetailExporter)

    export_pdf.short_description = _('Export to PDF')

    def export_isdoc(self, request, queryset):
        from invoicing.exporters import InvoiceISDOCXmlListExporter
        self._export_and_email(request, queryset, InvoiceISDOCXmlListExporter)

    export_isdoc.short_description = _('Export to ISDOC (XML)')

    def export_mrp_v2_outgoing(self, request, queryset):
        from invoicing.exporters.mrp.v2.list import OutgoingInvoiceMrpExporter
        self._export_and_email(request, queryset, OutgoingInvoiceMrpExporter)

    export_mrp_v2_outgoing.short_description = _('Export to MRP v2 (outgoing)')

    def export_mrp_v2_incoming(self, request, queryset):
        from invoicing.exporters.mrp.v2.list import IncomingInvoiceMrpExporter
        self._export_and_email(request, queryset, IncomingInvoiceMrpExporter)

    export_mrp_v2_incoming.short_description = _('Export to MRP v2 (incoming)')

    def export_mrp_v1(self, request, queryset):
        """Legacy MRP XML export (v1) - returns direct response instead of email."""
        creator_id = request.user.id
        recipients_ids = [creator_id]
        invoice_ids = queryset.values_list("id", flat=True)

        mail_exported_invoices_mrp_v1.delay(
            creator_id, recipients_ids, invoice_ids, 'MRP_export.zip'
        )

    export_mrp_v1.short_description = _('Export to MRP v1 (XML)')
