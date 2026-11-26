"""
Checks on the invoice itself, before any XML is built: is it something this
library can turn into a correct e-invoice, and would that e-invoice say the
same as the invoice (and its PDF) already does?
"""
from invoicing.einvoicing import conf
from invoicing.einvoicing.calculations import ReconciliationError, compute, line_inputs_for_invoice, reconcile
from invoicing.einvoicing.identifiers import IdentifierError, ParticipantId
from invoicing.einvoicing.vat import DEFAULT_EXEMPTION_REASON_CODES, VatCategory, VatCategoryError
from invoicing.einvoicing.validation.report import ValidationReport


def _add(report, rule, message):
    report.add(f'PREFLIGHT-{rule}', message, 'preflight')


def preflight(invoice):
    report = ValidationReport()

    if invoice.type not in (invoice.TYPE.INVOICE, invoice.TYPE.CREDIT_NOTE):
        _add(report, 'TYPE', f'{invoice.get_type_display()} is not a tax document and cannot be sent as an e-invoice')

    if not invoice.number:
        _add(report, 'NUMBER', 'The invoice has no number')

    allowed_currencies = conf.get('ALLOWED_CURRENCIES')
    if allowed_currencies is not None and invoice.currency not in allowed_currencies:
        _add(report, 'CURRENCY', f'Currency {invoice.currency} is not supported (allowed: {", ".join(allowed_currencies)})')

    allowed_countries = conf.get('ALLOWED_CUSTOMER_COUNTRIES')
    customer_country = invoice.customer_country.code if invoice.customer_country else ''
    if allowed_countries is not None and customer_country not in allowed_countries:
        _add(report, 'COUNTRY', f'Customers from {customer_country or "an unknown country"} are not supported')

    if invoice.credit:
        # credit is deducted after VAT, which EN 16931 has no element for
        _add(report, 'CREDIT', 'Invoices with a credit deduction cannot be sent as an e-invoice')

    for role in ('supplier', 'customer'):
        scheme = getattr(invoice, f'{role}_endpoint_scheme')
        endpoint = getattr(invoice, f'{role}_endpoint_id')
        try:
            ParticipantId(scheme, endpoint)
        except IdentifierError:
            _add(report, f'{role.upper()}-ENDPOINT', f'The {role} has no valid electronic address (Peppol ID), got {scheme}:{endpoint}')

    if invoice.payment_method == invoice.PAYMENT_METHOD.BANK_TRANSFER and not invoice.bank_iban \
            and invoice.type != invoice.TYPE.CREDIT_NOTE:
        _add(report, 'IBAN', 'Bank transfer needs the account IBAN')

    if invoice.type == invoice.TYPE.CREDIT_NOTE and not invoice.related_document and not invoice.related_invoices.exists():
        _add(report, 'CREDIT-NOTE-REFERENCE', 'A credit note has to refer to the invoice it corrects')

    try:
        line_inputs = line_inputs_for_invoice(invoice)
    except VatCategoryError as error:
        _add(report, 'VAT-CATEGORY', str(error))
        return report

    if not line_inputs:
        _add(report, 'ITEMS', 'The invoice has no items')
        return report

    totals = compute(line_inputs, prepaid_amount=invoice.already_paid)

    if VatCategory.NOT_SUBJECT in totals.categories and len(totals.categories) > 1:
        # BR-O-11..14: an invoice not subject to VAT has no other VAT category
        _add(report, 'VAT-CATEGORY', 'Items not subject to VAT cannot be mixed with other VAT categories')

    exempt_categories = totals.categories & VatCategory.REQUIRES_EXEMPTION_REASON
    explicit_reason = invoice.vat_exemption_reason or invoice.vat_exemption_reason_code

    if len(exempt_categories) > 1 and explicit_reason:
        _add(report, 'EXEMPTION-REASON', 'One exemption reason cannot cover several VAT categories: '
                                         + ', '.join(sorted(exempt_categories)))

    for category in exempt_categories:
        if not explicit_reason and category not in DEFAULT_EXEMPTION_REASON_CODES:
            _add(report, 'EXEMPTION-REASON', f'VAT category {category} needs an exemption reason')

    try:
        reconcile(totals, invoice)
    except ReconciliationError as error:
        _add(report, 'TOTALS', f'The e-invoice totals would differ from the invoice: {error}')

    return report
