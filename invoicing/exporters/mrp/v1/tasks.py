import logging

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.module_loading import import_string
from outputs.models import Export, ExportItem
from outputs.usecases import mail_successful_export, notify_about_failed_export
from pragmatic.utils import compress, get_task_decorator

logger = logging.getLogger(__name__)

task = get_task_decorator("exports")


@task
def mail_exported_invoices_mrp_v1(export_id, exporter_subclass_paths, filename=None, language=settings.LANGUAGE_CODE):
    """MRP v1 export task - combines 3 XML exporters into a single zip file."""
    export = Export.objects.get(id=export_id)

    export.status = Export.STATUS_PROCESSING
    export.save(update_fields=['status'])

    # set language
    translation.activate(language)

    # Initialize and run all exporters
    if not exporter_subclass_paths:
        logger.info(
            f"Not possible to executed mrp v1 export without exporter subclasses.  {exporter_subclass_paths}"
        )

    queryset = export.object_list
    exporters = [
        import_string(path)(user=export.creator, recipients=export.recipients, params={}, queryset=queryset)
        for path in exporter_subclass_paths
    ]

    logger.info(
        f"Executed mrp v1 export with {queryset.count()} items."
    )

    try:
        with transaction.atomic():
            for exporter in exporters:
                exporter.export()

            # Combine into zip
            export_files = [
                {'name': exporter.get_filename(), 'content': exporter.get_output()}
                for exporter in exporters
            ]
            zip_file = compress(export_files)
            zip_file.seek(0)

            # update status of export
            export.status = Export.STATUS_FINISHED
            export.save(update_fields=['status'])
            updated_count = export.update_export_items_result(ExportItem.RESULT_SUCCESS)
            logger.info(
                f"Updated {updated_count} ExportItem records to SUCCESS for export_id={export.id}"
            )

        mail_successful_export(export, filename, zip_file)
    except Exception as e:
        with transaction.atomic():
            export.status = Export.STATUS_FAILED
            export.save(update_fields=['status'])
            updated_count = export.update_export_items_result(ExportItem.RESULT_FAILURE, detail=str(e))
            logger.info(
                f"Updated {updated_count} ExportItem records to FAILURE for export_id={export.id}"
            )
        notify_about_failed_export(export, str(e))
        raise
