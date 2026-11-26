import inspect
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.db.models import F, DecimalField
from django.db.models.functions import Coalesce
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from invoicing import settings as invoicing_settings
from invoicing.models import Invoice, Item


def _exporter_path_and_label(exporter_cls):
    """Return (path, label) for an exporter class. Path matches Export.exporter_path storage."""
    path = getattr(exporter_cls, 'get_path', lambda: None)()
    if path is None:
        path = f'{exporter_cls.__module__}.{exporter_cls.__qualname__}'
    label = getattr(exporter_cls, 'get_description', lambda: None)() or path
    return (path, label)


def get_exporter_path_choices():
    """Return choices of (path, label) from all configured INVOICING_MANAGERS.

    Collects exporter_class from each manager so the filter only shows exporters
    that are actually used by the invoicing app.
    """
    seen_paths = set()
    choices = []

    for manager_class_path in invoicing_settings.INVOICING_MANAGERS:
        try:
            manager_class = import_string(manager_class_path)
            manager_instance = manager_class()
        except (ImportError, ValueError, Exception):
            continue

        exporter_cls = getattr(manager_instance, 'exporter_class', None)
        if exporter_cls is None:
            continue
        path, label = _exporter_path_and_label(exporter_cls)
        if path not in seen_paths:
            seen_paths.add(path)
            choices.append((path, label))

    return sorted(choices, key=lambda c: c[1])


class NotExportedWithExporterListFilter(admin.SimpleListFilter):
    title = _('not yet exported with exporter')
    parameter_name = 'not_exported_with_exporter'

    def lookups(self, request, model_admin):
        return get_exporter_path_choices()

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        from outputs.models import ExportItem
        return queryset.exclude(
            export_items__export__exporter_path=value,
            export_items__result=ExportItem.RESULT_SUCCESS,
        )


def is_einvoice_locked(invoice):
    """Sent (or being sent) as an e-invoice: its content must not change any more."""
    if invoice is None or invoice.pk is None or not apps.is_installed('invoicing.einvoicing'):
        return False

    from invoicing.einvoicing.services import live_transmission
    return live_transmission(invoice) is not None


