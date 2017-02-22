from django.conf.urls import url

from invoicing.views import InvoiceDetailView


urlpatterns = [
    url(r'^invoice/detail/(?P<pk>[-\d]+)/$', InvoiceDetailView.as_view(), name='invoice_detail'),
]
