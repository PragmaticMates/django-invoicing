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

    # Dotted path to a callable(invoice) returning the EInvoiceProvider to send it with
    'PROVIDER_RESOLVER': None,

    # Also run the provider's own validation (if it has one) before storing a transmission
    'PREVALIDATE_WITH_PROVIDER': True,

    # Stop polling the status of a transmission this many days after submitting it
    'STATUS_POLL_DAYS': 30,

    # A transmission stuck in SUBMITTING this long (a worker died mid-request) may be resubmitted
    'SUBMITTING_TIMEOUT_SECONDS': 300,

    # Dotted path to a callable(invoice) returning the documents (ubl.Attachment) to embed
    # into each e-invoice, e.g. its PDF; used when sending, checking and exporting
    'ATTACHMENTS': None,

    # Invoice statuses that may be sent as e-invoices, e.g. ('NEW',); None means any
    'SENDABLE_STATUSES': None,

    # Background jobs (django-pragmatic task decorator, e.g. django-rq): the queue sending
    # and refreshing run on, and the periodic maintenance (resubmit unsent, poll statuses),
    # registered by django-pragmatic's rqscheduler; a cron of None disables it
    'QUEUE': 'default',
    'MAINTENANCE_CRON': '*/15 * * * *',
    'MAINTENANCE_QUEUE': 'cron',
    'MAX_SUBMIT_ATTEMPTS': 10,

    # Providers whose webhooks invoicing.einvoicing.urls receives, by name
    'WEBHOOK_PROVIDERS': {
        'slovakodata': 'invoicing.einvoicing.providers.slovakodata.SlovakodataProvider',
    },

    # Credentials for providers.slovakodata.from_settings, the resolver for a project with a
    # single SLOVAKODATA account: ENVIRONMENT ('test' or 'production'), CLIENT_ID,
    # CLIENT_SECRET, API_KEY, WEBHOOK_SECRET
    'SLOVAKODATA': None,
}


def get(key):
    return getattr(settings, 'INVOICING_EINVOICING', {}).get(key, DEFAULTS[key])
