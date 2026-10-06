from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0035_alter_item_quantity'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='buyer_reference',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='invoice',
            name='supplier_endpoint_scheme',
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.AddField(
            model_name='invoice',
            name='supplier_endpoint_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='invoice',
            name='customer_endpoint_scheme',
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.AddField(
            model_name='invoice',
            name='customer_endpoint_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='invoice',
            name='vat_exemption_reason',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='invoice',
            name='vat_exemption_reason_code',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='item',
            name='vat_category',
            field=models.CharField(blank=True, max_length=2),
        ),
    ]
