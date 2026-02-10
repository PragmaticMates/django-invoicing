"""
Tests for formatters.
"""
import pytest
from django.http import HttpResponse

from invoicing.formatters.html import HTMLFormatter, BootstrapHTMLFormatter
from invoicing.models import Invoice


@pytest.mark.django_db
@pytest.mark.unit
class TestHTMLFormatter:
    """Tests for HTMLFormatter."""

    def test_html_formatter_get_data(self, invoice_factory):
        """Test data retrieval."""
        invoice = invoice_factory()
        formatter = HTMLFormatter(invoice)
        data = formatter.get_data()
        
        assert 'invoice' in data
        assert data['invoice'] == invoice
        assert 'INVOICING_DATE_FORMAT_TAG' in data

    def test_html_formatter_get_response(self, invoice_factory):
        """Test response generation."""
        invoice = invoice_factory()
        formatter = HTMLFormatter(invoice)
        response = formatter.get_response()
        
        assert isinstance(response, HttpResponse)
        assert response.status_code == 200

    def test_html_formatter_with_context(self, invoice_factory):
        """Test context passing."""
        invoice = invoice_factory()
        formatter = HTMLFormatter(invoice)
        context = {'extra_data': 'test'}
        response = formatter.get_response(context=context)
        
        assert isinstance(response, HttpResponse)


@pytest.mark.django_db
@pytest.mark.unit
class TestBootstrapHTMLFormatter:
    """Tests for BootstrapHTMLFormatter."""

    def test_bootstrap_formatter_inheritance(self, invoice_factory):
        """Test inheritance from HTMLFormatter."""
        invoice = invoice_factory()
        formatter = BootstrapHTMLFormatter(invoice)
        
        assert isinstance(formatter, HTMLFormatter)

    def test_bootstrap_formatter_template(self, invoice_factory):
        """Test Bootstrap template usage."""
        invoice = invoice_factory()
        formatter = BootstrapHTMLFormatter(invoice)
        
        assert formatter.template_name == 'invoicing/formatters/bootstrap.html'
        assert formatter.template_name != HTMLFormatter.template_name

    def test_bootstrap_formatter_get_response(self, invoice_factory):
        """Test response generation."""
        invoice = invoice_factory()
        formatter = BootstrapHTMLFormatter(invoice)
        response = formatter.get_response()
        
        assert isinstance(response, HttpResponse)

