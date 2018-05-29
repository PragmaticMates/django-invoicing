from django.db import migrations
from invoicing.models import Invoice


def recalculate(*args, **kwargs):
    for invoice in Invoice.objects.all():
        invoice.total = invoice.calculate_total()
        invoice.vat = invoice.calculate_vat()
        invoice.save(update_fields=['total', 'vat'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0007_auto_20180529_1601'),
    ]

    operations = [
        migrations.RunPython(recalculate, lambda *args, **kwargs: None)
    ]
