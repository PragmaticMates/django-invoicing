# Custom exporters

You can extend django-invoicing with your own export formats by writing a custom manager (and optionally a custom exporter class) and registering it in `INVOICING_MANAGERS`.

## Creating a custom manager

A manager must inherit from `InvoiceManagerMixin` and define one or more methods whose names start with `export_`. Those methods are automatically discovered by `InvoiceAdmin` and registered as Django Admin bulk actions.

```python
# myapp/exporters.py
from django.utils.translation import gettext_lazy as _
from invoicing.exporters.mixins import InvoiceManagerMixin


class MyCustomManager(InvoiceManagerMixin):

    def export_to_my_system(self, request, queryset):
        # validate first
        from myapp.exporters import MyExporter
        exporter = MyExporter(
            user=request.user,
            recipients=[request.user],
            params={},
            queryset=queryset,
        )
        if not self._is_export_qs_valid(request, exporter):
            return

        # do your export work here, using the validated queryset
        for invoice in exporter.get_queryset():
            ...

    export_to_my_system.short_description = _('Export to My System')
```

Register it:

```python
INVOICING_MANAGERS = {
    "myapp.exporters.MyCustomManager": {},
}
```

The action will appear in Admin as `mycustommanager_export_to_my_system` with the label "Export to My System".

## Using the built-in email delivery pipeline

For file-based exports that should be queued and emailed, use `_execute_export()` instead of implementing delivery yourself:

```python
class MyCustomManager(InvoiceManagerMixin):
    exporter_class = MyCustomExporter  # must be a django-outputs exporter

    def export_my_format(self, request, queryset, exporter_params=None):
        self._execute_export(request, self.exporter_class, exporter_params, queryset)

    export_my_format.short_description = _('Export to My Format')
```

`_execute_export()` handles:

- Queryset validation (non-empty; and when `required_origin` is set, all invoices must share that origin)
- Constructing default `exporter_params` if none are provided (`user`, `recipients`, `params`)
- Calling `outputs.usecases.execute_export()` in the current language
- Showing a success message in Admin

## Restricting to a specific origin

Set `required_origin` on your manager class to enforce that only issued or only received invoices may be exported:

```python
from invoicing.models import Invoice

class MyIssuedOnlyManager(InvoiceManagerMixin):
    required_origin = Invoice.ORIGIN.ISSUED
    ...
```

If the queryset contains invoices with a different origin, `_is_export_qs_valid()` will abort the export with a warning message.

## Overriding the exporter class at runtime

Users can override `exporter_class` (and `exporter_subclasses`) per manager via `INVOICING_MANAGERS` without changing any code:

```python
INVOICING_MANAGERS = {
    "myapp.exporters.MyCustomManager": {
        "exporter_class": "myapp.exporters.MyAlternativeExporter",
    },
}
```

This is handled by `InvoiceManagerMixin.__init__()`, which reads `manager_settings` and calls `import_string()` on the provided paths.
