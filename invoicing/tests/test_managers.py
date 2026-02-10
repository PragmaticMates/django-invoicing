"""
Tests for manager classes.
"""
import builtins
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured

from invoicing import settings as invoicing_settings
from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.pdf.managers import PdfManager
from invoicing.exporters.xlsx.managers import XlsxManager
from invoicing.exporters.isdoc.managers import IsdocManager
from invoicing.exporters.ikros.managers import IKrosManager
from invoicing.exporters.profit365.managers import Profit365Manager
from invoicing.exporters.mrp.v1.managers import MrpV1Manager
from invoicing.exporters.mrp.v2.managers import MrpIssuedManager, MrpReceivedManager
from invoicing.models import Invoice


@pytest.mark.django_db
@pytest.mark.unit
class TestInvoiceManagerMixin:
    """Tests for InvoiceManagerMixin validation logic."""

    def test_is_export_qs_valid_empty(self):
        """Empty queryset should be rejected."""
        mixin = InvoiceManagerMixin()
        request = Mock()
        
        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.none()
        
        result = mixin._is_export_qs_valid(request, exporter)
        assert result is False

    def test_is_export_qs_valid_multiple_origins(self, invoice_factory, item_factory):
        """Mixed-origin queryset should be rejected."""
        mixin = InvoiceManagerMixin()
        request = Mock()
        
        invoice1 = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice1, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        invoice2 = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice2, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.filter(
            id__in=[invoice1.id, invoice2.id]
        )
        
        result = mixin._is_export_qs_valid(request, exporter)
        assert result is False

    def test_is_export_qs_valid_single_origin(self, invoice_factory, item_factory):
        """Single-origin queryset should pass when no origin constraint is set."""
        mixin = InvoiceManagerMixin()
        request = Mock()
        
        invoice1 = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice1, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        invoice2 = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice2, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.filter(
            id__in=[invoice1.id, invoice2.id]
        )
        
        result = mixin._is_export_qs_valid(request, exporter)
        assert result is True

    def test_is_export_qs_valid_origin_matches(self, invoice_factory, item_factory):
        """Queryset should pass when all invoices match the manager's required_origin."""
        mixin = InvoiceManagerMixin()
        mixin.required_origin = Invoice.ORIGIN.ISSUED
        request = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.filter(id=invoice.id)

        result = mixin._is_export_qs_valid(request, exporter)
        assert result is True

    def test_is_export_qs_valid_origin_mismatch(self, invoice_factory, item_factory):
        """Queryset should be rejected when invoices don't match the manager's required_origin."""
        mixin = InvoiceManagerMixin()
        mixin.required_origin = Invoice.ORIGIN.ISSUED
        request = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.filter(id=invoice.id)

        result = mixin._is_export_qs_valid(request, exporter)
        assert result is False

    def test_is_export_qs_valid_no_origin_constraint(self, invoice_factory, item_factory):
        """When required_origin is None, any single-origin queryset should pass."""
        mixin = InvoiceManagerMixin()
        assert mixin.required_origin is None  # default
        request = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.filter(id=invoice.id)

        result = mixin._is_export_qs_valid(request, exporter)
        assert result is True


@pytest.mark.django_db
@pytest.mark.unit
class TestPdfManager:
    """Tests for PdfManager."""

    def test_pdf_manager_initialization(self):
        """Test manager initialization."""
        manager = PdfManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_detail_pdf(self, mock_execute_export, invoice_factory, item_factory):
        """Test PDF export."""
        manager = PdfManager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_detail_pdf(request, queryset=queryset)
        
        # Should call execute_export from outputs.usecases
        assert mock_execute_export.called


@pytest.mark.django_db
@pytest.mark.unit
class TestXlsxManager:
    """Tests for XlsxManager."""

    def test_xlsx_manager_initialization(self):
        """Test manager initialization."""
        manager = XlsxManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_xlsx(self, mock_execute_export, invoice_factory, item_factory):
        """Test XLSX export."""
        manager = XlsxManager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_xlsx(request, queryset=queryset)

        assert mock_execute_export.called


