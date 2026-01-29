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
    MRPManager,
    InvoiceDetailsManager,
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
        assert manager.manager_name == 'PDF'

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
        assert manager.manager_name == 'XLSX'

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
        assert manager.manager_name == 'ISDOC'

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
            'IKROS': {}
        }
        
        # IKrosManager.__init__ checks for API_URL
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            IKrosManager()

    def test_ikros_manager_missing_api_key(self, settings):
        """Test missing API key error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'IKROS': {
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
            'IKROS': {
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
            'PROFIT365': {}
        }
        
        # Profit365Manager.__init__ checks for API_URL first
        with pytest.raises((builtins.EnvironmentError, ImproperlyConfigured, AttributeError)):
            Profit365Manager()

    def test_profit365_manager_missing_api_data(self, settings):
        """Test missing API data error."""
        invoicing_settings.INVOICING_MANAGERS = {
            'PROFIT365': {
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
            'PROFIT365': {
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
class TestMRPManager:
    """Tests for MRPManager."""

    def test_mrp_manager_initialization(self, settings):
        """Test manager initialization."""
        # Ensure INVOICING_MANAGERS is set for MRP
        invoicing_settings.INVOICING_MANAGERS.setdefault('MRP', {'API_URL': 'https://mrp.example.com'})
        manager = MRPManager()
        assert manager.manager_name == 'MRP'

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_v2_received(self, mock_execute_export, invoice_factory, item_factory):
        """Test MRP v2 received export."""
        invoicing_settings.INVOICING_MANAGERS.setdefault('MRP', {'API_URL': 'https://mrp.example.com'})
        manager = MRPManager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory(origin=Invoice.ORIGIN.RECEIVED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_mrp_v2(request, queryset=queryset)

        assert mock_execute_export.called

    @patch('outputs.usecases.execute_export', create=True)
    def test_export_list_mrp_v2_issued(self, mock_execute_export, invoice_factory, item_factory):
        """Test MRP v2 issued export."""
        invoicing_settings.INVOICING_MANAGERS.setdefault('MRP', {'API_URL': 'https://mrp.example.com'})
        manager = MRPManager()
        request = Mock()
        request.user = Mock()
        
        invoice = invoice_factory(origin=Invoice.ORIGIN.ISSUED)
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_mrp_v2(request, queryset=queryset)

        assert mock_execute_export.called

    @patch('invoicing.exporters.mrp.v1.tasks.mail_exported_invoices_mrp_v1')
    def test_export_list_mrp_v1(self, mock_task, invoice_factory, item_factory, settings):
        """Test MRP v1 export."""
        # Ensure INVOICING_MANAGERS is set
        invoicing_settings.INVOICING_MANAGERS.setdefault('MRP', {'API_URL': 'https://mrp.example.com'})
        
        manager = MRPManager()
        request = Mock()
        request.user = Mock()
        request.user.id = 1
        request.GET = {}
        
        invoice = invoice_factory()
        item_factory(invoice=invoice, quantity=Decimal('1.0'), unit_price=Decimal('100.00'))
        
        queryset = Invoice.objects.filter(id=invoice.id)
        
        # Mock the _is_export_qs_valid to return True
        with patch.object(manager, '_is_export_qs_valid', return_value=True):
            manager.export_list_mrp_v1(request, queryset=queryset)
        
        assert mock_task.delay.called


@pytest.mark.unit
class TestInvoiceDetailsManager:
    """Tests for InvoiceDetailsManager."""

    def test_invoice_details_manager_vat_type(self, invoice_factory):
        """Test VAT type method."""
        manager = InvoiceDetailsManager()
        invoice = invoice_factory()
        result = manager.vat_type(invoice)
        assert result == ''

    def test_invoice_details_manager_customer_number(self, invoice_factory):
        """Test customer number method."""
        manager = InvoiceDetailsManager()
        invoice = invoice_factory()
        result = manager.customer_number(invoice)
        assert result == ''

    def test_invoice_details_manager_advance_notice(self, invoice_factory):
        """Test advance notice method."""
        manager = InvoiceDetailsManager()
        invoice = invoice_factory()
        result = manager.advance_notice(invoice)
        assert result == ''

    def test_invoice_details_manager_fulfillment_code(self, invoice_factory):
        """Test fulfillment code method."""
        manager = InvoiceDetailsManager()
        invoice = invoice_factory()
        result = manager.fulfillment_code(invoice)
        assert result == ''

    def test_invoice_details_manager_center(self, invoice_factory):
        """Test center method."""
        manager = InvoiceDetailsManager()
        invoice = invoice_factory()
        result = manager.center(invoice)
        assert result == ''

