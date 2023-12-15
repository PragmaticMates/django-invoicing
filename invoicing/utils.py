import binascii

from django.conf import settings
from django.utils.module_loading import import_string
from requests_futures import sessions


def get_invoices_in_pdf(invoices):
    # TODO: replace with invoicing_settings
    invoicing_formatter = getattr(settings, 'INVOICING_FORMATTER', 'invoicing.formatters.html.BootstrapHTMLFormatter')
    formatter_class = import_string(invoicing_formatter)
    print_api_url = getattr(settings, 'HTMLTOPDF_API_URL', None)
    requests = []
    export_files = []

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
                raise NotImplementedError('Invoice content is not PDF and HTMLTOPDF_API_URL is not set.')
            else:
                requests.append({'invoice': str(invoice), 'html_content': invoice_content})

    if len(requests) > 0:
        session = sessions.FuturesSession(max_workers=3)
        futures = [
            {'invoice': request.get('invoice'), 'future': session.post(print_api_url, data=request.get('html_content'))}
            for request in requests]

        for f in futures:
            file_name = f.get('invoice')
            result = f.get('future').result()
            export_files.append({'name': file_name + '.pdf', 'content': result.content})

    return export_files
