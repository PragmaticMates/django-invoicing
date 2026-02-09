from django.db import migrations, models


def forwards_rename_invoice_origin(apps, schema_editor):
    """
    Rename existing invoice origins from legacy values to new ones:
    - OUTGOING -> ISSUED
    - INCOMING -> RECEIVED
    """
    Invoice = apps.get_model('invoicing', 'Invoice')

    Invoice.objects.filter(origin='OUTGOING').update(origin='ISSUED')
    Invoice.objects.filter(origin='INCOMING').update(origin='RECEIVED')


def backwards_rename_invoice_origin(apps, schema_editor):
    """
    Reverse origin rename if migration is rolled back:
    - ISSUED -> OUTGOING
    - RECEIVED -> INCOMING
    """
    Invoice = apps.get_model('invoicing', 'Invoice')

    Invoice.objects.filter(origin='ISSUED').update(origin='OUTGOING')
    Invoice.objects.filter(origin='RECEIVED').update(origin='INCOMING')


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0033_alter_invoice_constant_symbol_alter_invoice_currency_and_more'),
    ]

    operations = [
        migrations.RunPython(
            forwards_rename_invoice_origin,
            backwards_rename_invoice_origin,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='origin',
            field=models.CharField(
                verbose_name='origin',
                max_length=8,
                choices=[
                    ('RECEIVED', 'received invoice'),
                    ('ISSUED', 'issued invoice'),
                ],
                default='ISSUED',
            ),
        ),
    ]


