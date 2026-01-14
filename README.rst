django-invoicing
================

Django app for invoicing with support for multiple export formats and integrations.

Installation
------------

1. Install the package::

    pip install django-invoicing

2. Add ``invoicing`` to your ``INSTALLED_APPS`` in settings.py::

    INSTALLED_APPS = [
        ...
        'invoicing',
        ...
    ]

3. Run migrations::

    python manage.py migrate invoicing


Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

The app comes with three core managers configured by default:

- **DETAILS**: Invoice details manager
- **PDF**: PDF export manager  
- **XLSX**: Excel export manager

No additional configuration is required for these core managers.


Advanced Manager Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To use additional managers (MRP, ISDOC, IKROS, PROFIT365), add the ``INVOICING_MANAGERS`` setting to your Django settings.py:

**Example with all available managers:**

.. code-block:: python

    INVOICING_MANAGERS = {
        # Core managers (included by default)
        "DETAILS": {
            "MANAGER_CLASS": "invoicing.managers.InvoiceDetailsManager",
        },
        "PDF": {
            "MANAGER_CLASS": "invoicing.managers.PdfExportManager",
        },
        "XLSX": {
            "MANAGER_CLASS": "invoicing.managers.XlsxExportManager",
        },
        
        # Additional managers (configure as needed)
        "MRP": {
            "MANAGER_CLASS": "invoicing.managers.MRPManager",
            "API_URL": 'https://your-mrp-api.example.com/api/',
        },
        "ISDOC": {
            "MANAGER_CLASS": "invoicing.managers.ISDOCManager",
        },
        "IKROS": {
            "MANAGER_CLASS": "invoicing.managers.IKrosManager",
            "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
            "API_KEY": "your-api-key-here",
        },
        "PROFIT365": {
            "MANAGER_CLASS": "invoicing.managers.Profit365Manager",
            "API_URL": "https://api.profit365.eu/1.6",
            "API_DATA": {
                "Authorization": "Bearer your-token",
                "bankAccountId": "12345",
                "ClientID": "your-client-id",
                "ClientSecret": "your-client-secret",
                "CompanyID": "your-company-id",
            },
        },
    }


Individual Manager Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**MRP Manager** (Czech accounting system):

.. code-block:: python

    INVOICING_MANAGERS = {
        "MRP": {
            "MANAGER_CLASS": "invoicing.managers.MRPManager",
            "API_URL": "https://your-mrp-instance.example.com/api/",
        },
    }

**ISDOC Manager** (Czech electronic invoice format):

.. code-block:: python

    INVOICING_MANAGERS = {
        "ISDOC": {
            "MANAGER_CLASS": "invoicing.managers.ISDOCManager",
        },
    }

**IKROS Manager** (Slovak accounting system):

.. code-block:: python

    INVOICING_MANAGERS = {
        "IKROS": {
            "MANAGER_CLASS": "invoicing.managers.IKrosManager",
            "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
            "API_KEY": "your-api-key-here",
        },
    }

**PROFIT365 Manager** (European accounting system):

.. code-block:: python

    INVOICING_MANAGERS = {
        "PROFIT365": {
            "MANAGER_CLASS": "invoicing.managers.Profit365Manager",
            "API_URL": "https://api.profit365.eu/1.6",
            "API_DATA": {
                "Authorization": "Bearer your-token",
                "bankAccountId": "12345",
                "ClientID": "your-client-id",
                "ClientSecret": "your-client-secret",
                "CompanyID": "your-company-id",
            },
        },
    }


Usage
-----

The managers integrate with Django Admin. Once configured, export actions will be available in the Invoice admin interface.

**Available export formats:**

- PDF invoices
- Excel (XLSX) spreadsheets
- MRP XML exports (v1 and v2)
- ISDOC XML format
- Direct API integration with IKROS
- Direct API integration with PROFIT365

**Django Admin Integration:**

1. Navigate to the Invoice admin page
2. Select invoices to export
3. Choose an export action from the actions dropdown
4. The export will be processed and sent to your email


Features
--------

- Multiple invoice export formats
- Asynchronous export processing
- Email delivery of exports
- Support for multiple languages
- VAT calculation and taxation
- Credit notes support
- Invoice sequences and numbering
- Related invoices tracking
- Attachment support


Requirements
------------

See ``requirements.txt`` for the full list of dependencies.


Development
-----------

To set up a development environment::

    # Create virtual environment
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    
    # Install development dependencies
    pip install -r requirements-dev.txt
    
    # Run tests
    pytest


License
-------

See LICENSE file for details.
