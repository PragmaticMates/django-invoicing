from django.conf.urls import patterns, url

from views import InvoiceDetailView


urlpatterns = patterns('',
    url(r'^invoice/detail/(?P<pk>[-\d]+)/$', InvoiceDetailView.as_view(), name='invoice_detail'),
)
