import vatnumber

from django_countries.fields import Country

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from invoicing.taxation.eu import EUTaxationPolicy


class VATValidator(object):
    """ A validator for VAT numbers """

    def __init__(self, use_vies_validation=False):
        self.use_vies_validation = use_vies_validation

    def __call__(self, value):
        # check country code
        country_code = str(value[:2])
        country = Country(code=country_code.upper(), flag_url=None)
        if not country:
            raise ValidationError(_('{0} is not a valid country code.').format(country_code))

        if not vatnumber.check_vat(value):
            raise ValidationError(_('{0} is not a valid VAT number').format(value))

        if self.use_vies_validation and EUTaxationPolicy.is_in_EU(country_code):
            if not vatnumber.check_vies(value):
                raise ValidationError(_('{0} is not a valid VAT number').format(value))
