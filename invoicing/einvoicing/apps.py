from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EInvoicingConfig(AppConfig):
    name = 'invoicing.einvoicing'
    label = 'invoicing_einvoicing'
    verbose_name = _('E-invoicing')
    default_auto_field = 'django.db.models.AutoField'
