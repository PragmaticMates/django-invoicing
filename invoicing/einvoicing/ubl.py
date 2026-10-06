"""
Peppol BIS Billing 3.0 UBL serializer.

``PeppolBIS3Builder(invoice).build()`` returns the UBL 2.1 Invoice (or
CreditNote, for ``Invoice.TYPE.CREDIT_NOTE``) as UTF-8 bytes. Building is
deterministic: the same invoice gives the same bytes, so the XML can be
stored, hashed and resent unchanged.

The builder only serializes. Whether the invoice is fit to be sent at all
(required data present, totals matching the stored ones) is the job of
``validation.preflight()``; whether the result complies is the job of
``validation.validate()``.

Element order follows the UBL 2.1 XSD sequences, which the schema enforces.
Override the ``get_*`` methods to adapt the mapping.
"""
import base64
from dataclasses import dataclass
from decimal import Decimal

from django.utils.module_loading import import_string
from lxml import etree

from invoicing.einvoicing import conf
from invoicing.einvoicing.calculations import CENT, compute_for_invoice
from invoicing.einvoicing.identifiers import (
    CREDIT_NOTE_TYPE_CODE, CUSTOMIZATION_ID, INVOICE_TYPE_CODE, PROFILE_ID,
)
from invoicing.einvoicing.vat import DEFAULT_EXEMPTION_REASON_CODES, VatCategory


CAC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
CBC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
INVOICE_NS = 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'
CREDIT_NOTE_NS = 'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2'


@dataclass(frozen=True)
class Attachment:
    """A document embedded into the invoice (BG-24), e.g. its PDF rendering."""
    filename: str
    content: bytes
    mime_code: str = 'application/pdf'
    description: str = ''


def get_builder(invoice, attachments=()):
    builder_class = import_string(conf.get('BUILDER_CLASS'))
    return builder_class(invoice, attachments=attachments)


def format_amount(value):
    return str(Decimal(value).quantize(CENT))


def format_decimal(value):
    """Shortest exact representation: 23.0 -> '23', 1.250 -> '1.25'."""
    text = format(Decimal(value).normalize(), 'f')
    return text


