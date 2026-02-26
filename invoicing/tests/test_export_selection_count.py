"""
Tests verifying that the number of invoices selected in a Django Admin
action is equal to the number of invoices the exporter ultimately
receives — guarding against regressions where an exporter's
get_queryset() ignores the selection and falls back to the full table.

Pipeline under test
-------------------

  Admin action call  (N selected invoices)
    └→ InvoiceAdmin.get_actions() wrapper  (make_action)
         └→ manager.export_*(request, queryset=N)
              ├─ email-delivery path (_execute_export)
              │    └→ exporter_class(queryset=N)
              │         └→ execute_export(exporter)   ← captured HERE
              │              └→ [real: Export + N × ExportItem]
              └─ task-based path (_execute_api_export / export_list_mrp)
                   └→ exporter_class(queryset=N)
                        └→ exporter.save_export()     ← captured HERE
                             └→ task.delay(export.id, ...)

Because the ``outputs`` package is mocked in conftest.py we cannot
inspect real ExportItem rows.  Instead, we intercept the two
"handover points" listed above and verify that the exporter's
get_queryset().count() equals the number of invoices that were
originally selected — not the total number of invoices in the database.
"""
import sys
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from invoicing import settings as invoicing_settings
from invoicing.models import Invoice
from invoicing.exporters.mixins import InvoiceManagerMixin
from invoicing.exporters.pdf.managers import PdfManager
from invoicing.exporters.xlsx.managers import XlsxManager
from invoicing.exporters.isdoc.managers import IsdocManager
from invoicing.exporters.mrp.v1.managers import MrpV1Manager
from invoicing.exporters.mrp.v2.managers import MrpIssuedManager, MrpReceivedManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(user_id=1):
    """Build a minimal mock HTTP request suitable for manager calls."""
    request = Mock()
    request.user = Mock()
    request.user.id = user_id
    request.GET = {}
    return request


def _make_admin_request(user_id=1):
    """Build a mock request that satisfies Django Admin's get_actions()."""
    request = _make_request(user_id)
    request.user.is_active = True
    request.user.is_staff = True
    request.user.has_perm = Mock(return_value=True)
    request.user.has_module_perms = Mock(return_value=True)
    return request


def _capture_count_via_execute_export(action_fn, request, queryset):
    """
    Call *action_fn(request=..., queryset=...)* and return the queryset
    count seen by the exporter at the moment ``execute_export`` is
    invoked.

    Intercepts ``outputs.usecases.execute_export`` — the single
    hand-off point used by all email-delivery exporters that go through
    ``InvoiceManagerMixin._execute_export()``.

    Raises AssertionError if execute_export was never called (export
    aborted by validation — check _is_export_qs_valid / required_origin).
    """
    captured = {}

    def _capturing(exporter, language=None):
        captured['count'] = exporter.get_queryset().count()

    usecases = sys.modules['outputs.usecases']
    original = usecases.execute_export
    usecases.execute_export = _capturing
    try:
        action_fn(request=request, queryset=queryset)
    finally:
        usecases.execute_export = original

    assert 'count' in captured, (
        "execute_export was never called — the export was aborted before "
        "reaching the hand-off point.  Check _is_export_qs_valid() or "
        "required_origin constraints."
    )
    return captured['count']


def _capture_count_via_save_export(action_fn, request, queryset):
    """
    Call *action_fn(request=..., queryset=...)* and return the queryset
    count seen by the exporter at the moment ``save_export`` is invoked.

    Intercepts ``ExporterMixin.save_export`` — the hand-off point used
    by task-based exporters (MRP v1, MRP v2 API) which create an Export
    object and then queue a Celery task.

    Raises AssertionError if save_export was never called.
    """
    captured = {}
    ExporterMixin = sys.modules['outputs.mixins'].ExporterMixin
    original_save_export = ExporterMixin.save_export

    def _capturing(self_exporter):
        captured['count'] = self_exporter.get_queryset().count()
        return original_save_export(self_exporter)

    ExporterMixin.save_export = _capturing
    try:
        action_fn(request=request, queryset=queryset)
    finally:
        ExporterMixin.save_export = original_save_export

    assert 'count' in captured, (
        "save_export was never called — the export was aborted before "
        "reaching the hand-off point.  Check _is_export_qs_valid() or "
        "required_origin constraints."
    )
    return captured['count']


