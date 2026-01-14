import logging

from django.db import transaction
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver, Signal
from invoicing.models import Item, Invoice, InvoiceExport

logger = logging.getLogger(__name__)


# Signal sent after invoice(s) are exported
# Always receives invoices as list/queryset (even for single invoice)
# Arguments: invoices, method, result, detail, creator
# Note: manager_path is derived automatically from sender class
invoices_exported = Signal()


@receiver(invoices_exported)
@transaction.atomic
def create_invoice_exports(sender, invoices, method, export_id, result, detail='', creator=None, **kwargs):
    """
    Signal receiver that creates InvoiceExport records for exported invoices.
    
    Uses bulk_create for efficiency (works for both single and multiple invoices).
    Derives manager_path automatically from sender class.
    Uses transaction.atomic to ensure all records are created or none.
    
    Args:
        sender: The sender of the signal (manager class, e.g., MRPManager)
        invoices: List or QuerySet of Invoice instances
        method: Method name used for export (e.g., 'export_via_api')
        export_id: Export identifier to group exports (e.g., 'admin-20240112143045')
        result: InvoiceExport.RESULT choice ('SUCCESS' or 'FAIL') - same for all invoices
        detail: Optional detail message (error message on failure) - same for all invoices
        creator: User who initiated the export (optional)
    
    Returns:
        tuple[str, list[InvoiceExport]]: export_id and list of created export records
    """
    if not invoices:
        logger.warning(
            "create_invoice_exports called with empty invoices list",
            extra={
                'export_id': export_id,
                'manager_path': f'{sender.__module__}.{sender.__name__}',
                'method': method
            }
        )
        return export_id, []
    
    # Derive manager_path from sender class
    manager_path = f'{sender.__module__}.{sender.__name__}'
    
    export_records = [
        InvoiceExport(
            invoice=invoice,
            export_id=export_id,
            manager_path=manager_path,
            method_path=method,
            result=result,
            detail=detail,
            creator=creator
        )
        for invoice in invoices
    ]
    
    created_records = InvoiceExport.objects.bulk_create(export_records)
    
    logger.info(
        f"Created {len(created_records)} InvoiceExport record(s) for export_id={export_id}",
        extra={
            'export_id': export_id,
            'manager_path': manager_path,
            'method': method,
            'result': result,
            'invoice_count': len(created_records),
            'creator_id': creator.id if creator else None
        }
    )
    
    return export_id, created_records


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
