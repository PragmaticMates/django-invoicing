from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

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


class InvoiceAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_issue'
    list_display = ['pk', 'type', 'number', 'status',
                    'supplier_info', 'customer_info',
                    'subtotal', 'vat', 'total',  # TODO: annotate values using subqueries to improve performance
                    'currency', 'date_issue', 'payment_term_days', 'is_overdue_boolean', 'is_paid']
    list_editable = ['status']
    list_filter = ['type', 'status', 'payment_method', OverdueFilter, 'language', 'currency']
    search_fields = ['number', 'subtitle', 'note', 'supplier_name', 'customer_name', 'shipping_name']
    inlines = (ItemInline, )
    fieldsets = (
        (_(u'General information'), {
            'fields': (
                'type', 'sequence', 'number', 'status', 'subtitle', 'language', 'note',
                'date_issue', 'date_tax_point', 'date_due', 'date_sent'
            )
        }),
        (_(u'Contact details'), {
            'fields': (
                'issuer_name', 'issuer_email', 'issuer_phone'
            )
        }),
        (_(u'Payment details'), {
            'fields': (
                'currency', 'credit',
                #'already_paid',
                'payment_method', 'constant_symbol', 'variable_symbol', 'specific_symbol', 'reference',
                'bank_name', 'bank_country', 'bank_city', 'bank_street', 'bank_zip', 'bank_iban', 'bank_swift_bic'
            )
        }),
        (_(u'Supplier details'), {
            'fields': (
                'supplier_name', 'supplier_street', 'supplier_zip', 'supplier_city', 'supplier_country',
                'supplier_registration_id', 'supplier_tax_id', 'supplier_vat_id', 'supplier_additional_info'

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

admin.site.register(Invoice, InvoiceAdmin)
