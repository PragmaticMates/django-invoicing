from django import template
from django.template import loader, Context

from ..formatters.html import HTMLFormatter

register = template.Library()


@register.filter
def as_html(invoice):
    template = loader.get_template('invoicing/formatters/html.html')
    formatter = HTMLFormatter(invoice)
    data = formatter.get_data()

    try:
        return template.render(Context(data))
    except TypeError:
        return template.render(data)


@register.filter
def nice_iban(iban):
    return ' '.join(iban[i:i+4] for i in range(0, len(iban), 4))
