# Generated by Django 2.2.23 on 2023-09-12 02:58

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0028_auto_20230912_0404'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='already_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