class ItemInline(admin.TabularInline):
    fieldsets = (
        (
            None,
            {
                'fields': ('title', 'quantity', 'unit', 'unit_price', 'discount', 'tax_rate', 'vat_category', 'weight')
            }
        ),
    )
    model = Item
    extra = 0

    def has_add_permission(self, request, obj=None):
        return not is_einvoice_locked(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not is_einvoice_locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not is_einvoice_locked(obj) and super().has_delete_permission(request, obj)


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
    actions = ['recalculate_tax']
    list_display = ['pk', 'type', 'origin', 'number', 'status',
                    'supplier_info', 'customer_info',
                    'annotated_subtotal', 'vat', 'total',
                    'currency', 'date_issue', 'payment_term_days', 'is_overdue_boolean', 'is_paid']
    list_editable = ['status']
    list_filter = [
        'origin', 'type', 'status', 'payment_method', 'delivery_method',
        OverdueFilter, NotExportedWithExporterListFilter, 'language', 'currency',
    ]
    search_fields = ['number', 'subtitle', 'note', 'supplier_name', 'customer_name', 'shipping_name']
    inlines = (ItemInline, )
    autocomplete_fields = ('related_invoices',)
    fieldsets = (
        (_(u'General information'), {
            'fields': (
                'type', 'origin', 'status', 'language', ('sequence', 'number'), 'subtitle', 'related_document', 'related_invoices',
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
                'customer_email', 'customer_phone',
            )
        }),
        (_(u'E-invoicing'), {
            'classes': ('collapse',),
            'fields': (
                'buyer_reference',
                ('supplier_endpoint_scheme', 'supplier_endpoint_id'),
                ('customer_endpoint_scheme', 'customer_endpoint_id'),
                ('vat_exemption_reason', 'vat_exemption_reason_code'),
            )
        }),
        (_(u'Shipping details'), {
            'fields': (
                'shipping_name', 'shipping_street', 'shipping_zip', 'shipping_city', 'shipping_country'
            )
        })
    )

    # What may still change on an invoice sent as an e-invoice: its life after issuing
    EINVOICE_LOCKED_EDITABLE = ('status', 'date_paid', 'already_paid')

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))

        if is_einvoice_locked(obj):
            # the e-invoice is in Peppol: change it with a credit note, not here
            for name in flatten_fieldsets(self.get_fieldsets(request, obj)):
                if name not in self.EINVOICE_LOCKED_EDITABLE and name not in readonly:
                    readonly.append(name)

        return readonly

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)

        if obj is not None and apps.is_installed('invoicing.einvoicing'):
            from invoicing.einvoicing.admin import TransmissionInline
            inlines.append(TransmissionInline(self.model, self.admin_site))

        return inlines

    def get_actions(self, request):
        """
        Return only explicitly listed actions plus all export actions from configured managers.
        
        Iterates over all managers configured in INVOICING_MANAGERS setting and adds
        all methods starting with "export_" as admin actions.
        """
        actions = super().get_actions(request)

        # Collect export actions from all configured managers
        for manager_class_path, manager_config in invoicing_settings.INVOICING_MANAGERS.items():
            try:
                manager_class = import_string(manager_class_path)
                manager_instance = manager_class()
            except (ImportError, Exception):
                continue

            # Find all methods starting with "export_"
            for attr_name in dir(manager_instance):
                if not attr_name.startswith('export_'):
                    continue

                method = getattr(manager_instance, attr_name, None)
                if not callable(method):
                    continue

                # Create unique action name by combining manager class name and method name
                class_name = manager_class_path.rsplit('.', 1)[-1].lower()
                unique_action_name = f"{class_name}_{attr_name}"

                # Create a wrapper that calls the manager method
                def make_action(mgr_instance, method_name):
                    def action(modeladmin, request, queryset):
                        method = getattr(mgr_instance, method_name)
                        # Inspect method signature to determine what parameters it accepts
                        sig = inspect.signature(method)
                        params = {'request': request, 'queryset': queryset}
                        
                        # Only add exporter_class if the method accepts it
                        if 'exporter_class' in sig.parameters:
                            params['exporter_class'] = None
                        
                        return method(**params)
                    action.__name__ = method_name
                    action.short_description = getattr(
                        getattr(mgr_instance, method_name), 'short_description', method_name
                    )
                    return action

                action_func = make_action(manager_instance, attr_name)
                actions[unique_action_name] = (action_func, unique_action_name, action_func.short_description)

        return actions

    def get_queryset(self, request):
        queryset = self.model.objects.annotate(annotated_subtotal=F('total')-Coalesce(F('vat'), 0, output_field=DecimalField()))

        if apps.is_installed('invoicing.einvoicing'):
            from invoicing.einvoicing.services import with_transmissions
            queryset = with_transmissions(queryset)

        return queryset

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))

        if apps.is_installed('invoicing.einvoicing') and 'einvoice_status' not in list_display:
            list_display.insert(list_display.index('status') + 1, 'einvoice_status')

        return list_display

    # label colours of the newest transmission's status
    EINVOICE_STATUS_COLOURS = {'reached': '#2e7d32', 'attention': '#ef6c00', 'not_delivered': '#c62828', 'under_way': '#1565c0'}

    @admin.display(description=_(u'e-invoice'))
    def einvoice_status(self, invoice):
        transmissions = getattr(invoice, 'einvoice_transmission_list', None)
        if not transmissions:
            return mark_safe('<span style="color: var(--body-quiet-color)">—</span>')

        from django.urls import reverse
        from django.utils.html import format_html
        from invoicing.einvoicing.models import TransmissionStatus

        transmission = transmissions[0]
        if transmission.has_reached_recipient:
            colour = self.EINVOICE_STATUS_COLOURS['reached']
        elif not transmission.is_live:
            colour = self.EINVOICE_STATUS_COLOURS['not_delivered']
        elif transmission.status in (TransmissionStatus.CONFLICT, TransmissionStatus.SUBMIT_UNKNOWN):
            colour = self.EINVOICE_STATUS_COLOURS['attention']
        else:
            colour = self.EINVOICE_STATUS_COLOURS['under_way']

        return format_html(
            '<a href="{}" style="color: {}; font-weight: bold" title="{}">{}</a>',
            reverse('admin:invoicing_einvoicing_einvoicetransmission_change', args=[transmission.pk]),
            colour, transmission.provider_status or '', transmission.get_status_display(),
        )

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
