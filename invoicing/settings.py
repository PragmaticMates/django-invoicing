from django.conf import settings


ACCOUNTING_SOFTWARE = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE', None)
ACCOUNTING_SOFTWARE_API_KEY = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_API_KEY', None)
ACCOUNTING_SOFTWARE_IKROS_API_URL = getattr(settings, 'INVOICING_ACCOUNTING_SOFTWARE_IKROS_API_URL', 'https://eshops.inteo.sk/api/v1/invoices/')
