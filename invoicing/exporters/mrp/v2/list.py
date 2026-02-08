import logging
import os
from datetime import datetime

from django.core.validators import EMPTY_VALUES
from django.template import loader
from lxml import etree


from invoicing.models import Invoice

from outputs.mixins import ExporterMixin
from outputs.models import Export

from invoicing.utils import format_decimal

from .utils import (
    sanitize_forbidden_chars,
    sanitize_uppercase_only,
    sanitize_zipcode,
    sanitize_city,
)

logger = logging.getLogger(__name__)


class InvoiceMrpListExporterMixin(ExporterMixin):
    export_format = Export.FORMAT_XML
    export_context = Export.CONTEXT_LIST
    queryset = Invoice.objects.all()
    export_per_item = False
    outputs = []
    filename = 'MRP_invoice_export.xml'
    api_request_command = ''
    xml_encoding = 'Windows-1250'
    request_timeout = 30

    def get_queryset(self):
        return self.queryset

    def get_whole_queryset(self, params):
        return super().get_whole_queryset(params) \
            .order_by('-pk').distinct()

    def get_message_body(self, count, file_url=None):
        template = loader.get_template("outputs/export_message_body.html")
        return template.render({"count": count})

    @staticmethod
    def vat_type(invoice):
        return ''

    # predkontacia
    @staticmethod
    def advance_notice(invoice):
        return ''

    def export(self):
        if self.export_per_item:
            self.write_data_per_item(self.outputs)
        else:
            self.write_data(self.output)


    def get_outputs_per_item(self):
        """
        Get separate output for each item in queryset.

        Returns list of output bytes, one per item.
        Only works if export_per_item=True and export() has been called.
        """
        return self.outputs

    def get_invoice_root_element(self):
        raise NotImplementedError()

    def get_xsd_filename(self):
        """Return the full path to the XSD schema file."""
        raise NotImplementedError()

    def fill_company(self, invoice, parent_element):
        raise NotImplementedError()

    def get_xsd_schema(self):
        """Get XSD schema for validation."""
        xsd_path = self.get_xsd_filename()

        try:
            if not os.path.exists(xsd_path):
                raise FileNotFoundError(
                    f"XSD schema file not found: {xsd_path}"
                )

            # Parse XSD schema
            xsd_doc = etree.parse(xsd_path)
            return etree.XMLSchema(xsd_doc)

        except FileNotFoundError as e:
            # If file doesn't exist, log warning but don't fail
            import warnings
            warnings.warn(
                f"Could not load MRP XSD schema from {xsd_path}: {e}. "
                f"XML validation will be skipped.",
                UserWarning
            )
            return None
        except Exception as e:
            # If schema parsing fails, log warning but don't fail
            import warnings
            warnings.warn(
                f"Could not parse MRP XSD schema from {xsd_path}: {e}. "
                f"XML validation will be skipped.",
                UserWarning
            )
            return None

    def validate_xml(self, xml_element):
        """
        Validate XML element against MRP XSD schema.

        Raises ValueError with detailed validation errors if validation fails.
        """
        schema = self.get_xsd_schema()

        # Skip validation if schema couldn't be loaded
        if schema is None:
            return

        # Validate the XML
        try:
            schema.assertValid(xml_element)
        except etree.DocumentInvalid as e:
            # Build detailed error message
            error_log = schema.error_log
            errors = []

            for error in error_log:
                error_msg = (
                    f"Line {error.line}, Column {error.column}: "
                    f"{error.message}"
                )
                errors.append(error_msg)

            error_details = "\n".join(errors)
            xsd_path = self.get_xsd_filename()
            raise ValueError(
                f"XML validation failed against MRP XSD schema ({xsd_path}):\n{error_details}"
            )

    def wrap_to_request_envelope(self, data_element, invoice):
        """
        Create mrpEnvelope XML structure with MRP data.

        Final structure:
        <mrpEnvelope>
          <body>
            <mrpRequest>
              <request command="IMPFV0" requestId="...">
              </request>
              <data>
                <MRPKSData version="2.0">...</MRPKSData>
              </data>
            </mrpRequest>
          </body>
        </mrpEnvelope>


        Returns:
            tuple: (xml_string, request_id)

        Raises:
            ValueError: If queryset is empty
        """
        xml_envelope = etree.Element("mrpEnvelope")
        body = etree.SubElement(xml_envelope, "body")

        mrp_request = etree.SubElement(body, "mrpRequest")
        request_id = f"{invoice.id}-{int(datetime.now().timestamp())}"
        request_elem = etree.SubElement(
            mrp_request,
            "request",
            command=self.api_request_command,
            requestId=request_id,
        )

        # data is a sibling of request, both inside mrpRequest
        data_elem = etree.SubElement(mrp_request, "data")
        data_elem.append(data_element)

        logger.debug(f"Created MRP envelope for invoice {invoice.number} with request_id: {request_id}")

        return xml_envelope

    def write_data(self, output):
        """
        Generate a single XML element containing all invoices and write it to output.

        Creates a MRPKSData element with all invoices from the queryset,
        validates the XML against the XSD schema, and writes the result
        to the provided output stream.

        Args:
            output: File-like object to write the XML string to.

        Raises:
            ValueError: If XML validation fails against the XSD schema.
        """
        # Generate single XML element with all invoices
        mrpks_data = etree.Element("MRPKSData", version="2.0")
        invoices_container = etree.SubElement(mrpks_data, self.get_invoice_root_element())

        for invoice in self.get_queryset():
            invoice_element = self.get_invoice_element(invoice)
            invoices_container.append(invoice_element)

        # Validate once for all invoices
        self.validate_xml(mrpks_data)
        xml_string = self.xml_to_string(mrpks_data)
        output.write(xml_string)

    def write_data_per_item(self, outputs):
        """
        Generate separate XML elements for each invoice and store them in self.outputs.

        For each invoice in the queryset, creates a MRPKSData element containing
        that single invoice, validates it, wraps it in a request envelope,
        and appends the result to self.outputs as a dictionary with keys
        'invoice' and 'xml_string'.

        The outputs can be retrieved later using get_outputs_per_item().
        This method is used when export_per_item=True.

        Note:
            This method does not return anything. Results are stored in
            self.outputs and can be accessed via get_outputs_per_item().
        """
        # Generate separate XML element for each invoice
        for invoice in self.get_queryset():
            invoice_element = self.get_invoice_element(invoice)

            # Create MRPKSData structure for single invoice
            mrpks_data = etree.Element("MRPKSData", version="2.0")
            invoices_container = etree.SubElement(mrpks_data, self.get_invoice_root_element())
            invoices_container.append(invoice_element)

            # Validate and wrap in request envelope
            self.validate_xml(mrpks_data)

            if self.output_type == Export.OUTPUT_TYPE_STREAM:
                mrpks_data = self.wrap_to_request_envelope(mrpks_data, invoice)

            xml_string = self.xml_to_string(mrpks_data)
            outputs.append({"invoice": invoice, "xml_string": xml_string})

    def xml_to_string(self, xml):
        """
        Convert an XML element tree to a formatted XML string.
        """
        return etree.tostring(
            xml,
            pretty_print=True,
            xml_declaration=True,
            encoding=self.xml_encoding
        )

    def get_invoice_element(self, invoice):
        invoice_elem = etree.Element("Invoice")

        # ==== HEADER ====
        etree.SubElement(invoice_elem, "DocumentNumber").text = sanitize_forbidden_chars(invoice.number, 10)
        etree.SubElement(invoice_elem, "IssueDate").text = invoice.date_issue.isoformat()
        etree.SubElement(invoice_elem, "CurrencyCode").text = sanitize_uppercase_only(invoice.currency, 3)
        etree.SubElement(invoice_elem, "ValuesWithTax").text = "T" if invoice.type in ['INVOICE', 'ADVANCE'] else "F"

        # TaxCode is required - always include it, default to "0" if not available
        vat_type = self.vat_type(invoice)
        if vat_type not in EMPTY_VALUES:
            etree.SubElement(invoice_elem, "TaxCode").text = str(vat_type)
        else:
            etree.SubElement(invoice_elem, "TaxCode").text = "0"

        etree.SubElement(invoice_elem, "DocType").text = "" if invoice.type == 'INVOICE' else \
            "D" if invoice.type == 'CREDIT_NOTE' else "X" if invoice.type == 'ADVANCE' else "P"
        etree.SubElement(invoice_elem, "BaseTaxRateAmount").text = format_decimal(invoice.subtotal or 0)
        etree.SubElement(invoice_elem, "BaseTaxRateTax").text = format_decimal(invoice.vat or 0)
        etree.SubElement(invoice_elem, "TaxPointDate").text = invoice.date_tax_point.isoformat()
        etree.SubElement(invoice_elem, "DeliveryDate").text = invoice.date_issue.isoformat()
        etree.SubElement(invoice_elem, "PaymentDueDate").text = invoice.date_due.isoformat()

        advance_notice = self.advance_notice(invoice)
        if advance_notice not in EMPTY_VALUES:
            etree.SubElement(invoice_elem, "DoubleEntryBookkeepingCode").text = advance_notice

        # Note should be HeadNote according to XSD
        head_note = (invoice.note or "").strip()
        if head_note:
            etree.SubElement(invoice_elem, "HeadNote").text = sanitize_forbidden_chars(head_note, 30)

        etree.SubElement(invoice_elem, "VariableSymbol").text = sanitize_forbidden_chars(invoice.variable_symbol, 10)
        etree.SubElement(invoice_elem, "ConstantSymbol").text = sanitize_forbidden_chars(invoice.constant_symbol, 8)
        etree.SubElement(invoice_elem, "SpecificSymbol").text = sanitize_forbidden_chars(invoice.specific_symbol, 10)
        etree.SubElement(invoice_elem, "OriginalDocumentNumber").text = sanitize_forbidden_chars(invoice.related_document, 32)
        etree.SubElement(invoice_elem, "InvoiceType").text = {
            'INVOICE': 'F', 'ADVANCE': 'X', 'CREDIT_NOTE': 'P'
        }.get(invoice.type, 'F')
        etree.SubElement(invoice_elem, "DeliveryTypeCode").text = sanitize_forbidden_chars(invoice.delivery_method, 10)

        # For received invoices only, include header-level reverse charge
        # totals as allowed by the received_invoices.xsd schema.
        if (
                self.get_invoice_root_element() == "IncomingInvoices"
                and invoice.is_reverse_charge()
        ):
            etree.SubElement(invoice_elem, "ReverseChargeBaseTaxRateAmount").text = format_decimal(invoice.total or 0)
            etree.SubElement(invoice_elem, "ReverseChargeBaseTaxRateTax").text = format_decimal(invoice.vat or 0)

        if hasattr(invoice, "orders") and invoice.orders.exists():
            first_order = invoice.orders.first()
            etree.SubElement(invoice_elem, "OrderNumber").text = sanitize_forbidden_chars(first_order.order_number, 20)

        # ==== COMPANY ====
        company = etree.SubElement(invoice_elem, "Company")
        self.fill_company(invoice, company)

        # ==== COMPANY / BANK ACCOUNTS ====
        if invoice.bank_iban or invoice.bank_name:
            bankaccounts = etree.SubElement(company, "BankAccounts")
            bank = etree.SubElement(bankaccounts, "BankAccount")
            etree.SubElement(bank, "Name").text = sanitize_forbidden_chars(invoice.bank_name, 100)
            etree.SubElement(bank, "IBAN").text = sanitize_forbidden_chars(invoice.bank_iban, 34)
            etree.SubElement(bank, "BIC").text = sanitize_forbidden_chars(invoice.bank_swift_bic, 12)
            etree.SubElement(bank, "CurrencyCode").text = sanitize_uppercase_only(invoice.currency, 3)

        # Items subnode
        items_elem = etree.SubElement(invoice_elem, "Items")

        for item in invoice.item_set.all():
            item_elem = etree.SubElement(items_elem, "Item")

            etree.SubElement(item_elem, "Description").text = sanitize_forbidden_chars(item.title, 100)
            etree.SubElement(item_elem, "Quantity").text = str(round(item.quantity, 6))
            etree.SubElement(item_elem, "UnitCode").text = ""
            etree.SubElement(item_elem, "UnitPrice").text = str(round(item.unit_price, 6))
            etree.SubElement(item_elem, "TaxPercent").text = format_decimal(item.tax_rate if item.tax_rate else 0, 2)
            etree.SubElement(item_elem, "TaxAmount").text = format_decimal(item.vat, 2)
            etree.SubElement(item_elem, "DiscountPercent").text = format_decimal(item.discount, 2)
            etree.SubElement(item_elem, "TotalWeight").text = str(item.weight if item.weight is not None else 0)

        # ==== SUMS (SumValues) ====
        sum_values = etree.SubElement(invoice_elem, "SumValues")

        for vat_sum in invoice.vat_summary:
            sv = etree.SubElement(sum_values, "SumValue")
            # Use the same vat_type logic as in header
            sum_vat_type = self.vat_type(invoice)
            if sum_vat_type not in EMPTY_VALUES:
                etree.SubElement(sv, "TaxCode").text = str(sum_vat_type)
            else:
                etree.SubElement(sv, "TaxCode").text = "0"
            etree.SubElement(sv, "TaxType").text = "1"  # or as per code: 1=base, 2=reduced etc.
            etree.SubElement(sv, "TaxPercent").text = format_decimal(vat_sum.get('rate') or 0, 2)
            etree.SubElement(sv, "CurrencyCode").text = sanitize_uppercase_only(invoice.currency, 3)
            etree.SubElement(sv, "Amount").text = format_decimal(vat_sum.get('base') or 0)
            etree.SubElement(sv, "Tax").text = format_decimal(vat_sum.get('vat') or 0)

            if invoice.is_reverse_charge():
                # Reverse charge is represented on the summary level,
                # as expected by the XSD (ReverseChargeAmount / ReverseChargeTax).
                etree.SubElement(sv, "ReverseChargeAmount").text = format_decimal(vat_sum.get('base') or 0)
                etree.SubElement(sv, "ReverseChargeTax").text = format_decimal(vat_sum.get('vat') or 0)

        # ==== PAYMENTS ====
        if invoice.date_paid and invoice.already_paid > 0:
            payments = etree.SubElement(invoice_elem, "Payments")
            pay_elem = etree.SubElement(payments, "Payment")
            etree.SubElement(pay_elem, "PaymentType").text = (
                "1" if invoice.payment_method in ("BANK_TRANSFER", "PAYMENT_CARD")
                else "2" if invoice.payment_method in ("CASH", "CASH_ON_DELIVERY")
                else "0"
            )
            etree.SubElement(pay_elem, "PaymentDate").text = invoice.date_paid.isoformat()
            etree.SubElement(pay_elem, "Amount").text = format_decimal(invoice.already_paid)
            etree.SubElement(pay_elem, "CurrencyCode").text = sanitize_uppercase_only(invoice.currency, 3)

        return invoice_elem


