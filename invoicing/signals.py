from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from invoicing.models import Item


@receiver(post_save, sender=Item)
@receiver(post_delete, sender=Item)
def recalculate(instance, **kwargs):
    invoice = instance.invoice
    invoice.total = invoice.calculate_total()
    invoice.vat = invoice.calculate_vat()
    invoice.save(update_fields=['total', 'vat'])
