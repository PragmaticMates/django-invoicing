from django.http import HttpResponse
from django.template import loader, Context

from . import InvoiceFormatter


class HTMLFormatter(InvoiceFormatter):
    template_name = 'invoicing/formatters/html.html'

    def get_data(self):
        return {
            "invoice": self.invoice,
            "INVOICING_DATE_FORMAT_TAG": "d.m.Y"  # TODO: move to settings
        }

    def get_response(self, context={}):
        template = loader.get_template(self.template_name)
        data = self.get_data()
        data.update(context)

        try:
            response_data = template.render(Context(data))
        except TypeError:
            response_data = template.render(data)

        return HttpResponse(response_data)


class BootstrapHTMLFormatter(HTMLFormatter):
    template_name = 'invoicing/formatters/bootstrap.html'
