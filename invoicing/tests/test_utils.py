"""
Tests for utility functions.
"""
import pytest
from decimal import Decimal

from invoicing.utils import format_decimal, deprecated


@pytest.mark.unit
class TestFormatDecimal:
    """Tests for format_decimal function."""

    def test_format_decimal_basic(self):
        """Test basic decimal formatting."""
        result = format_decimal(Decimal('100.50'))
        assert isinstance(result, str)
        assert '100' in result

    def test_format_decimal_zero(self):
        """Test zero decimal formatting."""
        result = format_decimal(Decimal('0.00'))
        assert isinstance(result, str)

    def test_format_decimal_large_number(self):
        """Test large number formatting."""
        result = format_decimal(Decimal('999999.99'))
        assert isinstance(result, str)


@pytest.mark.unit
class TestDeprecated:
    """Tests for deprecated decorator."""

    def test_deprecated_decorator(self):
        """Test deprecated decorator functionality."""
        @deprecated
        def old_function():
            return "test"
        
        # Decorator should not break function execution
        result = old_function()
        assert result == "test"