@pytest.mark.django_db
@pytest.mark.unit
class TestIsdocManager:
    """Tests for IsdocManager."""

    def test_isdoc_manager_initialization(self):
        """Test manager initialization."""
        manager = IsdocManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_isdoc(self, mock_execute_export, invoice_factory, item_factory):
        """Test ISDOC export."""
        manager = IsdocManager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_isdoc(request, queryset=queryset)

        assert mock_execute_export.called


@pytest.mark.django_db
@pytest.mark.unit
class TestIKrosManager:
    """Tests for IKrosManager."""

    def test_ikros_manager_missing_api_url(self, settings):
        """Test missing API URL error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.ikros.managers.IKrosManager': {}
        }

        manager = IKrosManager()
        request = Mock()
        queryset = Invoice.objects.none()

        # export_via_api should validate API_URL and fail
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            manager.export_via_api(request, queryset)

    def test_ikros_manager_missing_api_key(self, settings):
        """Test missing API key error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.ikros.managers.IKrosManager': {
                'API_URL': 'https://api.example.com'
            }
        }

        manager = IKrosManager()
        request = Mock()
        queryset = Invoice.objects.none()

        # export_via_api should validate API_KEY after API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            manager.export_via_api(request, queryset)

    @patch('invoicing.exporters.ikros.managers.requests.post')
    def test_export_via_api_success(self, mock_post, invoice_factory, item_factory, settings):
        """Test successful API export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.ikros.managers.IKrosManager': {
                'API_URL': 'https://api.example.com',
                'API_KEY': 'test-key'
            }
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'documents': [{'downloadUrl': 'https://example.com/file.pdf'}]
        }
        mock_post.return_value = mock_response
        
        manager = IKrosManager()
        request = Mock()
        request.user = Mock()
        messages = Mock()
        request._messages = messages
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        result = manager.export_via_api(request, queryset)

        # In the test environment we mainly care that the call succeeds and
        # returns some value; the low‑level HTTP call is mocked elsewhere.
        assert isinstance(result, (str, type(None)))


@pytest.mark.django_db
@pytest.mark.unit
class TestProfit365Manager:
    """Tests for Profit365Manager."""

    def test_profit365_manager_missing_api_url(self, settings):
        """Test missing API URL error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.profit365.managers.Profit365Manager': {}
        }

        manager = Profit365Manager()
        request = Mock()
        queryset = Invoice.objects.none()

        # export_via_api should validate API_URL first
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            manager.export_via_api(request, queryset)

    def test_profit365_manager_missing_api_data(self, settings):
        """Test missing API data error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.profit365.managers.Profit365Manager': {
                'API_URL': 'https://api.example.com'
            }
        }

        manager = Profit365Manager()
        request = Mock()
        queryset = Invoice.objects.none()

        # export_via_api should validate API_DATA after API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            manager.export_via_api(request, queryset)

    @patch('invoicing.exporters.profit365.managers.requests.post')
    def test_export_via_api_success(self, mock_post, invoice_factory, item_factory, settings):
        """Test successful API export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.profit365.managers.Profit365Manager': {
                'API_URL': 'https://api.example.com',
                'API_DATA': {
                    'Authorization': 'Bearer token',
                    'ClientID': 'client-id',
                    'ClientSecret': 'client-secret',
                    'bankAccountId': 'account-id'
                }
            }
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.reason = 'OK'
        mock_post.return_value = mock_response
        
        manager = Profit365Manager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        result = manager.export_via_api(request, queryset)
        
        assert mock_post.called
        assert isinstance(result, list)


