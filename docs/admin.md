# Django Admin

`InvoiceAdmin` is registered automatically when the `invoicing` app is installed. It provides a feature-rich interface for managing invoices.

## List display

The changelist shows: PK, type, origin, number, status, supplier, customer, annotated subtotal (total minus VAT), VAT, total, currency, issue date, payment term (days), overdue flag, and paid flag.

`status` is editable directly in the list view.

## Filters

| Filter | Description |
|---|---|
| `origin` | Issued vs. received |
| `type` | Invoice type (invoice, advance, proforma, credit note) |
| `status` | Payment/workflow status |
| `payment_method` | Bank transfer, cash, etc. |
| `delivery_method` | Personal pickup, mailing, digital |
| `OverdueFilter` | Yes / No |
| `NotExportedWithExporterListFilter` | Invoices not yet successfully exported by a specific exporter |
| `language` | Invoice language |
| `currency` | Invoice currency |

## Search

Full-text search across: `number`, `subtitle`, `note`, `supplier_name`, `customer_name`, `shipping_name`.

## Export actions

Export actions are injected dynamically from the configured managers. For each manager in `INVOICING_MANAGERS`:

1. All methods whose names start with `export_` are discovered.
2. Each method is wrapped as an admin action.
3. The action name is `{manager_class_name_lower}_{method_name}` (e.g. `pdfmanager_export_detail_pdf`).
4. The action label comes from the method's `short_description` attribute.

Only managers listed in `INVOICING_MANAGERS` contribute actions. To remove an action, remove its manager from the setting.

## NotExportedWithExporterListFilter

This list filter lets you find invoices that have never been successfully exported by a given exporter. It reads the `ExportItem` records created by `django-outputs` and excludes invoices that have at least one successful export for the chosen exporter path.

The filter choices are built dynamically from all `exporter_class` attributes of the configured managers.

## Additional admin action

| Action | Description |
|---|---|
| `recalculate_tax` | Re-runs `invoice.recalculate_tax()` on each selected invoice, recalculating the tax rate for all items based on the current taxation policy |

## Inline

`ItemInline` (`TabularInline`) shows item fields: title, quantity, unit, unit price, discount, tax rate, weight.
