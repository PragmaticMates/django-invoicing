import inspect
from django.contrib import admin
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
        except (ImportError, ValueError):
            continue
        if not hasattr(manager_class, 'exporter_class') or manager_class.exporter_class is None:
            continue
        exporter_cls = manager_class.exporter_class
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
    actions = ['recalculate_tax']
    list_display = ['pk', 'type', 'number', 'status',
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
        Return only explicitly listed actions plus all export actions from configured managers.
        
        Iterates over all managers configured in INVOICING_MANAGERS setting and adds
        all methods starting with "export_" as admin actions.
        """
        actions = super().get_actions(request)

        # Keep only actions explicitly listed on the ModelAdmin
        explicit = set(self.actions or [])
        actions = {
            name: action for name, action in actions.items()
            if name in explicit
        }

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
