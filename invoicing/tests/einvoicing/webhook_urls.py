from django.contrib import admin
from django.urls import include, path

from invoicing.einvoicing.views import WebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('einvoicing/', include('invoicing.einvoicing.urls')),
    # an older per-account URL shape, still served
    path('legacy/webhook/<slug:provider>/<int:account_pk>/', WebhookView.as_view()),
]
