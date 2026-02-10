"""
Pytest conftest for invoicing tests (invoicing/tests/).

Path and Django project discovery: pytest.ini sets pythonpath = . and
django_find_project = false. Run pytest from the project root.

This conftest installs outputs/pragmatic mocks before any invoicing imports,
then defines shared fixtures (invoice_factory, item_factory, etc.).
"""
import sys
import types
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from decimal import Decimal


# --- Mocks (before any other invoicing imports) ---

_outputs_pkg = types.ModuleType("outputs")
_outputs_mixins = types.ModuleType("outputs.mixins")
_outputs_models = types.ModuleType("outputs.models")
_outputs_usecases = types.ModuleType("outputs.usecases")
_outputs_signals = types.ModuleType("outputs.signals")


class _DummyExport:
    FORMAT_XML = "xml"
    FORMAT_PDF = "pdf"
    CONTEXT_LIST = "list"
    CONTEXT_DETAIL = "detail"
    RESULT_SUCCESS = "success"
    RESULT_FAILURE = "failure"
    OUTPUT_TYPE_STREAM = "stream"
    STATUS_FINISHED = "finished"
    STATUS_PROCESSING = "processing"
    STATUS_FAILED = "failed"

    def __init__(self):
        self.id = 1
        self.total = 0
        self.status = self.STATUS_FINISHED
        self.exporter = None
        self.content_type = MagicMock()
        self.object_list = []
        self.creator = None
        self.recipients = []
        self.items = MagicMock()

    def save(self, update_fields=None):
        pass

    def update_export_items_result(self, result, detail=None):
        return 0


class _DummyExporterMixin:
    def __init__(self, *args, **kwargs):
        self.queryset = kwargs.get("queryset", None)
        self._items = None
        self.output = MagicMock()
        self.outputs = []

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, value):
        self._items = value
        # Sync queryset so that subclass get_queryset() (which returns
        # self.queryset) sees the assigned items – mirrors real ExporterMixin.
        if value is not None:
            self.queryset = value

    def export(self):
        pass

    def save_export(self):
        return _DummyExport()

    def get_queryset(self):
        return self.queryset


def _dummy_execute_export(exporter, language=None):
    if hasattr(exporter, "export"):
        exporter.export()


def _dummy_mail_successful_export(export, filename=None, zip_file=None):
    pass


def _dummy_notify_about_failed_export(export, error_msg):
    pass


_outputs_mixins.ExporterMixin = _DummyExporterMixin
_outputs_mixins.ExcelExporterMixin = _DummyExporterMixin
_outputs_models.Export = _DummyExport
_outputs_models.ExportItem = _DummyExport
_outputs_usecases.execute_export = _dummy_execute_export
_outputs_usecases.mail_successful_export = _dummy_mail_successful_export
_outputs_usecases.notify_about_failed_export = _dummy_notify_about_failed_export

_outputs_pkg.mixins = _outputs_mixins
_outputs_pkg.models = _outputs_models
_outputs_pkg.usecases = _outputs_usecases

_outputs_signals.export_item_changed = MagicMock()

sys.modules["outputs"] = _outputs_pkg
sys.modules["outputs.mixins"] = _outputs_mixins
sys.modules["outputs.models"] = _outputs_models
sys.modules["outputs.usecases"] = _outputs_usecases
sys.modules["outputs.signals"] = _outputs_signals

_pragmatic_pkg = types.ModuleType("pragmatic")
_pragmatic_utils = types.ModuleType("pragmatic.utils")


def _get_task_decorator(_queue_name):
    def _decorator(fn):
        return fn
    return _decorator


_pragmatic_utils.get_task_decorator = _get_task_decorator
_pragmatic_utils.compress = lambda content: content
_pragmatic_pkg.utils = _pragmatic_utils

sys.modules["pragmatic"] = _pragmatic_pkg
sys.modules["pragmatic.utils"] = _pragmatic_utils


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
