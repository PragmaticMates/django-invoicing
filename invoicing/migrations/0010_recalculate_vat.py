from django.db import migrations
from invoicing.models import Invoice


def recalculate_vat(*args, **kwargs):
    pass
    # try:
    #     for invoice in Invoice.objects.all():
    #         invoice.vat = invoice.calculate_vat()
    #         invoice.save(update_fields=['vat'])
    # except:
    #     pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0009_auto_20180531_1816'),
    ]

    operations = [
        migrations.RunPython(recalculate_vat, lambda *args, **kwargs: None)
    ]
