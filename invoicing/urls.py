from django.conf.urls import url

from invoicing.views import InvoiceDetailView


app_name = 'invoicing'

urlpatterns = [
    url(r'^invoice/detail/(?P<pk>[-\d]+)/$', InvoiceDetailView.as_view(), name='invoice_detail'),
]
