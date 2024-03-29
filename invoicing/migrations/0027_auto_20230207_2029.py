# Generated by Django 3.1.14 on 2023-02-07 19:29

from django.db import migrations
from internationalflavor.iban import BICField


class Migration(migrations.Migration):
    dependencies = [
        ('invoicing', '0026_auto_20210622_1055'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='bank_swift_bic',
            field=BICField(blank=True, max_length=11, verbose_name='Bank SWIFT / BIC'),
        ),
    ]
