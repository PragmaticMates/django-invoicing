from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _

from .validators import VATValidator


def validate_min_length(value, min_length=4):
    if len(str(value)) < min_length:
        raise ValidationError(_(u'Minimal length is %d') % min_length)


class VATField(models.CharField):
    """
    An VAT consists of up to 13 alphanumeric characters.

    http://en.wikipedia.org/wiki/Vat_number
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 13)
        super(VATField, self).__init__(*args, **kwargs)
        self.validators.append(VATValidator())
        self.validators.append(validate_min_length)

    def to_python(self, value):
        value = super(VATField, self).to_python(value)
        try:
            return value.replace(' ', '').upper()
        except AttributeError:
            return value


# If south is installed, ensure that IBANField will be introspected just
# like a normal CharField
try:
    from south.modelsinspector import add_introspection_rules

    add_introspection_rules([], ["^invoicing\.fields\.VATField"])
except ImportError:
    pass


class VATFormField(forms.CharField):
    """
    An VAT consists of up to 13 alphanumeric characters.

    http://en.wikipedia.org/wiki/Vat_number
    """
    default_validators = [VATValidator(), validate_min_length]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 13)
        super(VATFormField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        value = super(VATFormField, self).to_python(value)
        try:
            return value.replace(' ', '').upper()
        except AttributeError:
            return value
