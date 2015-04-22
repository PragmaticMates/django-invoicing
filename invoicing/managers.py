import datetime
from django.db.models import Manager, Q
from django.db.models.query import QuerySet
from django.utils.timezone import now


class InvoiceQuerySet(QuerySet):
    def overdue(self):
        return self.filter(date_due__lt=datetime.datetime.combine(now().date(), datetime.time.max)).exclude(status__in=[self.model.STATUS.PAID, self.model.STATUS.CANCELED])

    def not_overdue(self):
        return self.filter(Q(date_due__gt=datetime.datetime.combine(now().date(), datetime.time.max)) | Q(status__in=[self.model.STATUS.PAID, self.model.STATUS.CANCELED]))


class InvoiceManager(Manager):
    # TODO: Deprecated
    def get_query_set(self):
        return InvoiceQuerySet(self.model, self._db)

    def get_queryset(self):
        return InvoiceQuerySet(self.model, self._db)

    def overdue(self):
        return self.get_queryset().overdue()


class ItemQuerySet(QuerySet):
    def with_tag(self, tag):
        return self.filter(tag=tag)


class ItemManager(Manager):
    # TODO: Deprecated
    def get_query_set(self):
        return ItemQuerySet(self.model, using=self._db)

    def get_queryset(self):
        return ItemQuerySet(self.model, using=self._db)

    def with_tag(self, tag):
        return self.get_queryset().with_tag(tag)
