import json
from pprint import pprint

import requests
from django.contrib import admin, messages
from django.core.validators import EMPTY_VALUES
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from invoicing import settings as invoicing_settings
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
    actions = ['send_to_accounting_software']
    list_display = ['pk', 'type', 'number', 'status',
                    'supplier_info', 'customer_info',
                    'annotated_subtotal', 'vat', 'total',
                    'currency', 'date_issue', 'payment_term_days', 'is_overdue_boolean', 'is_paid']
    list_editable = ['status']
    list_filter = ['type', 'status', 'payment_method', 'delivery_method', OverdueFilter, 'language', 'currency']
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
                'currency', 'credit', #'already_paid',
                ('payment_method', 'delivery_method'),
                ('constant_symbol', 'variable_symbol', 'specific_symbol', 'reference'),
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

    def get_queryset(self, request):
        return self.model.objects.annotate(annotated_subtotal=F('total')-Coalesce(F('vat'), 0))

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

    def send_to_accounting_software(self, request, queryset):
        if invoicing_settings.ACCOUNTING_SOFTWARE in EMPTY_VALUES:
            messages.error(request, _('Missing specification of accounting software'))
            return

        if invoicing_settings.ACCOUNTING_SOFTWARE_API_KEY in EMPTY_VALUES:
            messages.error(request, _('Missing accounting software API'))
            return

        if invoicing_settings.ACCOUNTING_SOFTWARE != 'IKROS':
            # TODO: more universal implementation
            messages.error(request, _('Accounting software %s not implemented') % invoicing_settings.ACCOUNTING_SOFTWARE)
            return

        invoices_data = []

        if invoicing_settings.ACCOUNTING_SOFTWARE == 'IKROS':
            for invoice in queryset:
                invoice_data = {
                    "documentNumber": invoice.number,
                    "createDate": invoice.date_issue.strftime('%Y-%m-%dT00:00:00'),
                    "dueDate": invoice.date_due.strftime('%Y-%m-%dT00:00:00'),
                    "completionDate": invoice.date_tax_point.strftime('%Y-%m-%dT00:00:00'),
                    "clientName": invoice.customer_name,
                    "clientStreet": invoice.customer_street,
                    "clientPostCode": invoice.customer_zip,
                    "clientTown": invoice.customer_city,
                    "clientCountry": invoice.get_customer_country_display(),
                    "clientRegistrationId": invoice.customer_registration_id,
                    "clientTaxId": invoice.customer_tax_id,
                    "clientVatId": invoice.customer_vat_id,
                    "clientPhone": invoice.customer_phone,
                    "clientEmail": invoice.customer_email,
                    "variableSymbol": invoice.variable_symbol,
                    "paymentType": invoice.get_payment_method_display(),
                    "deliveryType": invoice.get_delivery_method_display(),
                    "senderContactName": invoice.issuer_name,
                    "clientPostalName": invoice.shipping_name,
                    "clientPostalStreet": invoice.shipping_street,
                    "clientPostalPostCode": invoice.shipping_zip,
                    "clientPostalTown": invoice.shipping_city,
                    "clientPostalCountry": invoice.get_shipping_country_display(),
                    "clientInternalId": f'{invoice.customer_country}001',
                    # "clientHasDifferentPostalAddress": True,
                    "currency": invoice.currency,
                    # "orderNumber": invoice.variable_symbol,
                    "items": []
                }

                for item in invoice.item_set.all():
                    item_data = {
                        "name": item.title,
                        "count": str(item.quantity),
                        "measureType": item.get_unit_display(),
                        "unitPrice": str(item.unit_price),
                        "vat": item.vat
                    }

                    if invoice.status == Invoice.STATUS.CANCELED:
                        item_data['count'] = 0  # not working actually (min value = 1)
                        item_data['unitPrice'] = 0
                        # item_data['description'] = 'STORNO'

                    invoice_data['items'].append(item_data)

                if invoice.status == Invoice.STATUS.CANCELED:
                    invoice_data['closingText'] = 'STORNO'

                if invoice.credit != 0:
                    invoice_data['items'][0]['hasDiscount'] = True
                    invoice_data['items'][0]['discountValue'] = str(invoice.credit * -1)  # TODO: substract VAT
                    # invoice_data['items'][0]['discountValueWithVat'] = str(invoice.credit * -1)

                invoices_data.append(invoice_data)

            # pprint(invoices_data)
            payload = json.dumps(invoices_data)


            url = invoicing_settings.ACCOUNTING_SOFTWARE_IKROS_API_URL
            api_key = invoicing_settings.ACCOUNTING_SOFTWARE_API_KEY
            headers = {
                'Authorization': 'Bearer ' + str(api_key),
                'Content-Type': 'application/json'
            }
            r = requests.post(url=url, data=payload, headers=headers)
            data = r.json()
            
            # pprint(data)

            if data.get('message', None) is not None:
                messages.error(request, _('Result code: %d. Message: %s (%s)') % (
                    data.get('code', data.get('resultCode')),
                    data['message'],
                    data.get('errorType', '-'))
                )
            else:
                if 'documents' in data:
                    if len(data['documents']) > 0:
                        download_url = data['documents'][0]['downloadUrl']
                        # requests.get(download_url)

                        messages.success(request, mark_safe(_('%d invoices sent to accounting software [<a href="%s" target="_blank">Fetch</a>]') % (
                            queryset.count(),
                            download_url
                        )))
                    else:
                        messages.success(request, _('%d invoices sent to accounting software') % (
                            queryset.count(),
                        ))

    send_to_accounting_software.short_description = _('Send to accounting software')
