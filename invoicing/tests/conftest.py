"""
Pytest conftest for invoicing tests (invoicing/tests/).

Path and Django project discovery: pytest.ini sets pythonpath = . and
django_find_project = false. Run pytest from the project root.

Mocking strategy
----------------
outputs.models / outputs.mixins / outputs.jobs  → real package (3.0.0)
    Tests use the real ExporterMixin, Export and ExportItem models, and the
    real execute_export job body (save_export pipeline) where tests run it
    synchronously.  The test database is
    PostgreSQL, which is required by Export.fields/emails (ArrayField columns).

outputs.signals  → mocked
    signals.py imports django_rq at module level and registers a post_save
    handler on Export that calls django_rq.get_scheduler().  That needs a
    live Redis connection.  Keeping signals mocked avoids Redis entirely while
    still letting invoicing/exporters/mrp/v2/tasks.py obtain a usable
    export_item_changed signal object.

pragmatic  → partially mocked
    pragmatic.utils.get_task_decorator    – would wrap MRP tasks as RQ jobs
    pragmatic.forms.SingleSubmitFormHelper – used by outputs.forms (UI only)
    pragmatic.signals.*                    – imported by outputs.signals mock
    pragmatic.templatetags.pragmatic_tags  – imported by outputs.mixins
    All of the above are mocked with no-op stubs so the real outputs package
    can be imported without needing django-pragmatic fully configured.
"""
import sys
import types
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from decimal import Decimal


# ---------------------------------------------------------------------------
# outputs.signals  (mocked to avoid django_rq / Redis dependency)
# ---------------------------------------------------------------------------

_outputs_signals = types.ModuleType("outputs.signals")
_outputs_signals.export_item_changed = MagicMock()
sys.modules["outputs.signals"] = _outputs_signals


# ---------------------------------------------------------------------------
# pragmatic stubs  (no-op implementations of the parts outputs uses)
# ---------------------------------------------------------------------------

_pragmatic_pkg = types.ModuleType("pragmatic")
_pragmatic_utils = types.ModuleType("pragmatic.utils")
_pragmatic_forms = types.ModuleType("pragmatic.forms")
_pragmatic_signals = types.ModuleType("pragmatic.signals")
_pragmatic_templatetags = types.ModuleType("pragmatic.templatetags")
_pragmatic_tags = types.ModuleType("pragmatic.templatetags.pragmatic_tags")


def _get_task_decorator(_queue_name):
    """Make the RQ @task decorator a plain no-op so MRP tasks stay synchronous."""
    def _decorator(fn):
        return fn
    return _decorator


def _dispatch_task(task, *args, **kwargs):
    """Mirror pragmatic task dispatch while keeping tests synchronous."""
    if hasattr(task, "delay"):
        return task.delay(*args, **kwargs)
    return task(*args, **kwargs)


_pragmatic_utils.get_task_decorator = _get_task_decorator
_pragmatic_utils.dispatch_task = _dispatch_task
_pragmatic_utils.compress = lambda content: content


class _DummyFormHelper:
    """Minimal crispy-forms helper stub (only layout/submit attrs used)."""
    def __init__(self, *args, **kwargs):
        pass

    def add_input(self, *args, **kwargs):
        pass


_pragmatic_forms.SingleSubmitFormHelper = _DummyFormHelper


class _DummySignalsHelper:
    @staticmethod
    def attribute_changed(*args, **kwargs):
        return False

    @staticmethod
    def add_task_and_connect(*args, **kwargs):
        pass


def _dummy_apm_custom_context(*args, **kwargs):
    """Stub for the APM context decorator used by outputs.signals."""
    def decorator(fn):
        return fn
    return decorator


_pragmatic_signals.SignalsHelper = _DummySignalsHelper
_pragmatic_signals.apm_custom_context = _dummy_apm_custom_context

_pragmatic_tags.filtered_values = lambda *args, **kwargs: []

_pragmatic_pkg.utils = _pragmatic_utils
_pragmatic_pkg.forms = _pragmatic_forms
_pragmatic_pkg.signals = _pragmatic_signals
_pragmatic_pkg.templatetags = _pragmatic_templatetags

sys.modules["pragmatic"] = _pragmatic_pkg
sys.modules["pragmatic.utils"] = _pragmatic_utils
sys.modules["pragmatic.forms"] = _pragmatic_forms
sys.modules["pragmatic.signals"] = _pragmatic_signals
sys.modules["pragmatic.templatetags"] = _pragmatic_templatetags
sys.modules["pragmatic.templatetags.pragmatic_tags"] = _pragmatic_tags


# --- Fixtures (invoicing imports after mocks) ---

from invoicing.models import Invoice, Item


@pytest.fixture
def settings_override(settings):
    """Override Django settings for tests."""
    settings.INVOICING_COUNTER_PERIOD = 'YEARLY'
    settings.INVOICING_NUMBER_START_FROM = 1
    settings.INVOICING_NUMBER_FORMAT = "{{ invoice.date_issue|date:'Y' }}/{{ invoice.sequence }}"
    settings.INVOICING_TAX_RATE = Decimal(20)
    return settings


@pytest.fixture
def settings_daily_counter(settings):
    """Settings with daily counter period."""
    settings.INVOICING_COUNTER_PERIOD = 'DAILY'
    return settings


