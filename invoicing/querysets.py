import datetime

from django.db import connection
from django.db.models import Q, Count
from django.db.models.query import QuerySet
from django.utils.timezone import now


class InvoiceQuerySet(QuerySet):
    def overdue(self):
        return self.unpaid() \
            .filter(date_due__lt=datetime.datetime.combine(now().date(), datetime.time.max)) \
            .exclude(type=self.model.TYPE.CREDIT_NOTE)

    def not_overdue(self):
        return self.filter(Q(date_due__gt=datetime.datetime.combine(now().date(), datetime.time.max)) | Q(status__in=[self.model.STATUS.PAID, self.model.STATUS.CANCELED, self.model.STATUS.CREDITED]))

    def paid(self):
        return self.filter(status=self.model.STATUS.PAID)

    def unpaid(self):
        return self.exclude(Q(status__in=[self.model.STATUS.PAID, self.model.STATUS.CANCELED, self.model.STATUS.CREDITED]) | Q(total=0))

    def valid(self):
        return self.exclude(status__in=[self.model.STATUS.RETURNED, self.model.STATUS.CANCELED, self.model.STATUS.CREDITED, self.model.STATUS.UNCOLLECTIBLE])

    def collectible(self):
        return self.exclude(status=self.model.STATUS.UNCOLLECTIBLE)

    def uncollectible(self):
        return self.filter(status=self.model.STATUS.UNCOLLECTIBLE)

    def having_related_invoices(self):
        return self.exclude(related_invoices=None)

    def not_having_related_invoices(self):
        return self.filter(related_invoices=None)

    def duplicate_numbers(self):
        return list(self
                    .values('number')
                    .order_by()
                    .annotate(count=Count('id'))
                    .filter(count__gt=1)
                    .values_list('number', flat=True))

    def lock(self):
        """ Lock table.

        Locks the object model table so that atomic update is possible.
        Simultaneous database access request pend until the lock is unlock()'ed.

        Note: If you need to lock multiple tables, you need to do lock them
        all in one SQL clause and this function is not enough. To avoid
        dead lock, all tables must be locked in the same order.

        If no lock mode is specified, then ACCESS EXCLUSIVE, the most restrictive mode, is used.
        Read more: https://www.postgresql.org/docs/9.4/static/sql-lock.html
        """
        cursor = connection.cursor()
        table = self.model._meta.db_table
        cursor.execute("LOCK TABLE %s" % table)


class ItemQuerySet(QuerySet):
    def with_tag(self, tag):
        return self.filter(tag=tag)
