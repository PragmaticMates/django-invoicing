import os

from django.core.validators import EMPTY_VALUES
from django.template import loader
from lxml import etree

from invoicing.managers import get_invoice_details_manager
from invoicing.models import Invoice

from outputs.mixins import ExporterMixin
from outputs.models import Export

from invoicing.utils import format_decimal


class InvoiceMrpExporterMixin(ExporterMixin):
    export_format = Export.FORMAT_XML_MRP
    export_context = Export.CONTEXT_LIST
    queryset = Invoice.objects.all()
    filename = 'MRP_invoice_export_v2.xml'
    
    def get_queryset(self):
        return self.queryset

    def get_whole_queryset(self, params):
        return super().get_whole_queryset(params) \
            .order_by('-pk').distinct()

    def get_message_body(self, count):
        template = loader.get_template("outputs/export_message_body.html")
        return template.render({"count": count, "filtered_values": None})

    def export(self):
        self.write_data(self.output)

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

    def get_mrp_data_element(self):
        """
        Generate and return the MRPKSData XML element tree.
        This can be used for API calls or manual XML generation.
        """
        mrp_data = etree.Element("MRPKSData", version="2.0")
        incoming_invoices = etree.SubElement(mrp_data, self.get_invoice_root_element())

        for invoice in self.get_queryset():
            invoice_elem = etree.SubElement(incoming_invoices, "Invoice")

            # ==== HEADER ====
            etree.SubElement(invoice_elem, "DocumentNumber").text = str(invoice.number[:10] or "")
            etree.SubElement(invoice_elem, "IssueDate").text = invoice.date_issue.strftime("%Y-%m-%d")
            etree.SubElement(invoice_elem, "CurrencyCode").text = invoice.currency or ""
            etree.SubElement(invoice_elem, "ValuesWithTax").text = "T" if invoice.type in ['INVOICE', 'ADVANCE'] else "F"

            # TaxCode is required - always include it, default to "0" if not available
            vat_type = get_invoice_details_manager().vat_type(invoice)
            if vat_type not in EMPTY_VALUES:
                etree.SubElement(invoice_elem, "TaxCode").text = str(vat_type)
            else:
                etree.SubElement(invoice_elem, "TaxCode").text = "0"

            etree.SubElement(invoice_elem, "DocType").text = "" if invoice.type == 'INVOICE' else \
                "D" if invoice.type == 'CREDIT_NOTE' else "X" if invoice.type == 'ADVANCE' else "P"
            etree.SubElement(invoice_elem, "BaseTaxRateAmount").text = format_decimal(invoice.total or 0)
            etree.SubElement(invoice_elem, "BaseTaxRateTax").text = format_decimal(invoice.vat or 0)
            etree.SubElement(invoice_elem, "TotalWithTaxCurr").text = format_decimal(invoice.total or 0)
            etree.SubElement(invoice_elem, "TaxPointDate").text = invoice.date_tax_point.strftime("%Y-%m-%d")
            etree.SubElement(invoice_elem, "DeliveryDate").text = invoice.date_issue.strftime("%Y-%m-%d")
            etree.SubElement(invoice_elem, "PaymentDueDate").text = invoice.date_due.strftime("%Y-%m-%d")

            advance_notice = get_invoice_details_manager().advance_notice(invoice)
            if advance_notice not in EMPTY_VALUES:
                etree.SubElement(invoice_elem, "DoubleEntryBookkeepingCode").text = advance_notice

            # Note should be HeadNote according to XSD
            head_note = (invoice.note or "").strip()
            if head_note:
                etree.SubElement(invoice_elem, "HeadNote").text = head_note[:30]

            etree.SubElement(invoice_elem, "VariableSymbol").text = str(invoice.variable_symbol or '')[:10]
            etree.SubElement(invoice_elem, "ConstantSymbol").text = str(invoice.constant_symbol or '')[:8]
            etree.SubElement(invoice_elem, "SpecificSymbol").text = str(invoice.specific_symbol or '')[:10]
            etree.SubElement(invoice_elem, "OriginalDocumentNumber").text = (invoice.related_document or "")[:32]
            etree.SubElement(invoice_elem, "InvoiceType").text = {
                'INVOICE': 'F', 'ADVANCE': 'X', 'CREDIT_NOTE': 'P'
            }.get(invoice.type, 'F')
            etree.SubElement(invoice_elem, "DeliveryTypeCode").text = invoice.delivery_method or ""

            # For incoming invoices only, include header-level reverse charge
            # totals as allowed by the incoming_invoices.xsd schema.
            if (
                self.get_invoice_root_element() == "IncomingInvoices"
                and invoice.is_reverse_charge()
            ):
                etree.SubElement(invoice_elem, "ReverseChargeBaseTaxRateAmount").text = format_decimal(invoice.total or 0)
                etree.SubElement(invoice_elem, "ReverseChargeBaseTaxRateTax").text = format_decimal(invoice.vat or 0)

            if hasattr(invoice, "orders") and invoice.orders.exists():
                first_order = invoice.orders.first()
                etree.SubElement(invoice_elem, "OrderNumber").text = (first_order.order_number or "")[:20]

            # ==== COMPANY ====
            company = etree.SubElement(invoice_elem, "Company")
            self.fill_company(invoice, company)

            # ==== COMPANY / BANK ACCOUNTS ====
            if invoice.bank_iban or invoice.bank_name:
                bankaccounts = etree.SubElement(company, "BankAccounts")
                bank = etree.SubElement(bankaccounts, "BankAccount")
                etree.SubElement(bank, "Name").text = (invoice.bank_name or "")[:100]
                etree.SubElement(bank, "IBAN").text = (invoice.bank_iban or "")[:34]
                etree.SubElement(bank, "BIC").text = (invoice.bank_swift_bic or "")[:11]
                etree.SubElement(bank, "CurrencyCode").text = invoice.currency or ""

            # Items subnode
            items_elem = etree.SubElement(invoice_elem, "Items")

            for item in invoice.item_set.all():
                item_elem = etree.SubElement(items_elem, "Item")

                etree.SubElement(item_elem, "Description").text = item.title[:100] or ""
                etree.SubElement(item_elem, "Quantity").text = str(round(item.quantity, 6))
                etree.SubElement(item_elem, "UnitCode").text = ""
                etree.SubElement(item_elem, "UnitPrice").text = str(round(item.unit_price, 6))
                etree.SubElement(item_elem, "DiscountPercent").text = format_decimal(item.discount, 2)
                # Discount amount (not UnitDiscount) - total discount for the item
                if item.discount and item.discount > 0:
                    discount_amount = (item.unit_price * item.quantity) * (item.discount / 100)
                    etree.SubElement(item_elem, "Discount").text = format_decimal(discount_amount)
                etree.SubElement(item_elem, "TaxPercent").text = format_decimal(item.tax_rate if item.tax_rate else 0, 2)
                etree.SubElement(item_elem, "TaxAmount").text = format_decimal(item.vat, 2)
                etree.SubElement(item_elem, "TotalWeight").text = str(item.weight if item.weight is not None else 0)

            # ==== SUMS (SumValues) ====
            sum_values = etree.SubElement(invoice_elem, "SumValues")

            for vat_sum in invoice.vat_summary:
                sv = etree.SubElement(sum_values, "SumValue")
                # Use the same vat_type logic as in header
                sum_vat_type = get_invoice_details_manager().vat_type(invoice)
                if sum_vat_type not in EMPTY_VALUES:
                    etree.SubElement(sv, "TaxCode").text = str(sum_vat_type)
                else:
                    etree.SubElement(sv, "TaxCode").text = "0"
                etree.SubElement(sv, "TaxType").text = "1"  # or as per code: 1=base, 2=reduced etc.
                etree.SubElement(sv, "TaxPercent").text = format_decimal(vat_sum.get('rate') or 0, 2)
                etree.SubElement(sv, "CurrencyCode").text = invoice.currency or ""
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
                etree.SubElement(pay_elem, "PaymentDate").text = invoice.date_paid.strftime("%Y-%m-%d")
                etree.SubElement(pay_elem, "Amount").text = format_decimal(invoice.already_paid)
                etree.SubElement(pay_elem, "CurrencyCode").text = invoice.currency or ""

        # Validate XML against XSD schema
        self.validate_xml(mrp_data)
        
        return mrp_data

    def write_data(self, output):
        mrp_data = self.get_mrp_data_element()
        output_string = etree.tostring(mrp_data, pretty_print=True, xml_declaration=True, encoding='Windows-1250')
        output.write(output_string)


