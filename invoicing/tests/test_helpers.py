"""
Tests for helper functions.
"""
import pytest
from datetime import date
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from invoicing.helpers import sequence_generator, number_formatter
from invoicing.models import Invoice


@pytest.mark.django_db
@pytest.mark.unit
class TestSequenceGenerator:
    """Tests for sequence_generator function."""

    def test_sequence_generator_daily(self, invoice_factory, settings_daily_counter):
        """Test daily sequence generation."""
        date1 = date(2024, 1, 15)
        date2 = date(2024, 1, 16)
        
        # Create invoices on same day
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        
        # Generate sequence for same day
        seq1 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date1,
            related_invoices=Invoice.objects.filter(date_issue=date1)
        )
        
        # Should be next after invoice2
        assert seq1 == invoice2.sequence + 1
        
        # Generate sequence for different day
        seq2 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date2,
            related_invoices=Invoice.objects.filter(date_issue=date2)
        )
        
        # Should start from 1 for new day
        assert seq2 == 1

    def test_sequence_generator_monthly(self, invoice_factory, settings_monthly_counter):
        """Test monthly sequence generation."""
        date1 = date(2024, 1, 15)
        date2 = date(2024, 2, 15)
        
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        
        seq1 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date1,
            related_invoices=Invoice.objects.filter(
                date_issue__year=date1.year,
                date_issue__month=date1.month
            )
        )
        
        assert seq1 == invoice2.sequence + 1
        
        seq2 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date2,
            related_invoices=Invoice.objects.filter(
                date_issue__year=date2.year,
                date_issue__month=date2.month
            )
        )
        
        assert seq2 == 1  # New month

    def test_sequence_generator_yearly(self, invoice_factory, settings_yearly_counter):
        """Test yearly sequence generation."""
        date1 = date(2024, 1, 15)
        date2 = date(2025, 1, 15)
        
        invoice1 = invoice_factory(date_issue=date1)
        invoice2 = invoice_factory(date_issue=date1)
        
        seq1 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date1,
            related_invoices=Invoice.objects.filter(date_issue__year=date1.year)
        )
        
        assert seq1 == invoice2.sequence + 1
        
        seq2 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date2,
            related_invoices=Invoice.objects.filter(date_issue__year=date2.year)
        )
        
        assert seq2 == 1  # New year

    @override_settings(INVOICING_COUNTER_PERIOD='INFINITE')
    def test_sequence_generator_infinite(self, invoice_factory):
        """Test infinite sequence generation."""
        invoice1 = invoice_factory()
        invoice2 = invoice_factory()
        
        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all()
        )
        
        assert seq == invoice2.sequence + 1

    def test_sequence_generator_with_prefix(self, invoice_factory, settings_yearly_counter):
        """Test sequence with number prefix."""
        invoice1 = invoice_factory(number='PREFIX-001')
        invoice2 = invoice_factory(number='PREFIX-002')
        
        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            number_prefix='PREFIX',
            related_invoices=Invoice.objects.filter(number__startswith='PREFIX')
        )
        
        assert seq == invoice2.sequence + 1

    @override_settings(INVOICING_COUNTER_PER_TYPE=True)
    def test_sequence_generator_per_type(self, invoice_factory, settings_yearly_counter):
        """Test per-type sequence generation."""
        invoice1 = invoice_factory(type=Invoice.TYPE.INVOICE)
        invoice2 = invoice_factory(type=Invoice.TYPE.INVOICE)
        proforma = invoice_factory(type=Invoice.TYPE.PROFORMA)
        
        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.filter(type=Invoice.TYPE.INVOICE)
        )
        
        assert seq == invoice2.sequence + 1

    def test_sequence_generator_start_from(self, settings_yearly_counter):
        """Test custom start value."""
        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            start_from=100,
            related_invoices=Invoice.objects.none()
        )
        
        assert seq == 100

    def test_sequence_generator_improperly_configured(self):
        """Test invalid configuration."""
        with pytest.raises(ImproperlyConfigured):
            sequence_generator(
                type=Invoice.TYPE.INVOICE,
                important_date=date.today(),
                counter_period='INVALID',
                related_invoices=Invoice.objects.none()
            )

    @override_settings(INVOICING_COUNTER_PER_TYPE=True)
    def test_sequence_generator_requires_type(self):
        """Test that type is required when INVOICING_COUNTER_PER_TYPE is enabled."""
        with pytest.raises(ValueError):
            sequence_generator(
                type=None,
                important_date=date.today(),
                related_invoices=Invoice.objects.none()
            )


