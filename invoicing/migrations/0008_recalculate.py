from django.db import migrations, transaction
from invoicing.models import Invoice


def recalculate(*args, **kwargs):
    pass
    # try:
    #     for invoice in Invoice.objects.all():
    #         with transaction.atomic():
    #             invoice.total = invoice.calculate_total()
    #             invoice.vat = invoice.calculate_vat()
    #             invoice.save(update_fields=['total'])
    #
    #             try:
    #                 invoice.save(update_fields=['vat'])
    #             except:
    #                 pass
    # except:
    #     pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0007_auto_20180529_1601'),
    ]

    operations = [
        migrations.RunPython(recalculate, lambda *args, **kwargs: None)
    ]