class OutgoingInvoiceMrpExporter(InvoiceMrpExporterMixin):
    queryset = Invoice.objects.outgoing()

    def get_invoice_root_element(self):
        return "IssuedInvoices"
    
    def get_xsd_filename(self):
        """Return the full path to the XSD schema file for outgoing invoices."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'xsd', 'issued_invoices.xsd')

    def fill_company(self, invoice, parent_element):
        etree.SubElement(parent_element, "CompanyId").text = (invoice.customer_registration_id or "")[:12]
        etree.SubElement(parent_element, "Name").text = (invoice.customer_name or "")[:50]
        etree.SubElement(parent_element, "Street").text = (invoice.customer_street or "").replace("'", "")[:30]
        etree.SubElement(parent_element, "ZipCode").text = (invoice.customer_zip or "")[:15]
        etree.SubElement(parent_element, "City").text = (invoice.customer_city or "")[:30]
        etree.SubElement(parent_element, "CountryCode").text = getattr(invoice.customer_country, "code", "") or ""
        etree.SubElement(parent_element, "VatNumber").text = (invoice.customer_vat_id or "")[:17]
        etree.SubElement(parent_element, "Phone").text = (invoice.customer_phone or "")[:30]
        etree.SubElement(parent_element, "Email").text = (invoice.customer_email or "")[:256]


class IncomingInvoiceMrpExporter(InvoiceMrpExporterMixin):
    queryset = Invoice.objects.incoming()

    def get_invoice_root_element(self):
        return "IncomingInvoices"
    
    def get_xsd_filename(self):
        """Return the full path to the XSD schema file for incoming invoices."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'xsd', 'incoming_invoices.xsd')

    def fill_company(self, invoice, parent_element):
        etree.SubElement(parent_element, "CompanyId").text = (invoice.supplier_registration_id or "")[:12]
        etree.SubElement(parent_element, "Name").text = (invoice.supplier_name or "")[:50]
        etree.SubElement(parent_element, "Street").text = (invoice.supplier_street or "").replace("'", "")[:30]
        etree.SubElement(parent_element, "ZipCode").text = (invoice.supplier_zip or "")[:15]
        etree.SubElement(parent_element, "City").text = (invoice.supplier_city or "")[:30]
        etree.SubElement(parent_element, "CountryCode").text = getattr(invoice.supplier_country, "code", "") or ""
        etree.SubElement(parent_element, "VatNumber").text = (invoice.supplier_vat_id or "")[:17]
        etree.SubElement(parent_element, "Phone").text = (invoice.issuer_phone or "")[:30]
        etree.SubElement(parent_element, "Email").text = (invoice.issuer_email or "")[:256]
