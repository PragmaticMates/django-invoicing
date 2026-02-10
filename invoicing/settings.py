import json

from django.conf import settings


LANGUAGES = getattr(settings, 'INVOICING_LANGUAGES', getattr(settings, 'LANGUAGES', []))

# Default managers configuration - can be overridden in Django settings
# see README.rst for configuration examples.
DEFAULT_INVOICING_MANAGERS = {
    "invoicing.exporters.pdf.managers.PdfManager": {},
    "invoicing.exporters.xlsx.managers.XlsxManager": {}
}

# Allow users to configure only the managers they need
INVOICING_MANAGERS = getattr(settings, 'INVOICING_MANAGERS', DEFAULT_INVOICING_MANAGERS)