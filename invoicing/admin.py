import datetime

from django.contrib import admin
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    fieldsets = (
        (
            None,
            {
                'fields': ('title', 'quantity', 'unit', 'unit_price', 'tax_rate', 'weight')
            }
        ),
    )
    model = InvoiceItem
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
            return queryset.filter(Q(date_due__gt=datetime.datetime.combine(now().date(), datetime.time.max))|Q(status=Invoice.STATUS.PAID))
        if self.value() == 'yes':
            return queryset.filter(date_due__lt=datetime.datetime.combine(now().date(), datetime.time.max)).exclude(status=Invoice.STATUS.PAID)


class InvoiceAdmin(admin.ModelAdmin):
    date_hierarchy = 'date_issue'
    list_display = ['pk', 'type', 'full_number', 'status', 'customer_name', 'customer_country',
                    'subtotal', 'vat', 'total', 'currency', 'date_issue', 'payment_term', 'is_overdue_boolean', 'is_paid']
    list_editable = ['status']
    list_filter = ['type', 'status', 'payment_method', OverdueFilter,
                   #'language', 'currency'
    ]
    search_fields = ['number', 'subtitle', 'note', 'supplier_name', 'customer_name', 'shipping_name']
    inlines = (InvoiceItemInline, )
    fieldsets = (
        (_(u'General information'), {
            'fields': (
                'type', 'number', 'full_number', 'status', 'subtitle', 'language', 'note',
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
                'currency', 'discount', 'credit',
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

    def is_overdue_boolean(self, invoice):
        return invoice.is_overdue
    is_overdue_boolean.boolean = True
    is_overdue_boolean.short_description = _(u'Is overdue')

    def is_paid(self, invoice):
        return invoice.status == Invoice.STATUS.PAID
    is_paid.boolean = True
    is_paid.short_description = _(u'Is paid')

admin.site.register(Invoice, InvoiceAdmin)