class IssuedInvoiceMrpListExporter(InvoiceMrpListExporterMixin):
    queryset = Invoice.objects.issued()
    filename = 'MRP_issued_invoice_export.xml'
    api_request_command = "IMPFV0"

    def get_invoice_root_element(self):
        return "IssuedInvoices"

    def get_xsd_filename(self):
        """Return the full path to the XSD schema file for issued invoices."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'xsd', 'issued_invoices.xsd')

    def fill_company(self, invoice, parent_element):
        etree.SubElement(parent_element, "CompanyId").text = sanitize_forbidden_chars(invoice.customer_registration_id, 12)
        etree.SubElement(parent_element, "Name").text = sanitize_forbidden_chars(invoice.customer_name, 50)
        etree.SubElement(parent_element, "Street").text = sanitize_forbidden_chars(invoice.customer_street, 30)
        etree.SubElement(parent_element, "ZipCode").text = sanitize_zipcode(invoice.customer_zip)
        etree.SubElement(parent_element, "City").text = sanitize_city(invoice.customer_city)
        etree.SubElement(parent_element, "CountryCode").text = sanitize_uppercase_only(getattr(invoice.customer_country, "code", ""), 10)
        etree.SubElement(parent_element, "VatNumber").text = sanitize_forbidden_chars(invoice.customer_vat_id, 17)
        etree.SubElement(parent_element, "Phone").text = sanitize_forbidden_chars(invoice.customer_phone, 30)
        etree.SubElement(parent_element, "Email").text = sanitize_forbidden_chars(invoice.customer_email, 256)


class ReceivedInvoiceMrpListExporter(InvoiceMrpListExporterMixin):
    queryset = Invoice.objects.received()
    filename = 'MRP_received_invoice_export.xml'
    api_request_command = "IMPFP0"

    def get_invoice_root_element(self):
        return "IncomingInvoices"

    def get_xsd_filename(self):
        """Return the full path to the XSD schema file for incoming invoices."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'xsd', 'received_invoices.xsd')

    def fill_company(self, invoice, parent_element):
        etree.SubElement(parent_element, "CompanyId").text = sanitize_forbidden_chars(invoice.supplier_registration_id, 12)
        etree.SubElement(parent_element, "Name").text = sanitize_forbidden_chars(invoice.supplier_name, 50)
        etree.SubElement(parent_element, "Street").text = sanitize_forbidden_chars(invoice.supplier_street, 30)
        etree.SubElement(parent_element, "ZipCode").text = sanitize_zipcode(invoice.supplier_zip)
        etree.SubElement(parent_element, "City").text = sanitize_city(invoice.supplier_city)
        etree.SubElement(parent_element, "CountryCode").text = sanitize_uppercase_only(getattr(invoice.supplier_country, "code", ""), 10)
        etree.SubElement(parent_element, "VatNumber").text = sanitize_forbidden_chars(invoice.supplier_vat_id, 17)
        etree.SubElement(parent_element, "Phone").text = sanitize_forbidden_chars(invoice.issuer_phone, 30)
        etree.SubElement(parent_element, "Email").text = sanitize_forbidden_chars(invoice.issuer_email, 256)
