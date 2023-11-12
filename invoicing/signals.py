from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from invoicing.models import Item, Invoice
# from pragmatic.signals import temporary_disconnect_signal


@receiver(post_save, sender=Item)
@receiver(post_delete, sender=Item)
def recalculate_total_by_items(instance, **kwargs):
    invoice = instance.invoice
    invoice.total = invoice.calculate_total()
    invoice.vat = invoice.calculate_vat()
    # with temporary_disconnect_signal(signal=post_save, receiver=recalculate_total_by_invoice, sender=Invoice):
    invoice.save(update_fields=['total', 'vat'])


@receiver(pre_save, sender=Invoice)
def recalculate_total_by_invoice(instance, **kwargs):
    invoice = instance
    invoice.total = invoice.calculate_total()
    invoice.vat = invoice.calculate_vat()
