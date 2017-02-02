# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0002_auto_20170123_1806'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='discount',
            field=models.DecimalField(default=0, verbose_name='discount (%)', max_digits=4, decimal_places=1),
            preserve_default=True,
        )
    ]
