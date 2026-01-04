import functools
import warnings
from decimal import Decimal

import binascii

from django.conf import settings
from django.utils.module_loading import import_string
from requests_futures import sessions


def get_invoices_in_pdf(invoices):
    # TODO: replace with invoicing_settings
    invoicing_formatter = getattr(settings, 'INVOICING_FORMATTER', 'invoicing.formatters.html.BootstrapHTMLFormatter')
    formatter_class = import_string(invoicing_formatter)
    htmltopdf_api_url = getattr(settings, 'HTMLTOPDF_API_URL', None)
    printmyweb_url = getattr(settings, 'PRINTMYWEB_URL', None)
    printmyweb_token = getattr(settings, 'PRINTMYWEB_TOKEN', None)
    requests = []
    export_files = []

    print_api_url = htmltopdf_api_url or printmyweb_url

    for invoice in invoices:
        formatter = formatter_class(invoice)
        invoice_content = formatter.get_response().content

        hex_4_bytes = binascii.hexlify(invoice_content)[0:8]

        # Look at the first 4 bytes of the file.
        # PDF has "%PDF" (hex 25 50 44 46) and ZIP has hex 50 4B 03 04.
        is_pdf = hex_4_bytes == b'25504446'

        if is_pdf:
            export_files.append({'name': str(invoice) + '.pdf', 'content': invoice_content})
        else:
            if print_api_url is None:
                raise NotImplementedError('Invoice content is not PDF and print_api_url is not set!')
            else:
                requests.append({'invoice': str(invoice), 'html_content': invoice_content})

    if len(requests) > 0:
        session = sessions.FuturesSession(max_workers=3)

        kwargs = {}
        if printmyweb_token:
            kwargs['headers'] = {
                'api-key': printmyweb_token
            }

        futures = [
            {'invoice': request.get('invoice'), 'future': session.post(
                url=print_api_url,
                data=request.get('html_content'),
                **kwargs
            )}
            for request in requests]

        for f in futures:
            file_name = f.get('invoice')
            result = f.get('future').result()
            export_files.append({'name': file_name + '.pdf', 'content': result.content})

    return export_files


def deprecated(func):
    """This decorator can be used to mark functions or properties as deprecated."""

    # Handle property objects
    if isinstance(func, property):
        prop_fget = func.fget
        prop_name = prop_fget.__name__ if prop_fget else "unknown"

        @functools.wraps(prop_fget)
        def deprecated_getter(self):
            warnings.warn(
                f"{prop_name} is deprecated and will be removed in a future version.",
                category=DeprecationWarning,
                stacklevel=2
            )
            return prop_fget(self)

        return property(
            fget=deprecated_getter,
            fset=func.fset,
            fdel=func.fdel,
            doc=func.__doc__
        )

    # Handle regular functions/methods
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__name__} is deprecated and will be removed in a future version.",
            category=DeprecationWarning,
            stacklevel=2
        )
        return func(*args, **kwargs)

    return wrapper

def format_decimal(value, decimal_places=2):
    """Format decimal value with specified number of decimal places."""
    if value is None:
        return format_decimal(0, decimal_places)
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except (ValueError, TypeError):
            return format_decimal(0, decimal_places)
    try:
        return "{:.{places}f}".format(float(value), places=decimal_places)
    except (ValueError, TypeError):
        return format_decimal(0, decimal_places)


def get_task_decorator(queue=None):
    """
    Import task decorator based on INVOICING_TASK_BACKEND setting.

    Default: 'django.tasks.task' (Django 6.0+)
    Examples: 'django_rq.job', 'celery.shared_task'

    Args:
        queue: Queue name for backends that support it (e.g. django_rq)

    Raises ImportError if the module is not installed.
    """
    task_backend = getattr(settings, 'INVOICING_TASK_BACKEND', 'django.tasks.task')

    try:
        decorator = import_string(task_backend)
    except ImportError as e:
        raise ImportError(
            f"Task backend '{task_backend}' is not installed. "
            f"Install the required package or set INVOICING_TASK_BACKEND to a valid decorator path."
        ) from e

    # django_rq.job requires queue name as first argument
    if task_backend == 'django_rq.job' and queue:
        return decorator(queue)

    return decorator