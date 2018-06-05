
from django.db import migrations, transaction
from invoicing.models import Invoice


def update_credit_notes(*args, **kwargs):
    Invoice.objects.filter(type='VAT_CREDIT_NOTE').update(type='CREDIT_NOTE')


class Migration(migrations.Migration):
    dependencies = [
        ('invoicing', '0015_auto_20180605_1232'),
    ]

    operations = [
        migrations.RunPython(update_credit_notes, lambda *args, **kwargs: None)
    ]
