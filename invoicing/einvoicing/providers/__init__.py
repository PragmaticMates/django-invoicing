from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from invoicing.einvoicing import conf
from invoicing.einvoicing.providers.base import (
    CapabilityNotSupported, EInvoiceProvider, OutgoingDocument, ProviderError, Reachability, StatusResult, SubmitResult,
)


__all__ = [
    'CapabilityNotSupported', 'EInvoiceProvider', 'OutgoingDocument', 'ProviderError', 'Reachability',
    'StatusResult', 'SubmitResult', 'get_provider',
]


def get_provider(invoice):
    """The provider to send ``invoice`` with, from ``INVOICING_EINVOICING['PROVIDER_RESOLVER']``."""
    resolver = conf.get('PROVIDER_RESOLVER')

    if not resolver:
        raise ImproperlyConfigured("Set INVOICING_EINVOICING['PROVIDER_RESOLVER'] to send e-invoices")

    provider = import_string(resolver)(invoice)

    if provider is None:
        raise ImproperlyConfigured(f'No e-invoicing provider is configured for invoice {invoice}')

    return provider
