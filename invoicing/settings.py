import json

from django.conf import settings


LANGUAGES = getattr(settings, 'INVOICING_LANGUAGES', getattr(settings, 'LANGUAGES', []))
ACCOUNTING_SOFTWARE = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE', None)
try:
    ACCOUNTING_SOFTWARE_API_DATA = json.loads(getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_API_DATA', None))
except:
    ACCOUNTING_SOFTWARE_API_DATA = None
# ACCOUNTING_SOFTWARE_API_KEY = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_API_KEY', None)

# TODO: refactor
ACCOUNTING_SOFTWARE_IKROS_API_URL = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_IKROS_API_URL', 'https://eshops.inteo.sk/api/v1/invoices/')
ACCOUNTING_SOFTWARE_PROFIT365_API_URL = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_PROFIT365_API_URL', 'https://api.profit365.eu/1.6')
ACCOUNTING_SOFTWARE_MANAGER = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_MANAGER', None)
