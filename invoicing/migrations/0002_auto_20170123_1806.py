# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invoice',
            name='discount',
        ),
        migrations.AddField(
            model_name='item',
            name='discount',
            field=models.DecimalField(default=0, verbose_name='discount (%)', max_digits=3, decimal_places=1),
            preserve_default=True,
        )
    ]
