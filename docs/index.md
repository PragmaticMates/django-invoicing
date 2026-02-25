# django-invoicing

**django-invoicing** is a reusable Django app for managing invoices. It provides a rich data model, automatic sequence and number generation, VAT/taxation logic, and a pluggable export system that integrates with Django Admin.

## Features

- **Invoice management** — issued and received invoices, credit notes, proforma and advance invoices
- **Automatic numbering** — configurable sequence generation and number formatting via Django template strings
- **VAT & taxation** — built-in EU taxation policy with per-country rates and VIES reverse-charge validation
- **Pluggable exporters** — PDF, XLSX, ISDOC XML, MRP XML (v1 & v2), IKROS API, Profit365 API
- **Asynchronous exports** — exports are queued and delivered by email via `django-outputs`
- **Django Admin integration** — export actions added automatically for every configured manager

## Quick start

```python
# settings.py
INSTALLED_APPS = [
    ...
    'invoicing',
]

INVOICING_SUPPLIER = {
    'name': 'Acme Ltd.',
    'street': 'Main Street 1',
    'city': 'Springfield',
    'zip': '12345',
    'country_code': 'SK',
    'registration_id': '12345678',
    'tax_id': '2012345678',
    'vat_id': 'SK2012345678',
    'bank': {
        'name': 'Good Bank',
        'street': 'Bank Street 1',
        'city': 'Springfield',
        'zip': '12345',
        'country_code': 'SK',
        'iban': 'SK0000000000000000000028',
        'swift_bic': 'GOODBANK',
    },
}
```

Then run migrations:

```
python manage.py migrate invoicing
```

See [Installation](installation.md) for full setup instructions and [Configuration](configuration.md) for all available settings.