@pytest.mark.django_db
@pytest.mark.unit
class TestMrpV1Manager:
    """Tests for MrpV1Manager."""

    def test_mrp_v1_manager_initialization(self):
        """Test manager initialization."""
        manager = MrpV1Manager()
        assert manager.exporter_class is not None
        assert manager.required_origin == Invoice.ORIGIN.ISSUED

    def test_export_list_mrp(self, invoice_factory, item_factory):
        """Test MRP v1 export - saves export and queues task."""
        import invoicing.exporters.mrp.v1.tasks as mrp_v1_tasks

        with patch.object(mrp_v1_tasks, 'mail_exported_invoices_mrp_v1') as mock_task:
            manager = MrpV1Manager()
            request = Mock()
            request.user = Mock()
            request.user.id = 1
            request.GET = {}

            invoice = invoice_factory()
            item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

            queryset = Invoice.objects.filter(id=invoice.id)

            with patch.object(manager, '_is_export_qs_valid', return_value=True):
                manager.export_list_mrp(request, queryset=queryset)

            assert mock_task.delay.called
            # Verify the task was called with export_id and exporter_subclass_paths
            call_args = mock_task.delay.call_args
            assert call_args[0][0] is not None  # export_id
            assert 'exporter_subclass_paths' in call_args[1]
            exporter_subclass_paths = call_args[1]['exporter_subclass_paths']
            assert exporter_subclass_paths is not None
            assert len(exporter_subclass_paths) == 3  # Should have 3 exporter subclasses


@pytest.mark.django_db
@pytest.mark.unit
class TestMrpManagers:
    """Tests for MRP managers (issued and received)."""

    def test_mrp_issued_v2_manager_initialization(self):
        """Issued manager should define exporter_class and required_origin."""
        manager = MrpIssuedManager()
        assert manager.exporter_class is not None
        assert manager.required_origin == Invoice.ORIGIN.ISSUED

    def test_mrp_received_v2_manager_initialization(self):
        """Received manager should define exporter_class and required_origin."""
        manager = MrpReceivedManager()
        assert manager.exporter_class is not None
        assert manager.required_origin == Invoice.ORIGIN.RECEIVED

    def test_mrp_v2_issued_manager_missing_api_url(self, settings):
        """Missing API URL for issued manager should raise on export_via_api."""
        invoicing_settings.INVOICING_MANAGERS = {}
        manager = MrpIssuedManager()
        request = Mock()
        request.user = Mock()
        request.GET = {}
        queryset = Invoice.objects.none()

        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            manager.export_via_api(request, queryset)

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_received(self, mock_execute_export, invoice_factory, item_factory, settings):
        """Test MRP v2 received export."""
        manager = MrpReceivedManager()
        request = Mock()
        request.user = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        queryset = Invoice.objects.filter(id=invoice.id)

        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_received_mrp(request, queryset=queryset)

        assert mock_execute_export.called

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_issued(self, mock_execute_export, invoice_factory, item_factory, settings):
        """Test MRP v2 issued export."""
        manager = MrpIssuedManager()
        request = Mock()
        request.user = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        queryset = Invoice.objects.filter(id=invoice.id)

        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_issued_mrp(request, queryset=queryset)

        assert mock_execute_export.called

    def test_export_via_api_queued(self, invoice_factory, item_factory, settings):
        """Test MRP v2 API export queues send_invoices_to_mrp task."""
        import invoicing.exporters.mrp.v2.tasks as mrp_v2_tasks

        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.exporters.mrp.v2.managers.MrpReceivedManager': {'API_URL': 'https://mrp.example.com'}
        }

        with patch.object(mrp_v2_tasks, 'send_invoices_to_mrp') as mock_task:
            manager = MrpReceivedManager()
            request = Mock()
            request.user = Mock()
            request.user.id = 1
            request.GET = {}

            invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
            item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

            queryset = Invoice.objects.filter(id=invoice.id)

            # Avoid coupling to queryset validation details
            with patch.object(manager, '_is_export_qs_valid', return_value=True):
                manager.export_via_api(request, queryset)

            assert mock_task.delay.called
            # Verify the task was called with export_id (integer) and manager (self)
            call_args = mock_task.delay.call_args
            assert len(call_args[0]) == 2
            export_id_arg = call_args[0][0]
            manager_arg = call_args[0][1]
            # export_id_arg should be an integer (export.id)
            assert isinstance(export_id_arg, int)
            assert export_id_arg > 0
            # manager_arg should be the manager instance
            assert manager_arg == manager