class PeppolBIS3Builder:
    def __init__(self, invoice, attachments=()):
        self.invoice = invoice
        self.attachments = tuple(attachments)
        self.totals = compute_for_invoice(invoice)
        self.currency = invoice.currency

    # Document kind

    @property
    def is_credit_note(self):
        return self.invoice.type == self.invoice.TYPE.CREDIT_NOTE

    @property
    def type_code(self):
        return CREDIT_NOTE_TYPE_CODE if self.is_credit_note else INVOICE_TYPE_CODE

    # Element helpers

    def cbc(self, parent, name, text=None, **attributes):
        element = etree.SubElement(parent, f'{{{CBC}}}{name}', {k: str(v) for k, v in attributes.items()})
        if text is not None:
            element.text = str(text)
        return element

    def cac(self, parent, name):
        return etree.SubElement(parent, f'{{{CAC}}}{name}')

    def amount(self, parent, name, value):
        return self.cbc(parent, name, format_amount(value), currencyID=self.currency)

    # Build

    def build(self):
        root = self.build_tree()
        return etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)

    def build_tree(self):
        invoice = self.invoice
        namespace = CREDIT_NOTE_NS if self.is_credit_note else INVOICE_NS
        root_name = 'CreditNote' if self.is_credit_note else 'Invoice'
        root = etree.Element(f'{{{namespace}}}{root_name}', nsmap={None: namespace, 'cac': CAC, 'cbc': CBC})

        self.cbc(root, 'CustomizationID', CUSTOMIZATION_ID)
        self.cbc(root, 'ProfileID', PROFILE_ID)
        self.cbc(root, 'ID', invoice.number)
        self.cbc(root, 'IssueDate', invoice.date_issue.isoformat())

        if self.is_credit_note:
            self.add_tax_point_date(root)
            self.cbc(root, 'CreditNoteTypeCode', self.type_code)
        else:
            self.cbc(root, 'DueDate', invoice.date_due.isoformat())
            self.cbc(root, 'InvoiceTypeCode', self.type_code)

        for note in self.get_notes():
            self.cbc(root, 'Note', note)

        if not self.is_credit_note:
            self.add_tax_point_date(root)

        self.cbc(root, 'DocumentCurrencyCode', self.currency)
        self.cbc(root, 'BuyerReference', self.get_buyer_reference())
        self.add_billing_references(root)
        self.add_attachments(root)
        self.add_supplier(root)
        self.add_customer(root)
        self.add_payment_means(root)
        self.add_tax_total(root)
        self.add_monetary_total(root)

        for index, line in enumerate(self.totals.lines, start=1):
            self.add_line(root, index, line)

        return root

    def add_tax_point_date(self, root):
        # BT-7, stated only when it differs from the issue date (as Slovak law asks)
        invoice = self.invoice
        if invoice.date_tax_point and invoice.date_tax_point != invoice.date_issue:
            self.cbc(root, 'TaxPointDate', invoice.date_tax_point.isoformat())

    # Header data

    def get_notes(self):
        return [self.invoice.note] if self.invoice.note else []

    def get_buyer_reference(self):
        # BIS requires a buyer reference (BT-10) or an order reference (BT-13);
        # without one from the buyer, the invoice number is the usual fallback
        return self.invoice.buyer_reference or self.invoice.number

    def get_billing_references(self):
        """[(number, issue date or None)] of the invoices a credit note corrects."""
        if not self.is_credit_note:
            return []

        references = [
            (related.number, related.date_issue)
            for related in self.invoice.related_invoices.order_by('date_issue', 'pk')
        ]

        if not references and self.invoice.related_document:
            references = [(self.invoice.related_document, None)]

        return references

    def add_billing_references(self, root):
        for number, issue_date in self.get_billing_references():
            reference = self.cac(self.cac(root, 'BillingReference'), 'InvoiceDocumentReference')
            self.cbc(reference, 'ID', number)
            if issue_date:
                self.cbc(reference, 'IssueDate', issue_date.isoformat())

    def add_attachments(self, root):
        for attachment in self.attachments:
            reference = self.cac(root, 'AdditionalDocumentReference')
            self.cbc(reference, 'ID', attachment.filename)
            if attachment.description:
                self.cbc(reference, 'DocumentDescription', attachment.description)
            self.cbc(
                self.cac(reference, 'Attachment'), 'EmbeddedDocumentBinaryObject',
                base64.b64encode(attachment.content).decode('ascii'),
                mimeCode=attachment.mime_code, filename=attachment.filename,
            )

    # Parties

    @property
    def states_vat_identifiers(self):
        # An invoice not subject to VAT must not state any VAT identifier (BR-O-02)
        return VatCategory.NOT_SUBJECT not in self.totals.categories

    def get_seller_legal_info(self):
        """Seller additional legal information (BT-33), e.g. legal form and commercial register entry."""
        info = self.invoice.supplier_additional_info or {}
        parts = [info.get('legal_form'), info.get('register')]
        return ', '.join(str(part) for part in parts if part)

    def add_address(self, party, street, city, zip_code, country):
        address = self.cac(party, 'PostalAddress')
        if street:
            self.cbc(address, 'StreetName', street)
        if city:
            self.cbc(address, 'CityName', city)
        if zip_code:
            self.cbc(address, 'PostalZone', zip_code)
        self.cbc(self.cac(address, 'Country'), 'IdentificationCode', country.code if country else '')

    def add_tax_scheme(self, party, company_id, scheme):
        tax_scheme = self.cac(party, 'PartyTaxScheme')
        self.cbc(tax_scheme, 'CompanyID', company_id)
        self.cbc(self.cac(tax_scheme, 'TaxScheme'), 'ID', scheme)

    def add_supplier(self, root):
        invoice = self.invoice
        party = self.cac(self.cac(root, 'AccountingSupplierParty'), 'Party')

        self.cbc(party, 'EndpointID', invoice.supplier_endpoint_id, schemeID=invoice.supplier_endpoint_scheme)
        self.cbc(self.cac(party, 'PartyName'), 'Name', invoice.supplier_name)
        self.add_address(party, invoice.supplier_street, invoice.supplier_city, invoice.supplier_zip, invoice.supplier_country)

        if invoice.supplier_vat_id and self.states_vat_identifiers:
            self.add_tax_scheme(party, invoice.supplier_vat_id, 'VAT')  # BT-31, IČ DPH
        if invoice.supplier_tax_id:
            self.add_tax_scheme(party, invoice.supplier_tax_id, 'TAX')  # BT-32, DIČ

        legal_entity = self.cac(party, 'PartyLegalEntity')
        self.cbc(legal_entity, 'RegistrationName', invoice.supplier_name)
        if invoice.supplier_registration_id:
            self.cbc(legal_entity, 'CompanyID', invoice.supplier_registration_id)  # BT-30, IČO
        legal_info = self.get_seller_legal_info()
        if legal_info:
            self.cbc(legal_entity, 'CompanyLegalForm', legal_info)

        if invoice.issuer_name or invoice.issuer_phone or invoice.issuer_email:
            contact = self.cac(party, 'Contact')
            if invoice.issuer_name:
                self.cbc(contact, 'Name', invoice.issuer_name)
            if invoice.issuer_phone:
                self.cbc(contact, 'Telephone', invoice.issuer_phone)
            if invoice.issuer_email:
                self.cbc(contact, 'ElectronicMail', invoice.issuer_email)

    def add_customer(self, root):
        invoice = self.invoice
        party = self.cac(self.cac(root, 'AccountingCustomerParty'), 'Party')

        self.cbc(party, 'EndpointID', invoice.customer_endpoint_id, schemeID=invoice.customer_endpoint_scheme)
        self.cbc(self.cac(party, 'PartyName'), 'Name', invoice.customer_name)
        self.add_address(party, invoice.customer_street, invoice.customer_city, invoice.customer_zip, invoice.customer_country)

        if invoice.customer_vat_id and self.states_vat_identifiers:
            self.add_tax_scheme(party, invoice.customer_vat_id, 'VAT')  # BT-48

        legal_entity = self.cac(party, 'PartyLegalEntity')
        self.cbc(legal_entity, 'RegistrationName', invoice.customer_name)
        if invoice.customer_registration_id:
            self.cbc(legal_entity, 'CompanyID', invoice.customer_registration_id)  # BT-47

        if invoice.customer_phone or invoice.customer_email:
            contact = self.cac(party, 'Contact')
            if invoice.customer_phone:
                self.cbc(contact, 'Telephone', invoice.customer_phone)
            if invoice.customer_email:
                self.cbc(contact, 'ElectronicMail', invoice.customer_email)

    # Payment

    def get_payment_means_code(self):
        return conf.get('PAYMENT_MEANS_CODES').get(self.invoice.payment_method)

    def get_payment_id(self):
        # Remittance information (BT-83): the variable symbol Slovak banks pair payments by
        invoice = self.invoice
        return str(invoice.variable_symbol) if invoice.variable_symbol is not None else invoice.number

    def add_payment_means(self, root):
        invoice = self.invoice
        code = self.get_payment_means_code()

        if self.is_credit_note or not code:
            return

        payment_means = self.cac(root, 'PaymentMeans')
        self.cbc(payment_means, 'PaymentMeansCode', code)
        self.cbc(payment_means, 'PaymentID', self.get_payment_id())

        if code == '30' and invoice.bank_iban:
            account = self.cac(payment_means, 'PayeeFinancialAccount')
            self.cbc(account, 'ID', str(invoice.bank_iban).replace(' ', ''))
            if invoice.bank_swift_bic:
                self.cbc(self.cac(account, 'FinancialInstitutionBranch'), 'ID', invoice.bank_swift_bic)

    # Totals

    def get_exemption_reason(self, category):
        """(code, text) for categories which need one (BT-121, BT-120)."""
        if category not in VatCategory.REQUIRES_EXEMPTION_REASON:
            return None, None

        invoice = self.invoice
        code = invoice.vat_exemption_reason_code or DEFAULT_EXEMPTION_REASON_CODES.get(category)
        return code or None, invoice.vat_exemption_reason or None

    def add_tax_category(self, parent, element_name, category, rate, with_exemption=False):
        tax_category = self.cac(parent, element_name)
        self.cbc(tax_category, 'ID', category)
        if rate is not None:
            self.cbc(tax_category, 'Percent', format_decimal(rate))
        if with_exemption:
            code, text = self.get_exemption_reason(category)
            if code:
                self.cbc(tax_category, 'TaxExemptionReasonCode', code)
            if text:
                self.cbc(tax_category, 'TaxExemptionReason', text)
        self.cbc(self.cac(tax_category, 'TaxScheme'), 'ID', 'VAT')

    def add_tax_total(self, root):
        tax_total = self.cac(root, 'TaxTotal')
        self.amount(tax_total, 'TaxAmount', self.totals.tax_amount)

        for row in self.totals.vat_breakdown:
            subtotal = self.cac(tax_total, 'TaxSubtotal')
            self.amount(subtotal, 'TaxableAmount', row.taxable_amount)
            self.amount(subtotal, 'TaxAmount', row.tax_amount)
            self.add_tax_category(subtotal, 'TaxCategory', row.category, row.rate, with_exemption=True)

    def add_monetary_total(self, root):
        totals = self.totals
        monetary_total = self.cac(root, 'LegalMonetaryTotal')
        self.amount(monetary_total, 'LineExtensionAmount', totals.line_extension_amount)
        self.amount(monetary_total, 'TaxExclusiveAmount', totals.tax_exclusive_amount)
        self.amount(monetary_total, 'TaxInclusiveAmount', totals.tax_inclusive_amount)
        if totals.prepaid_amount:
            self.amount(monetary_total, 'PrepaidAmount', totals.prepaid_amount)
        self.amount(monetary_total, 'PayableAmount', totals.payable_amount)

    # Lines

    def get_unit_code(self, item):
        return conf.get('UNIT_CODES').get(item.unit, conf.get('DEFAULT_UNIT_CODE'))

    def get_item_name_and_description(self, item):
        lines = [line.strip() for line in item.title.strip().splitlines() if line.strip()]
        name = lines[0] if lines else item.title
        description = item.title.strip() if len(lines) > 1 else None
        return name, description

    def add_line(self, root, index, line):
        item = line.input.reference
        line_name = 'CreditNoteLine' if self.is_credit_note else 'InvoiceLine'
        quantity_name = 'CreditedQuantity' if self.is_credit_note else 'InvoicedQuantity'

        element = self.cac(root, line_name)
        self.cbc(element, 'ID', index)
        self.cbc(element, quantity_name, format_decimal(line.input.quantity), unitCode=self.get_unit_code(item))
        self.amount(element, 'LineExtensionAmount', line.net_amount)

        if line.allowance_amount:
            allowance = self.cac(element, 'AllowanceCharge')
            self.cbc(allowance, 'ChargeIndicator', 'false')
            self.cbc(allowance, 'AllowanceChargeReasonCode', '95')  # discount
            self.cbc(allowance, 'AllowanceChargeReason', 'Discount')
            self.cbc(allowance, 'MultiplierFactorNumeric', format_decimal(line.input.discount_percent))
            self.amount(allowance, 'Amount', line.allowance_amount)
            self.amount(allowance, 'BaseAmount', line.gross_amount)

        item_element = self.cac(element, 'Item')
        name, description = self.get_item_name_and_description(item)
        if description:
            self.cbc(item_element, 'Description', description)
        self.cbc(item_element, 'Name', name)
        self.add_tax_category(item_element, 'ClassifiedTaxCategory', line.vat_category, line.vat_rate)

        price = self.cac(element, 'Price')
        self.cbc(price, 'PriceAmount', format_decimal(line.input.unit_price), currencyID=self.currency)
