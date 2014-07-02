from django.db.models import Manager
from django.db.models.query import QuerySet


class InvoiceItemQuerySet(QuerySet):
    def with_tag(self, tag):
        return self.filter(tag=tag)


class InvoiceItemManager(Manager):
    def get_query_set(self):
        return self.get_query_set()

    def get_queryset(self):
        return InvoiceItemQuerySet(self.model, using=self._db)

    def with_tag(self, tag):
        return self.get_queryset().with_tag(tag)
