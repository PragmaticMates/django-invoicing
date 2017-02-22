from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import DetailView

from invoicing.models import Invoice
from invoicing.utils import import_name


class InvoiceDetailView(DetailView):
    model = Invoice

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_active and not request.user.is_superuser:
            return HttpResponseForbidden()

        invoice = get_object_or_404(self.model, pk=kwargs.get('pk', None))

        invoicing_formatter = getattr(settings, 'INVOICING_FORMATTER', 'invoicing.formatters.html.BootstrapHTMLFormatter')
        formatter_class = import_name(invoicing_formatter)
        formatter = formatter_class(invoice)
        return formatter.get_response()
