import json

from django.conf import settings


LANGUAGES = getattr(settings, 'INVOICING_LANGUAGES', getattr(settings, 'LANGUAGES', []))

# Default managers configuration - can be overridden in Django settings
# Only includes core managers. For additional managers (MRP, ISDOC, IKROS, PROFIT365),
# see README.rst for configuration examples.
DEFAULT_INVOICING_MANAGERS = {
    "DETAILS": {
        "MANAGER_CLASS": "invoicing.managers.InvoiceDetailsManager",
    },
    "PDF": {
        "MANAGER_CLASS": "invoicing.managers.PdfExportManager",
    },
    "XLSX": {
        "MANAGER_CLASS": "invoicing.managers.XlsxExportManager",
    },
}

# Allow users to configure only the managers they need
INVOICING_MANAGERS = getattr(settings, 'INVOICING_MANAGERS', DEFAULT_INVOICING_MANAGERS)