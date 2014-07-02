from django.http import HttpResponse
from django.template import loader, Context

from . import InvoiceFormatter


class BootstrapHTMLFormatter(InvoiceFormatter):
    template_name = 'invoicing/formatters/bootstrap.html'

    def get_data(self):
        return {
            "invoice": self.invoice,
            "INVOICING_DATE_FORMAT_TAG": "d.m.Y"  # TODO: move to settings
        }

    def get_response(self):
        template = loader.get_template(self.template_name)
        data = self.get_data()
        context = Context(data)
        response_data = template.render(context)
        return HttpResponse(response_data)
