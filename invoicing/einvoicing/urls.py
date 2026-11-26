"""
Include outside i18n_patterns (providers do not follow redirects):

    path('einvoicing/', include('invoicing.einvoicing.urls')),
"""
from django.urls import path

from invoicing.einvoicing.views import WebhookView


urlpatterns = [
    path('webhook/<slug:provider>/', WebhookView.as_view(), name='einvoicing_webhook'),
]
