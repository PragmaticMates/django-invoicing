# Installation

## Requirements

- Python 3.8+
- Django 4.2+
- See `requirements.txt` for the full dependency list

## Install the package

```
pip install django-invoicing
```

To include all exporter backends (PDF, XLSX, ISDOC, MRP, …) install the optional extras:

```
pip install "django-invoicing[exporters]"
```

This installs `django-outputs`, which provides the asynchronous export queue and email delivery that all exporters depend on.

## Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    'django_countries',
    'djmoney',
    'model_utils',
    'invoicing',
    # Required if you use any exporter:
    'outputs',
]
```

## Run migrations

```
python manage.py migrate invoicing
```

## URL configuration (optional)

The app ships with a single view that renders an invoice as HTML. Include it only if you need that endpoint:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    ...
    path('invoicing/', include('invoicing.urls', namespace='invoicing')),
]
```

This registers the route `invoicing/invoice/detail/<pk>/` as `invoicing:invoice_detail`.

## Minimum settings

The only required Django setting is `INVOICING_SUPPLIER`, which pre-fills the supplier block on every new invoice:

```python
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

All other settings have sensible defaults. See [Configuration](configuration.md) for the full reference.
