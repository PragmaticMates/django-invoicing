from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EInvoicingConfig(AppConfig):
    name = 'invoicing.einvoicing'
    label = 'invoicing_einvoicing'
    verbose_name = _('E-invoicing')
    default_auto_field = 'django.db.models.AutoField'

    def schedule_jobs(self):
        """
        Registers the periodic maintenance (resubmit unsent, poll statuses).

        Called by django-pragmatic's ``rqscheduler`` command, which first wipes the
        ``cron`` scheduler, so redeploys never leave a duplicate.
        INVOICING_EINVOICING['MAINTENANCE_CRON'] = None disables it.
        """
        from invoicing.einvoicing import conf

        cron = conf.get('MAINTENANCE_CRON')
        if not cron:
            return

        import django_rq

        django_rq.get_scheduler('cron').cron(
            cron,
            func='invoicing.einvoicing.tasks.einvoicing_maintenance',
            id='invoicing-einvoicing-maintenance',  # rq 2.x: letters, digits, - and _ only
            description='E-invoicing: resubmit unsent transmissions, poll the status of sent ones',
            queue_name=conf.get('MAINTENANCE_QUEUE'),
            use_local_timezone=True,
            timeout=600,
            result_ttl=60 * 60 * 24,
            repeat=None,
        )
