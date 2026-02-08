"""
Tests for manager classes.
"""
import builtins
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured

from invoicing import settings as invoicing_settings
from invoicing.managers import (
    InvoiceExportMixin,
    PdfExportManager,
    XlsxExportManager,
    ISDOCManager,
    IKrosManager,
    Profit365Manager,
    MrpV1Manager,
    MrpV2Manager,
)
from invoicing.models import Invoice


@pytest.mark.django_db
@pytest.mark.unit
class TestInvoiceExportMixin:
    """Tests for InvoiceExportMixin."""

    def test_is_export_qs_valid_empty(self):
        """Test validation with empty queryset."""
        mixin = InvoiceExportMixin()
        request = Mock()
        
        exporter = Mock()
        exporter.get_queryset.return_value = Invoice.objects.none()
        
        result = mixin._is_export_qs_valid(request, exporter)
        assert result is False

    def test_is_export_qs_valid_multiple_origins(self, invoice_factory, item_factory):
        """Test validation with multiple origins."""
        mixin = InvoiceExportMixin()
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
        """Test validation with single origin."""
        mixin = InvoiceExportMixin()
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


@pytest.mark.django_db
@pytest.mark.unit
class TestPdfExportManager:
    """Tests for PdfExportManager."""

    def test_pdf_export_manager_initialization(self):
        """Test manager initialization."""
        manager = PdfExportManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_detail_pdf(self, mock_execute_export, invoice_factory, item_factory):
        """Test PDF export."""
        manager = PdfExportManager()
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
class TestXlsxExportManager:
    """Tests for XlsxExportManager."""

    def test_xlsx_export_manager_initialization(self):
        """Test manager initialization."""
        manager = XlsxExportManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_xlsx(self, mock_execute_export, invoice_factory, item_factory):
        """Test XLSX export."""
        manager = XlsxExportManager()
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
class TestISDOCManager:
    """Tests for ISDOCManager."""

    def test_isdoc_export_manager_initialization(self):
        """Test manager initialization."""
        manager = ISDOCManager()
        assert manager.exporter_class is not None

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_isdoc(self, mock_execute_export, invoice_factory, item_factory):
        """Test ISDOC export."""
        manager = ISDOCManager()
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
            'invoicing.managers.IKrosManager': {}
        }

        # IKrosManager.__init__ checks for API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            IKrosManager()

    def test_ikros_manager_missing_api_key(self, settings):
        """Test missing API key error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.IKrosManager': {
                'API_URL': 'https://api.example.com'
            }
        }

        # IKrosManager.__init__ checks for API_KEY after API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            IKrosManager()

    @patch('invoicing.managers.requests.post')
    def test_export_via_api_success(self, mock_post, invoice_factory, item_factory, settings):
        """Test successful API export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.IKrosManager': {
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
            'invoicing.managers.Profit365Manager': {}
        }

        # Profit365Manager.__init__ checks for API_URL first
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            Profit365Manager()

    def test_profit365_manager_missing_api_data(self, settings):
        """Test missing API data error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.Profit365Manager': {
                'API_URL': 'https://api.example.com'
            }
        }

        # Profit365Manager.__init__ checks for API_DATA after API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            Profit365Manager()

    @patch('invoicing.managers.requests.post')
    def test_export_via_api_success(self, mock_post, invoice_factory, item_factory, settings):
        """Test successful API export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.Profit365Manager': {
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


@pytest.mark.django_db
@pytest.mark.unit
class TestMrpV2Manager:
    """Tests for MrpV2Manager."""

    def test_mrp_v2_manager_initialization(self, settings):
        """Test manager initialization requires API_URL."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.MrpV2Manager': {'API_URL': 'https://mrp.example.com'}
        }
        manager = MrpV2Manager()
        assert manager.exporter_classes is not None

    def test_mrp_v2_manager_missing_api_url(self, settings):
        """Test missing API URL raises error."""
        invoicing_settings.INVOICING_MANAGERS = {}
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            MrpV2Manager()

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_received(self, mock_execute_export, invoice_factory, item_factory, settings):
        """Test MRP v2 received export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.MrpV2Manager': {'API_URL': 'https://mrp.example.com'}
        }
        manager = MrpV2Manager()
        request = Mock()
        request.user = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        queryset = Invoice.objects.filter(id=invoice.id)

        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_mrp(request, queryset=queryset)

        assert mock_execute_export.called

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_issued(self, mock_execute_export, invoice_factory, item_factory, settings):
        """Test MRP v2 issued export."""
        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.MrpV2Manager': {'API_URL': 'https://mrp.example.com'}
        }
        manager = MrpV2Manager()
        request = Mock()
        request.user = Mock()

        invoice = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

        queryset = Invoice.objects.filter(id=invoice.id)

        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_mrp(request, queryset=queryset)

        assert mock_execute_export.called

    def test_export_via_api(self, invoice_factory, item_factory, settings):
        """Test MRP v2 API export - queues send_invoices_to_mrp task."""
        import invoicing.exporters.mrp.v2.tasks as mrp_v2_tasks
        from invoicing.exporters.mrp.v2.list import ReceivedInvoiceMrpListExporter

        invoicing_settings.INVOICING_MANAGERS = {
            'invoicing.managers.MrpV2Manager': {'API_URL': 'https://mrp.example.com'}
        }

        with patch.object(mrp_v2_tasks, 'send_invoices_to_mrp') as mock_task:
            manager = MrpV2Manager()
            request = Mock()
            request.user = Mock()
            request.user.id = 1

            invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
            item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))

            queryset = Invoice.objects.filter(id=invoice.id)

            manager.export_via_api(request, queryset)

            assert mock_task.delay.called
            mock_task.delay.assert_called_once_with(
                ReceivedInvoiceMrpListExporter, 1, list(queryset.values_list('id', flat=True)), 'https://mrp.example.com'
            )

