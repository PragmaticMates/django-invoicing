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
    #             invoice.save(update_fields=['vat'])
    # except:
    #     pass


class Migration(migrations.Migration):
    dependencies = [
        ('invoicing', '0013_rename_full_number_to_number'),
    ]

    operations = [
        migrations.RunPython(recalculate, lambda *args, **kwargs: None)
    ]
