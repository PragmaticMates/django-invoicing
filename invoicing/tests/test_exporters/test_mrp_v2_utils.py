"""
Tests for MRP v2 utility functions.
"""
import pytest

from invoicing.exporters.mrp.v2.utils import (
    sanitize_forbidden_chars,
    sanitize_uppercase_only,
    sanitize_zipcode,
    sanitize_city
)


@pytest.mark.exporters
@pytest.mark.unit
class TestMRPUtils:
    """Tests for MRP v2 utility functions."""

    def test_sanitize_forbidden_chars(self):
        """Test removal of forbidden characters."""
        result = sanitize_forbidden_chars("Test'#|String\t")
        assert result == "TestString"
        assert "'" not in result
        assert "#" not in result
        assert "|" not in result
        assert "\t" not in result

    def test_sanitize_forbidden_chars_empty(self):
        """Test sanitization of empty string."""
        result = sanitize_forbidden_chars("")
        assert result == ""

    def test_sanitize_forbidden_chars_none(self):
        """Test sanitization of None."""
        result = sanitize_forbidden_chars(None)
        assert result == ""

    def test_sanitize_forbidden_chars_max_length(self):
        """Test max length truncation."""
        result = sanitize_forbidden_chars("Very Long String", max_length=10)
        assert result == "Very Long "
        assert len(result) == 10

    def test_sanitize_forbidden_chars_no_forbidden(self):
        """Test string without forbidden characters."""
        result = sanitize_forbidden_chars("NormalString123")
        assert result == "NormalString123"

    def test_sanitize_uppercase_only(self):
        """Test uppercase conversion."""
        result = sanitize_uppercase_only("test123")
        assert result == "TEST"
        assert result.isupper()
        assert "123" not in result

    def test_sanitize_uppercase_only_empty(self):
        """Test uppercase conversion of empty string."""
        result = sanitize_uppercase_only("")
        assert result == ""

    def test_sanitize_uppercase_only_none(self):
        """Test uppercase conversion of None."""
        result = sanitize_uppercase_only(None)
        assert result == ""

    def test_sanitize_uppercase_only_max_length(self):
        """Test uppercase with max length."""
        result = sanitize_uppercase_only("verylongstring", max_length=5)
        assert result == "VERYL"
        assert len(result) == 5

    def test_sanitize_uppercase_only_special_chars(self):
        """Test uppercase conversion with special characters."""
        result = sanitize_uppercase_only("test-123_abc")
        assert result == "TESTABC"
        assert result.isalpha()

    def test_sanitize_zipcode(self):
        """Test zipcode sanitization."""
        result = sanitize_zipcode("12345")
        assert result == "12345"

    def test_sanitize_zipcode_with_spaces(self):
        """Test zipcode with spaces."""
        result = sanitize_zipcode("123 45")
        assert result == "123 45"

    def test_sanitize_zipcode_with_dots(self):
        """Test zipcode with dots."""
        result = sanitize_zipcode("123.45")
        assert result == "123.45"

    def test_sanitize_zipcode_with_hyphens(self):
        """Test zipcode with hyphens."""
        result = sanitize_zipcode("123-45")
        assert result == "123-45"

    def test_sanitize_zipcode_removes_invalid_chars(self):
        """Test zipcode removes invalid characters."""
        result = sanitize_zipcode("123#45@67")
        assert "#" not in result
        assert "@" not in result

    def test_sanitize_zipcode_max_length(self):
        """Test zipcode max length."""
        result = sanitize_zipcode("12345678901234567890", max_length=15)
        assert len(result) == 15

    def test_sanitize_zipcode_empty(self):
        """Test zipcode sanitization of empty string."""
        result = sanitize_zipcode("")
        assert result == ""

    def test_sanitize_zipcode_none(self):
        """Test zipcode sanitization of None."""
        result = sanitize_zipcode(None)
        assert result == ""

    def test_sanitize_city(self):
        """Test city sanitization."""
        result = sanitize_city("Bratislava")
        assert result == "Bratislava"
        assert len(result) <= 30

    def test_sanitize_city_removes_forbidden_chars(self):
        """Test city removes forbidden characters."""
        result = sanitize_city("City'#|Name\t")
        assert "'" not in result
        assert "#" not in result
        assert "|" not in result
        assert "\t" not in result

    def test_sanitize_city_replaces_apostrophe(self):
        """Test city replaces apostrophe with backtick."""
        result = sanitize_city("O'City")
        assert "`" in result or "'" not in result

    def test_sanitize_city_max_length(self):
        """Test city max length (30 characters)."""
        long_city = "A" * 50
        result = sanitize_city(long_city)
        assert len(result) <= 30

    def test_sanitize_city_empty(self):
        """Test city sanitization of empty string."""
        result = sanitize_city("")
        assert result == ""

    def test_sanitize_city_none(self):
        """Test city sanitization of None."""
        result = sanitize_city(None)
        assert result == ""

