from django.urls import re_path

from invoicing.views import InvoiceDetailView


app_name = 'invoicing'

urlpatterns = [
    re_path(r'^invoice/detail/(?P<pk>[-\d]+)/$', InvoiceDetailView.as_view(), name='invoice_detail'),
]
