import uuid
from collections import OrderedDict, defaultdict
from decimal import Decimal, ROUND_HALF_UP

from lxml import etree

from invoicing.models import Invoice
from invoicing.utils import get_invoices_in_pdf
from invoicing.taxation.eu import EUTaxationPolicy

from django.utils.translation import gettext_lazy as _, gettext

from outputs.mixins import ExporterMixin, ExcelExporterMixin, FilterExporterMixin
from outputs.models import Export
from pragmatic.utils import compress


# TODO: inherit from filterexporter mixin?
# class InvoiceXlsxListExporter(FilterExporterMixin, ExcelExporterMixin):
class InvoiceXlsxListExporter(ExcelExporterMixin):
    # filter_class = InvoiceFilter
    model = Invoice
    queryset = None
    filename = _('invoices.xlsx')

    @classmethod
    def get_model(cls):
        return cls.queryset.model if cls.queryset is not None else cls.model

    @classmethod
    def get_app_and_model(cls):
        return cls.get_model()._meta.label.split('.')

    @staticmethod
    def selectable_fields():
        # attribute, label, width, format (self.FORMATS), value
        return OrderedDict({
            gettext('Details'): [
                ('id', gettext('ID'), 7, 'integer'),
                ('created', gettext('Created'), 20, 'datetime'),
                ('get_type_display', gettext('Type'), 10, None, lambda value: value()),
                ('sequence', gettext('Sequence'), 10),
                ('number', gettext('Number'), 15),
                ('get_status_display', gettext('Status'), 10, None, lambda value: value()),
                ('subtitle', gettext('Subtitle'), 20),
                ('get_language_display', gettext('Language'), 10, None, lambda value: value()),
                ('note', gettext('Note'), 30),
            ],
            gettext('Dates'): [
                ('date_issue', gettext('Issue date'), 15, 'date'),
                ('date_tax_point', gettext('Tax point date'), 15, 'date'),
                ('date_due', gettext('Due date'), 15, 'date'),
                ('date_sent', gettext('Sent (date)'), 15, 'date'),
                ('date_paid', gettext('Date of payment'), 15, 'date', lambda value: value.date() if value else None),
                ('payment_term', gettext('Payment term (days)'), 15, 'integer'),
                ('overdue_days', gettext('Overdue (days)'), 15, 'integer', lambda value, obj: (
                    '=IF(TODAY()<=%(date_due)d, "", _xlfn.DAYS(TODAY(),%(date_due)d))' % {
                        'date_due': ExcelExporterMixin.to_excel_datetime(obj.date_due)
                    } if obj.status not in [Invoice.STATUS.PAID, Invoice.STATUS.CANCELED] else '', obj.overdue_days if obj.is_overdue else '')),
            ],
            gettext('Payment'): [
                ('total', gettext('Total'), 10),
                ('vat', gettext('VAT'), 10),
                ('get_currency_display', gettext('Currency'), 10, None, lambda value: value()),
                ('credit', gettext('Credit'), 10),
                ('get_payment_method_display', gettext('Payment method'), 20, None, lambda value: value()),
                ('constant_symbol', gettext('Constant symbol'), 20),
                ('variable_symbol', gettext('Variable symbol'), 20),
                ('specific_symbol', gettext('Specific symbol'), 20),
                ('reference', gettext('Reference'), 20),
                ('bank_name', gettext('Bank name'), 20),
                # ('bank_street', gettext('Bank street'), 20),
                # ('bank_zip', gettext('Bank zip'), 15),
                # ('bank_city', gettext('Bank city'), 20),
                # ('get_bank_country_display', gettext('Bank country'), 20, None, lambda value: value()),
                ('bank_iban', gettext('IBAN'), 30),
                ('bank_swift_bic', gettext('SWIFT/BIC'), 15),
            ],
            gettext('Issuer'): [
                ('supplier_name', gettext('Supplier name'), 20),
                ('supplier_street', gettext('Supplier street'), 20),
                ('supplier_zip', gettext('Supplier zip'), 15),
                ('supplier_city', gettext('Supplier city'), 15),
                ('get_supplier_country_display', gettext('Supplier country'), 20, None, lambda value: value()),
                ('supplier_registration_id', gettext('Supplier reg. ID'), 20),
                ('supplier_tax_id', gettext('Supplier tax ID'), 20),
                ('supplier_vat_id', gettext('Supplier VAT ID'), 20),
                ('supplier_additional_info', gettext('Supplier additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('issuer_name', gettext('Issuer name'), 20),
                ('issuer_email', gettext('Issuer email'), 30),
                ('issuer_phone', gettext('Issuer phone'), 30),
            ],
            gettext('Customer'): [
                ('customer_name', gettext('Customer name'), 20),
                ('customer_street', gettext('Customer street'), 20),
                ('customer_zip', gettext('Customer zip'), 15),
                ('customer_city', gettext('Customer city'), 20),
                ('get_customer_country_display', gettext('Customer country'), 20, None, lambda value: value()),
                ('customer_registration_id', gettext('Customer reg. ID'), 20),
                ('customer_tax_id', gettext('Customer tax ID'), 20),
                ('customer_vat_id', gettext('Customer VAT ID'), 20),
                ('customer_additional_info', gettext('Customer additional info'), 25, None, lambda ord_dict: ', '.join(': '.join([str(label), str(value)]) for label, value in ord_dict.items()) if ord_dict and not isinstance(ord_dict, str) else ''),
                ('customer_email', gettext('Customer email'), 30),
                ('customer_phone', gettext('Customer phone'), 30),
            ],
            # gettext('Shipping'): [
            #     ('shipping_name', gettext('Shipping name'), 20),
            #     ('shipping_street', gettext('Shipping street'), 20),
            #     ('shipping_zip', gettext('Shipping zip'), 15),
            #     ('shipping_city', gettext('Shipping city'), 20),
            #     ('get_shipping_country_display', gettext('Shipping country'), 20, None, lambda value: value()),
            #     ('get_delivery_method_display', gettext('Delivery method'), 20, None, lambda value: value()),
            # ],
        })

    # def get_whole_queryset(self, params):
    #     return super().get_whole_queryset(params) \
    #         .order_by('-created').distinct()
    #         # .prefetch_related(Prefetch('item_set', queryset=Item.objects.all())) \

    def get_worksheet_title(self, index=0):
        return gettext('Invoices')

    def get_queryset(self):
        return self.queryset


class InvoicePdfDetailExporter(ExporterMixin):
    queryset = Invoice.objects.all()
    export_format = Export.FORMAT_PDF
    export_context = Export.CONTEXT_DETAIL
    filename = _('invoices.zip')

    def get_queryset(self):
        return self.queryset

    def export(self):
        self.write_data(self.output)

    def write_data(self, output):
        export_files = get_invoices_in_pdf(self.get_queryset())

        if len(export_files) == 1:
            # directly export 1 PDF file
            file_data = export_files[0]
            self.filename = file_data['name']
            output.write(file_data['content'])
        else:
            # compress all invoices into single archive file
            output.write(compress(export_files).read())


class InvoiceISDOCXmlListExporter(ExporterMixin):
    queryset = Invoice.objects.all()
    filename = 'invoices_isdoc.zip'
    export_format = "ISDOC"
    export_context = Export.CONTEXT_LIST
    ISDOC_DOCUMENT_TYPE_MAPPING = {
        'INVOICE': '1',
        'CREDIT_NOTE': '2',
        'PROFORMA': '4',
        'ADVANCE': '5',
    }
    PAYMENT_MEANS_MAP = {
        'BANK_TRANSFER': '42',
        'CASH': '10',
        'CASH_ON_DELIVERY': '30',
        'PAYMENT_CARD': '48',
    }

    def get_queryset(self):
        return self.queryset

    def export(self):
        self.write_data(self.output)

    @staticmethod
    def get_invoice_orders(invoice):
        return []

    @staticmethod
    def get_invoice_domestic_currency(invoice):
        code = getattr(invoice.supplier_country, 'code', invoice.supplier_country)
        return 'EUR' if code == 'SK' else 'CZK'

    @staticmethod
    def get_invoice_fx_rate(invoice):
        return 1

    def write_data(self, output):
        export_files = []

        for invoice in self.get_queryset():

            root = etree.Element("Invoice", nsmap={None: "http://isdoc.cz/namespace/2013"}, version="6.0.1")

            # Header
            etree.SubElement(root, "DocumentType").text = self.ISDOC_DOCUMENT_TYPE_MAPPING.get(invoice.type, '1')
            etree.SubElement(root, "ID").text = invoice.number
            etree.SubElement(root, "UUID").text = str(uuid.uuid4())
            etree.SubElement(root, "IssueDate").text = invoice.date_issue.isoformat()
            etree.SubElement(root, "TaxPointDate").text = invoice.date_tax_point.isoformat()
            etree.SubElement(root, "VATApplicable").text = "true" if invoice.type != Invoice.TYPE.PROFORMA else "false"
            etree.SubElement(root, "ElectronicPossibilityAgreementReference").text = ""
            etree.SubElement(root, "Note").text = invoice.note

            # Currency handling
            domestic_currency = self.get_invoice_domestic_currency(invoice)
            etree.SubElement(root, "LocalCurrencyCode").text = domestic_currency
            has_foreign_currency = invoice.currency != self.get_invoice_domestic_currency(invoice)

            if has_foreign_currency:
                etree.SubElement(root, "ForeignCurrencyCode").text = invoice.currency

            fx_rate = self.get_invoice_fx_rate(invoice)
            etree.SubElement(root, "CurrRate").text = str(fx_rate) if fx_rate and has_foreign_currency else "1"
            etree.SubElement(root, "RefCurrRate").text = "1"

            # Supplier
            supplier = etree.SubElement(root, "AccountingSupplierParty")
            party = etree.SubElement(supplier, "Party")

            party_identification = etree.SubElement(party, "PartyIdentification")
            etree.SubElement(party_identification, "ID").text = invoice.supplier_registration_id
            etree.SubElement(etree.SubElement(party, "PartyName"), "Name").text = invoice.supplier_name

            address = etree.SubElement(party, "PostalAddress")
            etree.SubElement(address, "StreetName").text = invoice.supplier_street
            etree.SubElement(address, "BuildingNumber").text = ""
            etree.SubElement(address, "CityName").text = invoice.supplier_city
            etree.SubElement(address, "PostalZone").text = invoice.supplier_zip

            country = etree.SubElement(address, "Country")
            etree.SubElement(country, "IdentificationCode").text = invoice.supplier_country.code
            etree.SubElement(country, "Name").text = invoice.get_supplier_country_display()

            tax = etree.SubElement(party, "PartyTaxScheme")
            etree.SubElement(tax, "CompanyID").text = invoice.supplier_vat_id
            etree.SubElement(tax, "TaxScheme").text = "VAT"

            contact = etree.SubElement(party, "Contact")
            etree.SubElement(contact, "Name").text = invoice.issuer_name
            etree.SubElement(contact, "Telephone").text = invoice.issuer_phone
            etree.SubElement(contact, "ElectronicMail").text = invoice.issuer_email

            # Customer
            customer = etree.SubElement(root, "AccountingCustomerParty")
            party = etree.SubElement(customer, "Party")

            party_identification = etree.SubElement(party, "PartyIdentification")
            etree.SubElement(party_identification, "ID").text = invoice.customer_registration_id
            etree.SubElement(etree.SubElement(party, "PartyName"), "Name").text = invoice.customer_name

            address = etree.SubElement(party, "PostalAddress")
            etree.SubElement(address, "StreetName").text = invoice.customer_street
            etree.SubElement(address, "BuildingNumber").text = ""
            etree.SubElement(address, "CityName").text = invoice.customer_city
            etree.SubElement(address, "PostalZone").text = invoice.customer_zip

            country = etree.SubElement(address, "Country")
            etree.SubElement(country, "IdentificationCode").text = invoice.customer_country.code
            etree.SubElement(country, "Name").text = invoice.get_customer_country_display()

            tax = etree.SubElement(party, "PartyTaxScheme")
            etree.SubElement(tax, "CompanyID").text = invoice.customer_vat_id
            etree.SubElement(tax, "TaxScheme").text = "VAT"

            contact = etree.SubElement(party, "Contact")
            etree.SubElement(contact, "Telephone").text = invoice.customer_phone
            etree.SubElement(contact, "ElectronicMail").text = invoice.customer_email

            # Order references
            invoice_orders = self.get_invoice_orders(invoice)

            if invoice_orders:
                order_references = etree.SubElement(root, "OrderReferences")

                for order in self.get_invoice_orders(invoice):
                    order_reference = etree.SubElement(order_references, "OrderReference")
                    etree.SubElement(order_reference, "SalesOrderID").text = str(order.id)

            def format_money(value):
                """Return a string with 2-decimal formatting using Decimal for stable rounding."""
                if value is None:
                    value = Decimal('0')
                    # ensure Decimal for stable rounding/formatting
                if not isinstance(value, Decimal):
                    try:
                        value= Decimal(str(value))
                    except Exception:
                        return str(value)
                return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

            # Compute amounts
            def to_domestic_currency(amount):
                """Return string of amount in domestic currency with 2 decimals."""
                if amount in (None, ''):
                    return format_money(0)
                if has_foreign_currency and fx_rate:
                    return format_money(Decimal(str(amount)) * fx_rate)
                return format_money(amount)

            def add_amount_element(parent_element, tag, amount, foreign_currency_first=True):
                """
                Write <tag> (domestic) and, if foreign is used, <tag>Curr (foreign).
                - If foreign_currency_first=True, write Curr first (to match cases where your XML shows Curr first).
                """
                if has_foreign_currency and foreign_currency_first:
                    etree.SubElement(parent_element, f"{tag}Curr").text = format_money(amount)
                etree.SubElement(parent_element, tag).text = to_domestic_currency(amount)

                if has_foreign_currency and not foreign_currency_first:
                     etree.SubElement(parent_element, f"{tag}Curr").text = format_money(amount)

            def classify_tax_for_item(invoice_item):
                """
                Return a tuple:
                    (percent_decimal, vat_applicable_bool, local_reverse_charge_flag_bool)

                Rules:
                - Reverse charge: VATApplicable = false, Percent = actual tax rate (or 0), LocalReverseChargeFlag = true
                - Exempt supply: tax_rate is None → Percent = 0, VATApplicable = false, LocalReverseChargeFlag = false
                - Zero-rated supply: tax_rate == 0 → Percent = 0, VATApplicable = true, LocalReverseChargeFlag = false
                - Standard VAT: tax_rate > 0 → Percent = tax_rate, VATApplicable = true, LocalReverseChargeFlag = false
                """
                tax_rate_decimal = Decimal(str(invoice_item.tax_rate)) if invoice_item.tax_rate is not None else Decimal("0")
                is_item_reverse_charge = invoice_item.tax_rate is None and invoice.is_reverse_charge()

                # Domestic reverse charge – supplier does not charge VAT
                if is_item_reverse_charge:
                    if issubclass(invoice.taxation_policy, EUTaxationPolicy):
                        tax_rate_decimal = invoice.taxation_policy.get_rate_for_country(invoice.supplier_country.code, invoice.date_tax_point)
                    return tax_rate_decimal, False, True

                # Exempt supply (no VAT)
                if invoice_item.tax_rate is None:
                    return Decimal("0"), False, False

                # Zero-rated supply
                if Decimal(str(invoice_item.tax_rate)) == Decimal("0"):
                    return Decimal("0"), True, False

                # Standard taxable rate
                return tax_rate_decimal, True, False

            # Invoice lines
            lines = etree.SubElement(root, "InvoiceLines")
            for idx, item in enumerate(invoice.item_set.all(), start=1):
                line = etree.SubElement(lines, "InvoiceLine")
                etree.SubElement(line, "ID").text = str(idx)
                etree.SubElement(line, "InvoicedQuantity", unitCode=item.get_unit_display()).text = str(item.quantity)

                # Curr first in your examples for line extension amounts
                add_amount_element(line, "LineExtensionAmount", item.subtotal)

                if item.discount:
                    etree.SubElement(line, "LineExtensionAmountBeforeDiscount").text =  to_domestic_currency(item.subtotal_without_discount)

                add_amount_element(line, "LineExtensionAmountTaxInclusive", item.total)

                if item.discount:
                    etree.SubElement(line, "LineExtensionAmountTaxInclusiveBeforeDiscount").text =  to_domestic_currency(item.total_without_discount)

                etree.SubElement(line, "LineExtensionTaxAmount").text = to_domestic_currency(item.vat)
                etree.SubElement(line, "UnitPrice").text = to_domestic_currency(item.unit_price)
                etree.SubElement(line, "UnitPriceTaxInclusive").text = to_domestic_currency(item.unit_price_with_vat)

                tax_rate_percent, vat_applicable, local_reverse_charge = classify_tax_for_item(item)

                tax_category = etree.SubElement(line, "ClassifiedTaxCategory")
                etree.SubElement(tax_category, "Percent").text = str(tax_rate_percent) # Percent must always be present

                # VATCalculationMethod:
                #   1 = calculated from net (standard method),
                #   2 = calculated from gross (rare, retail POS)
                etree.SubElement(tax_category, "VATCalculationMethod").text = "1" # "Method - From the top"
                etree.SubElement(tax_category, "VATApplicable").text = "true" if vat_applicable else "false" # VATApplicable depending on classification

                item_elem = etree.SubElement(line, "Item")
                etree.SubElement(item_elem, "Description").text = item.title

            # Tax Total (grouped by item tax_rate)
            tax_total = etree.SubElement(root, "TaxTotal")

            # Group items by (Percent, VATApplicable, LocalReverseChargeFlag)
            items_grouped_by_tax_key = defaultdict(lambda: {
                "taxable_amount_foreign": Decimal("0"),
                "tax_amount_foreign": Decimal("0"),
                "tax_inclusive_amount_foreign": Decimal("0"),
            })

            for item in invoice.item_set.all():
                tax_rate_percent, vat_applicable, local_reverse_charge = classify_tax_for_item(item)
                tax_key = (tax_rate_percent, vat_applicable, local_reverse_charge)

                items_grouped_by_tax_key[tax_key]["taxable_amount_foreign"] += Decimal(str(item.subtotal or 0))
                items_grouped_by_tax_key[tax_key]["tax_amount_foreign"] += Decimal(str(item.vat or 0))
                items_grouped_by_tax_key[tax_key]["tax_inclusive_amount_foreign"] += Decimal(str(item.total or 0))

            # totals for <TaxTotal>/<TaxAmount>
            total_tax_amount_domestic_sum = Decimal("0")
            total_tax_amount_foreign_sum = Decimal("0")

            # Keep stable ordering of subtotals: first by Percent, then VATApplicable, then LocalReverseChargeFlag
            for (tax_rate_percent, vat_applicable, local_reverse_charge) in sorted(
                    items_grouped_by_tax_key.keys(),
                    key=lambda k: (k[0], k[1], k[2])
            ):
                bucket = items_grouped_by_tax_key[(tax_rate_percent, vat_applicable, local_reverse_charge)]
                taxable_amount_foreign = bucket["taxable_amount_foreign"]
                tax_amount_foreign = bucket["tax_amount_foreign"]
                tax_inclusive_amount_foreign = bucket["tax_inclusive_amount_foreign"]

                tax_subtotal = etree.SubElement(tax_total, "TaxSubTotal")

                add_amount_element(tax_subtotal, "TaxableAmount", taxable_amount_foreign)
                add_amount_element(tax_subtotal, "TaxAmount", tax_amount_foreign)
                add_amount_element(tax_subtotal, "TaxInclusiveAmount", tax_inclusive_amount_foreign)

                # TODO: AlreadyClaimed -> 0 for now
                add_amount_element(tax_subtotal, "AlreadyClaimedTaxableAmount", 0)
                add_amount_element(tax_subtotal, "AlreadyClaimedTaxAmount", 0)
                add_amount_element(tax_subtotal, "AlreadyClaimedTaxInclusiveAmount", 0)

                # Difference* → repeat current period values
                add_amount_element(tax_subtotal, "DifferenceTaxableAmount", taxable_amount_foreign)
                add_amount_element(tax_subtotal, "DifferenceTaxAmount", tax_amount_foreign)
                add_amount_element(tax_subtotal, "DifferenceTaxInclusiveAmount", tax_inclusive_amount_foreign)

                tax_category = etree.SubElement(tax_subtotal, "TaxCategory")
                etree.SubElement(tax_category, "Percent").text = str(tax_rate_percent)
                etree.SubElement(tax_category, "VATApplicable").text = "true" if vat_applicable else "false"

                if local_reverse_charge:
                    etree.SubElement(tax_category, "LocalReverseChargeFlag").text = "true"

                total_tax_amount_domestic_sum += Decimal(to_domestic_currency(tax_amount_foreign))
                total_tax_amount_foreign_sum += tax_amount_foreign

            add_amount_element(tax_total, "TaxAmount", total_tax_amount_foreign_sum)

            # Totals
            total = etree.SubElement(root, "LegalMonetaryTotal")

            add_amount_element(total, "TaxExclusiveAmount", invoice.subtotal, foreign_currency_first=False)
            add_amount_element(total, "TaxInclusiveAmount", invoice.total, foreign_currency_first=False)
            add_amount_element(total, "AlreadyClaimedTaxExclusiveAmount", 0, foreign_currency_first=False)

            add_amount_element(total, "AlreadyClaimedTaxInclusiveAmount", invoice.already_paid, foreign_currency_first=False)
            add_amount_element(total, "DifferenceTaxExclusiveAmount", invoice.subtotal, foreign_currency_first=False)
            add_amount_element(total, "DifferenceTaxInclusiveAmount", invoice.to_pay, foreign_currency_first=False)

            add_amount_element(total, "PayableRoundingAmount", 0, foreign_currency_first=False)
            add_amount_element(total, "PaidDepositsAmount", invoice.already_paid, foreign_currency_first=False)
            add_amount_element(total, "PayableAmount", invoice.to_pay, foreign_currency_first=False)

            # Payment details
            payment_means = etree.SubElement(root, "PaymentMeans")
            payment = etree.SubElement(payment_means, "Payment")
            etree.SubElement(payment, "PaidAmount").text = str(invoice.total)
            etree.SubElement(payment, "PaymentMeansCode").text = self.PAYMENT_MEANS_MAP.get(invoice.payment_method, "42")

            details = etree.SubElement(payment, "Details")
            etree.SubElement(details, "PaymentDueDate").text = invoice.date_due.isoformat()
            etree.SubElement(details, "ID").text = ""
            etree.SubElement(details, "BankCode").text = ""
            etree.SubElement(details, "Name").text = invoice.bank_name
            etree.SubElement(details, "IBAN").text = invoice.bank_iban or ""
            etree.SubElement(details, "BIC").text = invoice.bank_swift_bic
            etree.SubElement(details, "VariableSymbol").text = str(invoice.variable_symbol or "")
            etree.SubElement(details, "ConstantSymbol").text = str(invoice.constant_symbol)
            etree.SubElement(details, "SpecificSymbol").text = str(invoice.specific_symbol or "")

            # Convert to binary and store
            xml_bytes = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8")
            export_files.append({"name": f"{invoice.number}.{self.export_format}", "content": xml_bytes})

        output.write(compress(export_files).read())