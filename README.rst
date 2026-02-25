django-invoicing
================

Django app for invoicing with support for multiple export formats and integrations.

Full documentation: https://django-invoicing.readthedocs.io

Installation
------------

::

    pip install django-invoicing

Add ``invoicing`` to ``INSTALLED_APPS`` and run migrations::

    python manage.py migrate invoicing

Quick configuration
-------------------

.. code-block:: python

    # settings.py
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

    # Optional: add extra export managers beyond the default PDF and XLSX
    INVOICING_MANAGERS = {
        "invoicing.exporters.pdf.managers.PdfManager": {},
        "invoicing.exporters.xlsx.managers.XlsxManager": {},
        "invoicing.exporters.isdoc.managers.IsdocManager": {},
        "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {},
        "invoicing.exporters.mrp.v2.managers.MrpIssuedManager": {
            "API_URL": "https://your-mrp-instance.example.com/api/",
        },
        "invoicing.exporters.mrp.v2.managers.MrpReceivedManager": {
            "API_URL": "https://your-mrp-instance.example.com/api/",
        },
        "invoicing.exporters.ikros.managers.IKrosManager": {
            "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
            "API_KEY": "your-api-key",
        },
        "invoicing.exporters.profit365.managers.Profit365Manager": {
            "API_URL": "https://api.profit365.eu/1.6",
            "API_DATA": {
                "Authorization": "Bearer your-token",
                "bankAccountId": "12345",
                "ClientID": "your-client-id",
                "ClientSecret": "your-client-secret",
            },
        },
    }

Features
--------

- Invoice management — issued/received invoices, credit notes, proforma and advance invoices
- Automatic sequence generation and configurable number formatting
- EU taxation policy with per-country VAT rates and VIES reverse-charge validation
- Pluggable exporters: PDF, XLSX, ISDOC XML, MRP v1/v2 XML, IKROS API, Profit365 API
- Asynchronous file exports delivered by email (via ``django-outputs``)
- Django Admin integration — export actions registered automatically for every configured manager

Requirements
------------

- Django 4.2+
- See ``requirements.txt`` for the full dependency list

Development
-----------

::

    pip install -r requirements-test.txt
    pytest

License
-------

See LICENSE file for details.