# ---------------------------------------------------------------------------
# Parametrize: (total invoices in DB, how many are selected)
#
# The scenario (5, 3) is the most important regression guard: it proves
# the exporter receives the *selection*, not the full table.
# ---------------------------------------------------------------------------
SELECTION_SCENARIOS = [
    pytest.param(1, 1, id="select_1_of_1"),
    pytest.param(3, 3, id="select_all_3"),
    pytest.param(5, 3, id="select_3_of_5"),   # critical: 3 ≠ 5
    pytest.param(10, 1, id="select_1_of_10"),
    pytest.param(10, 7, id="select_7_of_10"),
]


# ---------------------------------------------------------------------------
# Manager-level tests (call manager methods directly)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.exporters
class TestExportCountMatchesSelection:
    """
    Verifies at the manager level that the exporter sees exactly the
    invoices that were selected — not the full database table.

    Each parametrized case creates *db_count* invoices in the database
    but passes only *selected_count* of them to the export action.
    """

    def _invoices(self, invoice_factory, count, **kwargs):
        return [invoice_factory(**kwargs) for _ in range(count)]

    # --- email-delivery exports -------------------------------------------

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_pdf_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        count = _capture_count_via_execute_export(
            PdfManager().export_detail_pdf, _make_request(), queryset
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_xlsx_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        count = _capture_count_via_execute_export(
            XlsxManager().export_list_xlsx, _make_request(), queryset
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_isdoc_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        count = _capture_count_via_execute_export(
            IsdocManager().export_list_isdoc, _make_request(), queryset
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_issued_xml_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        # MrpIssuedManager requires origin=ISSUED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        count = _capture_count_via_execute_export(
            MrpIssuedManager().export_list_issued_mrp, _make_request(), queryset
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_received_xml_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        # MrpReceivedManager requires origin=RECEIVED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.RECEIVED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        count = _capture_count_via_execute_export(
            MrpReceivedManager().export_list_received_mrp, _make_request(), queryset
        )
        assert count == selected_count

    # --- task-based exports (save_export path) ----------------------------

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v1_exporter_receives_selection(self, invoice_factory, db_count, selected_count):
        import invoicing.exporters.mrp.v1.tasks as mrp_v1_tasks

        # MrpV1Manager requires origin=ISSUED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        with patch.object(mrp_v1_tasks, 'mail_exported_invoices_mrp_v1'):
            count = _capture_count_via_save_export(
                MrpV1Manager().export_list_mrp, _make_request(), queryset
            )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_api_exporter_receives_selection(self, invoice_factory, monkeypatch, db_count, selected_count):
        import invoicing.exporters.mrp.v2.tasks as mrp_v2_tasks
        import invoicing.settings as inv_settings

        monkeypatch.setattr(inv_settings, 'INVOICING_MANAGERS', {
            'invoicing.exporters.mrp.v2.managers.MrpIssuedManager': {
                'API_URL': 'https://mrp.example.com'
            }
        })
        # MrpIssuedManager requires origin=ISSUED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        with patch.object(mrp_v2_tasks, 'send_invoices_to_mrp'):
            count = _capture_count_via_save_export(
                MrpIssuedManager().export_via_api, _make_request(), queryset
            )
        assert count == selected_count


# ---------------------------------------------------------------------------
# Admin action pipeline tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.exporters
class TestAdminActionExportCountMatchesSelection:
    """
    Verifies that the InvoiceAdmin.get_actions() wrapper correctly
    threads the admin selection queryset all the way through to the
    exporter.

    This tests the full path:
      InvoiceAdmin.get_actions() → make_action wrapper → manager method
      → _execute_export() → exporter.get_queryset()
    """

    _DEFAULT_ADMIN_MANAGERS = {
        'invoicing.exporters.pdf.managers.PdfManager': {},
        'invoicing.exporters.xlsx.managers.XlsxManager': {},
    }

    def _get_admin_action(self, monkeypatch, action_name, managers=None):
        """
        Return (admin_instance, action_fn) for *action_name* from
        InvoiceAdmin, with INVOICING_MANAGERS set to *managers*
        (defaults to PdfManager + XlsxManager).
        """
        import invoicing.settings as inv_settings
        from django.contrib.admin import site as admin_site
        from invoicing.admin import InvoiceAdmin

        monkeypatch.setattr(inv_settings, 'INVOICING_MANAGERS',
                            managers or self._DEFAULT_ADMIN_MANAGERS)

        admin_instance = InvoiceAdmin(Invoice, admin_site)
        request = _make_admin_request()
        actions = admin_instance.get_actions(request)
        assert action_name in actions, (
            f"Action '{action_name}' not found in InvoiceAdmin.  "
            f"Available actions: {list(actions.keys())}"
        )
        action_fn, _, _ = actions[action_name]
        return admin_instance, action_fn

    @pytest.mark.parametrize("db_count,selected_count", [
        pytest.param(5, 3, id="pdf_select_3_of_5"),
        pytest.param(10, 1, id="pdf_select_1_of_10"),
    ])
    def test_pdf_admin_action_threads_queryset(self, invoice_factory, monkeypatch, db_count, selected_count):
        """PDF admin action must pass only the selected invoices to the exporter."""
        all_inv = [invoice_factory() for _ in range(db_count)]
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        admin_instance, action_fn = self._get_admin_action(monkeypatch, 'pdfmanager_export_detail_pdf')
        request = _make_admin_request()

        # Admin actions have signature (modeladmin, request, queryset)
        count = _capture_count_via_execute_export(
            lambda request, queryset: action_fn(admin_instance, request, queryset),
            request,
            queryset,
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", [
        pytest.param(5, 3, id="xlsx_select_3_of_5"),
        pytest.param(10, 2, id="xlsx_select_2_of_10"),
    ])
    def test_xlsx_admin_action_threads_queryset(self, invoice_factory, monkeypatch, db_count, selected_count):
        """XLSX admin action must pass only the selected invoices to the exporter."""
        all_inv = [invoice_factory() for _ in range(db_count)]
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        admin_instance, action_fn = self._get_admin_action(monkeypatch, 'xlsxmanager_export_list_xlsx')
        request = _make_admin_request()

        count = _capture_count_via_execute_export(
            lambda request, queryset: action_fn(admin_instance, request, queryset),
            request,
            queryset,
        )
        assert count == selected_count

    def test_selection_is_isolated_from_unselected_invoices(self, invoice_factory, monkeypatch):
        """
        The most explicit regression guard: 10 invoices in DB, 3 selected.
        Regardless of what is in the database, the exporter must receive
        exactly 3.  A count of 10 would indicate the exporter is using
        Invoice.objects.all() instead of the selection.
        """
        all_inv = [invoice_factory() for _ in range(10)]
        selected = all_inv[2:5]   # pick 3 that are not the first/last
        queryset = Invoice.objects.filter(id__in=[i.id for i in selected])

        assert Invoice.objects.count() == 10, "Pre-condition: 10 invoices in DB"
        assert queryset.count() == 3, "Pre-condition: 3 selected"

        admin_instance, action_fn = self._get_admin_action(monkeypatch, 'pdfmanager_export_detail_pdf')
        request = _make_admin_request()

        count = _capture_count_via_execute_export(
            lambda request, queryset: action_fn(admin_instance, request, queryset),
            request,
            queryset,
        )

        assert count == 3, (
            f"Exporter received {count} invoices but only 3 were selected.  "
            "This indicates the exporter is ignoring the admin queryset "
            "and exporting the full table instead."
        )
        assert count != 10, "Exporter must not export the entire database table."
