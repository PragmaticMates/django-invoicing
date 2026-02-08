import json

from django.conf import settings


LANGUAGES = getattr(settings, 'INVOICING_LANGUAGES', getattr(settings, 'LANGUAGES', []))

# Default managers configuration - can be overridden in Django settings
# see README.rst for configuration examples.
DEFAULT_INVOICING_MANAGERS = {
    "invoicing.managers.PdfExportManager": {},
    "invoicing.managers.XlsxExportManager": {}
}

# Allow users to configure only the managers they need
INVOICING_MANAGERS = getattr(settings, 'INVOICING_MANAGERS', DEFAULT_INVOICING_MANAGERS)