@pytest.mark.django_db
@pytest.mark.unit
class TestSequenceGeneratorFillGaps:
    """Tests for INVOICING_FILL_SEQUENCE_GAPS (reusing numbers of deleted invoices)."""

    def _with_gap(self, invoice_factory, **kwargs):
        """Create the sequence 1, 2, 3, 7 - a gap at 4, 5, 6."""
        for sequence in (1, 2, 3, 7):
            invoice_factory(sequence=sequence, **kwargs)

    def test_gaps_are_not_filled_by_default(self, invoice_factory, settings_yearly_counter):
        """Without the setting the generator continues after the highest sequence."""
        self._with_gap(invoice_factory)

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all()
        )

        assert seq == 8

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_lowest_free_sequence_is_returned(self, invoice_factory, settings_yearly_counter):
        """With the setting enabled the lowest unused sequence is reused."""
        self._with_gap(invoice_factory)

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all()
        )

        assert seq == 4

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_continuous_sequence_behaves_as_before(self, invoice_factory, settings_yearly_counter):
        """Without a gap the result is identical to MAX + 1."""
        for sequence in (1, 2, 3):
            invoice_factory(sequence=sequence)

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all()
        )

        assert seq == 4

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_empty_counter_period_starts_from_beginning(self, settings_yearly_counter):
        """An empty period yields INVOICING_NUMBER_START_FROM, same as before."""
        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.none()
        )

        assert seq == 1

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_gap_does_not_leak_across_counter_periods(self, invoice_factory, settings_yearly_counter):
        """A gap in one year must not be filled from another year."""
        self._with_gap(invoice_factory, date_issue=date(2025, 6, 1))
        invoice_factory(sequence=1, date_issue=date(2026, 6, 1))

        seq_2025 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date(2025, 6, 1),
            related_invoices=Invoice.objects.all()
        )
        seq_2026 = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date(2026, 6, 1),
            related_invoices=Invoice.objects.all()
        )

        assert seq_2025 == 4
        assert seq_2026 == 2

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_respects_start_from(self, invoice_factory, settings_yearly_counter):
        """Sequences below start_from are ignored when looking for a gap."""
        invoice_factory(sequence=5)
        invoice_factory(sequence=100)
        invoice_factory(sequence=102)

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            start_from=100,
            related_invoices=Invoice.objects.all()
        )

        assert seq == 101

    @override_settings(INVOICING_FILL_SEQUENCE_GAPS=True)
    def test_respects_number_prefix(self, invoice_factory, settings_yearly_counter):
        """The gap is looked up within the prefixed sequence only."""
        invoice_factory(sequence=1, number='PREFIX-001')
        invoice_factory(sequence=2, number='PREFIX-002')
        invoice_factory(sequence=4, number='PREFIX-004')
        invoice_factory(sequence=3, number='OTHER-003')

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            number_prefix='PREFIX',
            related_invoices=Invoice.objects.all()
        )

        assert seq == 3

    def test_fill_gaps_argument_overrides_setting(self, invoice_factory, settings_yearly_counter):
        """The explicit argument wins over the (disabled) setting."""
        self._with_gap(invoice_factory)

        seq = sequence_generator(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all(),
            fill_gaps=True
        )

        assert seq == 4

    def test_get_next_sequence_forwards_fill_gaps(self, invoice_factory, settings_yearly_counter):
        """Invoice.get_next_sequence passes the flag down to the generator."""
        self._with_gap(invoice_factory)

        assert Invoice.get_next_sequence(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all(),
            fill_gaps=True) == 4

        assert Invoice.get_next_sequence(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            related_invoices=Invoice.objects.all()) == 8

    def test_get_next_sequence_keeps_legacy_generators_working(self, settings_yearly_counter):
        """A custom generator without a fill_gaps argument must not break."""
        def legacy_generator(type, important_date, number_prefix=None, counter_period=None,
                             related_invoices=None, start_from=None):
            return 42

        assert Invoice.get_next_sequence(
            type=Invoice.TYPE.INVOICE,
            important_date=date.today(),
            generator=legacy_generator) == 42

    def test_save_honours_instance_attribute(self, invoice_factory, settings_yearly_counter):
        """Invoice.fill_sequence_gaps overrides the setting for a single instance."""
        self._with_gap(invoice_factory)
        invoice = invoice_factory(sequence=99)

        invoice.sequence = None
        invoice.number = ''
        invoice.fill_sequence_gaps = True
        invoice.save()

        assert invoice.sequence == 4


@pytest.mark.django_db
@pytest.mark.unit
class TestNumberFormatter:
    """Tests for number_formatter function."""

    def test_number_formatter_default(self, invoice_factory):
        """Test default number format."""
        invoice = invoice_factory(date_issue=date(2024, 1, 15), sequence=5)
        number = number_formatter(invoice)
        
        # Default format: {{ invoice.date_issue|date:'Y' }}/{{ invoice.sequence }}
        assert '2024' in number
        assert '5' in number

    @override_settings(INVOICING_NUMBER_FORMAT="{{ invoice.sequence }}-{{ invoice.type }}")
    def test_number_formatter_custom(self, invoice_factory):
        """Test custom number format."""
        invoice = invoice_factory(sequence=42, type=Invoice.TYPE.INVOICE)
        number = number_formatter(invoice)
        
        assert '42' in number
        assert 'INVOICE' in number

    def test_number_formatter_with_date(self, invoice_factory):
        """Test date-based formatting."""
        invoice = invoice_factory(date_issue=date(2024, 3, 15), sequence=10)
        number = number_formatter(invoice)
        
        # Should include date components
        assert str(invoice.sequence) in number

    def test_number_formatter_with_sequence(self, invoice_factory):
        """Test sequence-based formatting."""
        invoice = invoice_factory(sequence=123)
        number = number_formatter(invoice)
        
        assert '123' in number

