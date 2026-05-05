"""
Tests verifying that exactly one ``outputs.ExportItem`` row is created
in the database for each invoice in the selected queryset — guarding
against regressions where an exporter's ``get_queryset()`` ignores the
selection and falls back to the full table.

Pipeline under test
-------------------

  manager.export_*(request, queryset=N)
    ├─ email-delivery path (_execute_export)
    │    └→ outputs.jobs.serialize_exporter_params → execute_export.delay(...)
    │         → exporter.save_export()             (creates Export row)
    │           → ExportItem.objects.bulk_create() (N ExportItem rows)
    │         → Export.send_mail()                 (mocked — no SMTP)
    └─ task-based path (MRP v1, MRP v2 API)
         → exporter.save_export()                  (creates Export row)
           → ExportItem.objects.bulk_create()      (N ExportItem rows)
         → task.delay(export.id, ...)              (mocked)

All integration tests assert ``ExportItem.objects.count() == selected_count``
against the real PostgreSQL database (required for ``Export.fields``/
``Export.emails`` which use PostgreSQL-only ``ArrayField`` columns).
A real ``auth.User`` is created per test because ``Export.creator`` is a FK.

``outputs.signals`` is mocked in conftest.py to avoid importing
``django_rq``, whose ``post_save`` handler on Export would require a
live Redis connection every time an Export row is saved.
"""
import sys
import pytest
from unittest.mock import Mock, patch

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

def _make_request(user=None, user_id=1):
    """Build a minimal mock HTTP request.  Pass a real User for DB tests."""
    request = Mock()
    if user is not None:
        request.user = user
    else:
        request.user = Mock()
        request.user.id = user_id
    request.GET = {}
    return request





# (db_count, selected_count) — (5, 3) is the key regression guard
SELECTION_SCENARIOS = [
    pytest.param(1, 1, id="select_1_of_1"),
    pytest.param(5, 3, id="select_3_of_5"),
    pytest.param(10, 7, id="select_7_of_10"),
]


# ---------------------------------------------------------------------------
# Unit test — _execute_export() queryset threading
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.exporters
class TestInvoiceManagerExecuteExport:
    """
    Direct unit test for InvoiceManagerMixin._execute_export().

    Patches ``pragmatic.utils.dispatch_task`` and checks
    ``serialize_exporter_params`` output: ``queryset_ids`` / ``queryset_model``
    match the selected invoices (the worker deserializes in django-outputs).
    """

    def test_execute_export_passes_queryset_to_exporter(self, invoice_factory):
        """
        _execute_export must hand the *given* queryset to the exporter,
        not silently fall back to the full table.
        """
        all_inv = [invoice_factory() for _ in range(5)]
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:3]])
        expected_ids = sorted(i.id for i in all_inv[:3])
        expected_model = f"{Invoice._meta.app_label}.{Invoice._meta.model_name}"

        class DummyManager(InvoiceManagerMixin):
            pass

        manager = DummyManager()
        request = _make_request()

        captured = {}

        def _capturing_dispatch(_task, exporter_class, job_params, language=None):
            captured["queryset_ids"] = sorted(job_params.get("queryset_ids") or [])
            captured["queryset_model"] = job_params.get("queryset_model")

        with patch("pragmatic.utils.dispatch_task", side_effect=_capturing_dispatch):
            manager._execute_export(
                request=request,
                exporter_class=sys.modules["outputs.mixins"].ExporterMixin,
                exporter_params={"user": request.user, "recipients": [request.user], "params": {}},
                queryset=queryset,
            )

        assert captured["queryset_ids"] == expected_ids
        assert captured["queryset_model"] == expected_model


# ---------------------------------------------------------------------------
# Integration tests — real Export + ExportItem rows in PostgreSQL
# ---------------------------------------------------------------------------

@pytest.fixture
def export_user(django_user_model):
    """A real auth.User needed for Export.creator (ForeignKey)."""
    return django_user_model.objects.create_user(
        username='testexporter',
        email='exporter@test.com',
        password='testpass',
    )


