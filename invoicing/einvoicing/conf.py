"""
``settings.INVOICING_EINVOICING``: a dict, every key optional.
"""
from django.conf import settings


DEFAULTS = {
    # Builder used by ubl.get_builder()
    'BUILDER_CLASS': 'invoicing.einvoicing.ubl.PeppolBIS3Builder',

    # Item.unit -> UN/ECE Recommendation 20 unit code
    'UNIT_CODES': {
        'EMPTY': 'C62',   # one
        'PIECES': 'H87',  # piece
        'HOURS': 'HUR',   # hour
    },
    'DEFAULT_UNIT_CODE': 'C62',

    # Invoice.payment_method -> UNCL4461 payment means code
    'PAYMENT_MEANS_CODES': {
        'BANK_TRANSFER': '30',     # credit transfer
        'CASH': '10',              # in cash
        'CASH_ON_DELIVERY': '10',  # in cash, on delivery
        'PAYMENT_CARD': '48',      # bank card
    },

    # Run the Peppol Schematron rules in validation.validate() (needs saxonche)
    'SCHEMATRON': True,

    # What validation.preflight() accepts; None means anything. The builder does
    # not state a separate VAT currency (BT-6), hence EUR only by default.
    'ALLOWED_CURRENCIES': ('EUR',),
    'ALLOWED_CUSTOMER_COUNTRIES': None,
}


def get(key):
    return getattr(settings, 'INVOICING_EINVOICING', {}).get(key, DEFAULTS[key])
