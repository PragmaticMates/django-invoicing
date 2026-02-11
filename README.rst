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

The app comes with two core managers configured by default:

- **PdfManager**: PDF export manager  
- **XlsxManager**: Excel export manager

No additional configuration is required for these core managers.


Advanced Manager Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To use additional managers (MRP, ISDOC, IKROS, PROFIT365), add the ``INVOICING_MANAGERS`` setting to your Django settings.py.

**Configuration Format (basic):**

Managers are configured using their full module path as the dictionary key. The value is a dictionary containing the manager-specific configuration (empty dict ``{}`` if no configuration is needed).

**Example with all available managers:**

.. code-block:: python

    INVOICING_MANAGERS = {
        # Core managers (included by default)
        "invoicing.exporters.pdf.managers.PdfManager": {},
        "invoicing.exporters.xlsx.managers.XlsxManager": {},
        
        # Additional managers (configure as needed)
        "invoicing.exporters.isdoc.managers.IsdocManager": {},
        "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {},
        "invoicing.exporters.mrp.v2.managers.MrpIssuedManager": {
            "API_URL": "https://your-mrp-api.example.com/api/",
        },
        "invoicing.exporters.mrp.v2.managers.MrpReceivedManager": {
            "API_URL": "https://your-mrp-api.example.com/api/",
        },
        "invoicing.exporters.ikros.managers.IKrosManager": {
            "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
            "API_KEY": "your-api-key-here",
        },
        "invoicing.exporters.profit365.managers.Profit365Manager": {
            "API_URL": "https://api.profit365.eu/1.6",
            "API_DATA": {
                "Authorization": "Bearer your-token",
                "bankAccountId": "12345",
                "ClientID": "your-client-id",
                "ClientSecret": "your-client-secret",
                "CompanyID": "your-company-id",  # Optional
            },
        },
    }


Overriding exporter classes (advanced)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, each manager uses a built‑in exporter class (and, where applicable, a
set of exporter subclasses). For advanced use cases you can override these via
settings using dotted import paths:

- **exporter_class**: dotted path to the main exporter class
- **exporter_subclasses**: list of dotted paths to exporter subclasses (used by some managers, e.g. MRP v1)

Example:

.. code-block:: python

    INVOICING_MANAGERS = {
        # Override the exporter used by PdfManager
        "invoicing.exporters.pdf.managers.PdfManager": {
            "exporter_class": "yourapp.exporters.CustomPdfExporter",
        },

        # Override main exporter and subclasses for MRP v1 manager
        "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {
            "exporter_class": "invoicing.exporters.mrp.v1.list.InvoiceXmlMrpListExporter",
            "exporter_subclasses": [
                "invoicing.exporters.mrp.v1.list.InvoiceFakvyXmlMrpExporter",
                "invoicing.exporters.mrp.v1.list.InvoiceFakvypolXmlMrpExporter",
                "invoicing.exporters.mrp.v1.list.InvoiceFvAdresXmlMrpExporter",
            ],
        },
    }


Individual Manager Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**PDF Manager** (no configuration needed):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.pdf.managers.PdfManager": {},
    }

**XLSX Manager** (no configuration needed):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.xlsx.managers.XlsxManager": {},
    }

**ISDOC Manager** (Czech electronic invoice format, no configuration needed):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.isdoc.managers.IsdocManager": {},
    }

**MRP v1 Manager** (Czech accounting system, no configuration needed):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.mrp.v1.managers.MrpV1Manager": {},
    }

**MRP Managers** (Czech accounting system, require API_URL per manager):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.mrp.v2.managers.MrpIssuedManager": {
            "API_URL": "https://your-mrp-instance.example.com/api/",
        },
        "invoicing.exporters.mrp.v2.managers.MrpReceivedManager": {
            "API_URL": "https://your-mrp-instance.example.com/api/",
        },
    }

**IKROS Manager** (Slovak accounting system, requires API_URL and API_KEY):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.ikros.managers.IKrosManager": {
            "API_URL": "https://eshops.inteo.sk/api/v1/invoices/",
            "API_KEY": "your-api-key-here",
        },
    }

**PROFIT365 Manager** (European accounting system, requires API_URL and API_DATA):

.. code-block:: python

    INVOICING_MANAGERS = {
        "invoicing.exporters.profit365.managers.Profit365Manager": {
            "API_URL": "https://api.profit365.eu/1.6",
            "API_DATA": {
                "Authorization": "Bearer your-token",
                "bankAccountId": "12345",
                "ClientID": "your-client-id",
                "ClientSecret": "your-client-secret",
                "CompanyID": "your-company-id",  # Optional
            },
        },
    }


Usage
-----

The managers integrate with Django Admin. Once configured, export actions will be available in the Invoice admin interface.

**Available export formats:**

- PDF invoices (PdfManager)
- Excel (XLSX) spreadsheets (XlsxManager)
- MRP XML exports v1 (MrpV1Manager)
- MRP XML exports v2 (MrpIssuedManager / MrpReceivedManager) - support both email export and API export
- ISDOC XML format (IsdocManager)
- Direct API integration with IKROS (IKrosManager)
- Direct API integration with PROFIT365 (Profit365Manager)

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