@pytest.fixture
def settings_monthly_counter(settings):
    """Settings with monthly counter period."""
    settings.INVOICING_COUNTER_PERIOD = 'MONTHLY'
    return settings


@pytest.fixture
def settings_yearly_counter(settings):
    """Settings with yearly counter period."""
    settings.INVOICING_COUNTER_PERIOD = 'YEARLY'
    return settings


@pytest.fixture
def invoice_factory(db):
    """Factory function for creating Invoice instances."""
    def _create_invoice(**kwargs):
        defaults = {
            'type': Invoice.TYPE.INVOICE,
            'status': Invoice.STATUS.NEW,
            'language': 'en',
            'date_issue': date.today(),
            'date_tax_point': date.today(),
            'date_due': date.today() + timedelta(days=30),
            'currency': 'EUR',
            'supplier_name': 'Test Supplier Ltd.',
            'supplier_street': 'Supplier Street 1',
            'supplier_zip': '12345',
            'supplier_city': 'Supplier City',
            'supplier_country': 'SK',
            'supplier_vat_id': 'SK1234567890',
            'customer_name': 'Test Customer Ltd.',
            'customer_street': 'Customer Street 1',
            'customer_zip': '54321',
            'customer_city': 'Customer City',
            'customer_country': 'SK',
            'payment_method': Invoice.PAYMENT_METHOD.BANK_TRANSFER,
            'delivery_method': Invoice.DELIVERY_METHOD.DIGITAL,
            'bank_name': 'Test Bank',
            'bank_iban': 'SK0000000000000000000028',
            'bank_swift_bic': 'TESTBANK',
            'total': Decimal('0.00'),
            'vat': Decimal('0.00'),
            'credit': Decimal('0.00'),
            'already_paid': Decimal('0.00'),
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)
    return _create_invoice


@pytest.fixture
def item_factory(db):
    """Factory function for creating Item instances."""
    def _create_item(invoice, **kwargs):
        defaults = {
            'title': 'Test Item',
            'quantity': Decimal('1.00'),
            'unit': Item.UNIT_PIECES,
            'unit_price': Decimal('100.00'),
            'discount': Decimal('0.0'),
            'tax_rate': Decimal('20.0'),
            'weight': 0,
        }
        defaults.update(kwargs)
        return Item.objects.create(invoice=invoice, **defaults)
    return _create_item


@pytest.fixture
def sample_invoice(invoice_factory, item_factory):
    """Create a sample invoice with items."""
    invoice = invoice_factory()
    item_factory(invoice=invoice, title='Item 1', quantity=Decimal('2.0'), unit_price=Decimal('50.00'))
    item_factory(invoice=invoice, title='Item 2', quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
    invoice.calculate_total()
    return invoice


@pytest.fixture
def sample_invoice_eu(invoice_factory, item_factory):
    """Create a sample EU invoice with different supplier and customer countries."""
    invoice = invoice_factory(
        supplier_country='SK',
        customer_country='CZ',
        supplier_vat_id='SK1234567890',
        customer_vat_id='CZ1234567890',
    )
    item_factory(invoice=invoice, title='EU Item 1', quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
    invoice.calculate_total()
    return invoice


@pytest.fixture
def sample_invoice_with_discount(invoice_factory, item_factory):
    """Create a sample invoice with discount."""
    invoice = invoice_factory()
    item_factory(
        invoice=invoice,
        title='Discounted Item',
        quantity=Decimal('1.0'),
        unit_price=Decimal('100.00'),
        discount=Decimal('10.0')
    )
    invoice.calculate_total()
    return invoice


@pytest.fixture
def sample_invoice_paid(invoice_factory, item_factory):
    """Create a paid invoice."""
    invoice = invoice_factory(status=Invoice.STATUS.PAID)
    item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
    invoice.calculate_total()
    invoice.already_paid = invoice.total
    invoice.save()
    return invoice


@pytest.fixture
def sample_invoice_overdue(invoice_factory, item_factory):
    """Create an overdue invoice."""
    invoice = invoice_factory(
        status=Invoice.STATUS.SENT,
        date_due=date.today() - timedelta(days=10),
    )
    item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
    invoice.calculate_total()
    return invoice


@pytest.fixture
def sample_credit_note(invoice_factory, item_factory):
    """Create a credit note."""
    invoice = invoice_factory(type=Invoice.TYPE.CREDIT_NOTE)
    item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
    invoice.calculate_total()
    return invoice


@pytest.fixture
def frozen_date():
    """Freeze date for consistent testing."""
    from freezegun import freeze_time
    with freeze_time('2024-01-15'):
        yield


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests library for API tests."""
    import requests
    from unittest.mock import Mock

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'status': 'success', 'documents': []}
    mock_response.reason = 'OK'
    mock_response.text = 'OK'

    mock_post = Mock(return_value=mock_response)
    monkeypatch.setattr(requests, 'post', mock_post)

    return mock_post


@pytest.fixture
def mock_vies_validator(monkeypatch):
    """Mock VIES VAT validator."""
    from unittest.mock import Mock

    def mock_validator(*args, **kwargs):
        validator = Mock()
        return validator

    monkeypatch.setattr('invoicing.taxation.eu.VATNumberValidator', mock_validator)
    return mock_validator
