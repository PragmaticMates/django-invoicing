from django import forms
from django.forms import ModelForm
from django.utils.translation import ugettext_lazy as _

from models import InvoiceItem


class InvoiceItemForm(ModelForm):
    tax_rate = forms.DecimalField(required=False, label=_(u'tax rate (%)'), max_digits=3, decimal_places=1)

    class Meta:
        model = InvoiceItem