@pytest.mark.django_db
@pytest.mark.exporters
class TestRealExportItemCreation:
    """
    Full-pipeline integration tests: verifies that exactly one
    ``outputs.ExportItem`` row is created for each invoice in the
    selected queryset, for every supported exporter.

    ``Export.send_mail`` is patched in email-delivery tests to suppress
    SMTP.  Task dispatch (``delay()``) is patched in MRP tests to keep
    execution synchronous.
    """

    # --- shared helpers ---------------------------------------------------

    @staticmethod
    def _invoices(invoice_factory, count, **kwargs):
        return [invoice_factory(**kwargs) for _ in range(count)]

    @staticmethod
    def _email_export(manager, exporter_class, queryset, user):
        """Run an email-delivery export and return the ExportItem count."""
        from outputs.jobs import execute_export as outputs_execute_export
        from outputs.models import ExportItem

        request = _make_request(user=user)
        with patch("outputs.models.Export.send_mail"), patch(
            "pragmatic.utils.dispatch_task",
            side_effect=lambda task, ec, ep, language=None: outputs_execute_export(
                ec, ep, language
            ),
        ):
            manager._execute_export(
                request=request,
                exporter_class=exporter_class,
                exporter_params={'user': user, 'recipients': [user], 'params': {}},
                queryset=queryset,
            )
        return ExportItem.objects.count()

    @staticmethod
    def _task_export(call_fn, queryset, user):
        """Run a task-based export (save_export → task.delay) and return the ExportItem count."""
        from outputs.models import ExportItem
        request = _make_request(user=user)
        call_fn(request, queryset)
        return ExportItem.objects.count()

    # --- email-delivery exporters (PDF, XLSX, ISDOC, MRP v2 XML) ----------

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_pdf_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])
        count = self._email_export(PdfManager(), PdfManager.exporter_class, queryset, export_user)
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_xlsx_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])
        count = self._email_export(XlsxManager(), XlsxManager.exporter_class, queryset, export_user)
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_isdoc_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        all_inv = self._invoices(invoice_factory, db_count)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])
        count = self._email_export(IsdocManager(), IsdocManager.exporter_class, queryset, export_user)
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_issued_xml_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        # MrpIssuedManager.required_origin = ISSUED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])
        count = self._email_export(
            MrpIssuedManager(), MrpIssuedManager.exporter_class, queryset, export_user
        )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_received_xml_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        # MrpReceivedManager.required_origin = RECEIVED
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.RECEIVED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])
        count = self._email_export(
            MrpReceivedManager(), MrpReceivedManager.exporter_class, queryset, export_user
        )
        assert count == selected_count

    # --- task-based exporters (MRP v1, MRP v2 API) ------------------------

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v1_exportitem_count_matches_selection(
        self, invoice_factory, export_user, db_count, selected_count
    ):
        import invoicing.exporters.mrp.v1.tasks as mrp_v1_tasks

        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        with patch.object(mrp_v1_tasks, 'mail_exported_invoices_mrp_v1'):
            count = self._task_export(
                lambda req, qs: MrpV1Manager().export_list_mrp(req, qs),
                queryset, export_user,
            )
        assert count == selected_count

    @pytest.mark.parametrize("db_count,selected_count", SELECTION_SCENARIOS)
    def test_mrp_v2_api_exportitem_count_matches_selection(
        self, invoice_factory, export_user, monkeypatch, db_count, selected_count
    ):
        import invoicing.exporters.mrp.v2.tasks as mrp_v2_tasks
        import invoicing.settings as inv_settings

        monkeypatch.setattr(inv_settings, 'INVOICING_MANAGERS', {
            'invoicing.exporters.mrp.v2.managers.MrpIssuedManager': {
                'API_URL': 'https://mrp.example.com',
            }
        })
        all_inv = self._invoices(invoice_factory, db_count, origin=Invoice.ORIGIN.ISSUED)
        queryset = Invoice.objects.filter(id__in=[i.id for i in all_inv[:selected_count]])

        with patch.object(mrp_v2_tasks, 'send_invoices_to_mrp'):
            count = self._task_export(
                lambda req, qs: MrpIssuedManager().export_via_api(req, qs),
                queryset, export_user,
            )
        assert count == selected_count

    # --- explicit regression guard ----------------------------------------

    def test_exportitem_count_is_not_full_table_size(self, invoice_factory, export_user):
        """
        10 invoices in DB, 3 selected — ExportItem count must be 3, not 10.
        A result of 10 would mean the exporter is using Invoice.objects.all()
        instead of the admin selection queryset.
        """
        from outputs.models import ExportItem

        all_inv = self._invoices(invoice_factory, 10)
        selected = all_inv[2:5]  # 3 mid-range invoices
        queryset = Invoice.objects.filter(id__in=[i.id for i in selected])

        assert Invoice.objects.count() == 10, "Pre-condition: 10 invoices in DB"
        assert queryset.count() == 3, "Pre-condition: 3 invoices selected"

        count = self._email_export(PdfManager(), PdfManager.exporter_class, queryset, export_user)

        assert count == 3, (
            f"Expected 3 ExportItem rows but got {count}.  "
            "If this equals 10, the exporter is ignoring the selection queryset."
        )
        assert count != 10, "Exporter must not create an ExportItem for every invoice in the DB."
