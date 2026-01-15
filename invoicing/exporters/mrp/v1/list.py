import re
from decimal import Decimal

from django.core.validators import EMPTY_VALUES
from django.template import loader

from invoicing.managers import get_invoice_details_manager
from invoicing.models import Invoice
from lxml import etree
from outputs.mixins import ExporterMixin
from outputs.models import Export


class InvoiceXmlMrpListExporter(ExporterMixin):
    queryset = Invoice.objects.all()
    export_format = Export.FORMAT_XML_MRP
    filename = "MRP_outgoing_invoice_export.zip"

    def get_queryset(self):
        return self.queryset.order_by("-pk").distinct()

    def export(self):
        self.write_data(self.output)

    def get_message_body(self, count):
        template = loader.get_template('outputs/export_message_body.html')
        return template.render({'count': count, 'filtered_values': None})


class InvoiceFakvyXmlMrpExporter(InvoiceXmlMrpListExporter):
    filename = "FAKVY.xml"

    @staticmethod
    def get_customer_ico(invoice) -> str:
        if invoice.customer_registration_id not in EMPTY_VALUES:
            return invoice.customer_registration_id

        if invoice.customer_tax_id not in EMPTY_VALUES:
            return invoice.customer_tax_id

        if invoice.customer_vat_id not in EMPTY_VALUES:
            # Remove all letters from the VAT ID
            return re.sub(r"\D", "", invoice.customer_vat_id)

        return ""

    def write_data(self, output):
        # http://faq.mrp.cz/faqcz/obrazky/jkimage/MRPKS_FAKTURY_IMPORT_5_53_001.TXT
        # Table: FAKVY - Faktura

        # < idfak > 24190 < / idfak >
        # < cislo > 201811543 < / cislo >
        # < ico > 662232848 < / ico >
        # < icoprij > < / icoprij >
        # < typdph > 13 < / typdph >
        # < zakl0 > -390 < / zakl0 >
        # < zakl1 > 0 < / zakl1 >
        # < zakl2 > 0 < / zakl2 >
        # < mimodph > 0 < / mimodph >
        # < dph1 > 0 < / dph1 >
        # < dph2 > 0 < / dph2 >
        # < cislododli > 20173146 < / cislododli >
        # < datvystave > 2018 - 10 - 22 < / datvystave >
        # < datzdanpln > 2018 - 10 - 22 < / datzdanpln >
        # < datsplatno > 2018 - 11 - 05 < / datsplatno >
        # < datobjed > 2017 - 06 - 14 < / datobjed >
        # < varsymb > 201811543 < / varsymb >
        # < konstsymb > 030
        # 8 < / konstsymb >
        # < specisymb > < / specisymb >
        # < stredisko > zml. d < / stredisko >
        # < formauhrad > bank
        # trans < / formauhrad >
        # < sposobdopr > < / sposobdopr >
        # < cisloobjed > 20176738 < / cisloobjed >
        # < origcislo > < / origcislo >
        # < mena > EUR < / mena >
        # < fixacecst > F < / fixacecst >
        # < kurz_zahr > < / kurz_zahr >
        # < kurz_sk > < / kurz_sk >
        # < platkar > 0 < / platkar >
        # < cisplatkar > < / cisplatkar >
        # < typ_dokl > D < / typ_dokl >
        # < cis_predf > < / cis_predf >
        # < cislo_zak > 20176738 < / cislo_zak >
        # < celk_zahr > < / celk_zahr >
        # < hmotnost > 0 < / hmotnost >
        # < poznamka > < / poznamka >
        # < cenysdph > F < / cenysdph >
        # < origcis2 > 20173146 < / origcis2 >
        # < origcisdok > < / origcisdok >
        # < KH_LEASING > F < / KH_LEASING >
        # < REZIM_DPH > 0 < / REZIM_DPH >

        # build xml structure
        document = etree.Element("document")
        datasets = etree.SubElement(document, "datasets")
        dataset0 = etree.SubElement(datasets, "dataset0")
        rows = etree.SubElement(dataset0, "rows")

        for invoice in self.get_queryset():
            row = etree.SubElement(rows, "row")
            fields = etree.SubElement(row, "fields")

            # # < druh > F < / druh >
            druh = etree.SubElement(fields, "druh")
            druh.text = "X" if invoice.type == Invoice.TYPE.ADVANCE else "F"

            # < idfak > 24190 < / idfak >
            idfak = etree.SubElement(fields, "idfak")
            idfak.text = str(invoice.id)
            # idfak.text = '1'  # rather ?

            # < udpredkont > 11 < / udpredkont >
            advance_notice = get_invoice_details_manager().advance_notice(invoice)

            if advance_notice not in EMPTY_VALUES:
                udpredkont = etree.SubElement(fields, "udpredkont")
                udpredkont.text = advance_notice

            # < cislo_zak > 0 < / cislo_zak >
            customer_number = get_invoice_details_manager().customer_number(invoice)

            if customer_number not in EMPTY_VALUES:
                cislo_zak = etree.SubElement(fields, "cislo_zak")
                cislo_zak.text = customer_number

            # < cislo > 201811543 < / cislo >
            cislo = etree.SubElement(fields, "cislo")
            cislo.text = str(invoice.number)

            # < ico > 662232848 < / ico >
            ico = etree.SubElement(fields, "ico")
            ico.text = InvoiceFakvyXmlMrpExporter.get_customer_ico(invoice)

            # < icoprij > < / icoprij >
            icoprij = etree.SubElement(fields, "icoprij")
            icoprij.text = ""

            # < typdph > 72 < / typdph >
            vat_type = get_invoice_details_manager().vat_type(invoice)

            if vat_type not in EMPTY_VALUES:
                typdph = etree.SubElement(fields, "typdph")
                typdph.text = str(vat_type)

            # < KODPLNENI > X < / KODPLNENI >
            fulfillment_code = get_invoice_details_manager().fulfillment_code(invoice)

            if fulfillment_code not in EMPTY_VALUES:
                kodplneni = etree.SubElement(fields, "kodplneni")
                kodplneni.text = fulfillment_code

            # < zakl0 > -390 < / zakl0 >
            zakl0 = etree.SubElement(fields, "zakl0")
            zakl0.text = str(invoice.subtotal) if invoice.vat in [0, None] else "0"

            # < zakl1 > 0 < / zakl1 >
            zakl1 = etree.SubElement(fields, "zakl1")
            zakl1.text = "0"

            # < zakl2 > 0 < / zakl2 >
            zakl2 = etree.SubElement(fields, "zakl2")
            zakl2.text = str(invoice.subtotal) if invoice.vat not in [0, None] else "0"

            # < mimodph > 0 < / mimodph >
            mimodph = etree.SubElement(fields, "mimodph")
            mimodph.text = "0"

            # < dph1 > 0 < / dph1 >
            dph1 = etree.SubElement(fields, "dph1")
            dph1.text = "0"

            # < dph2 > 0 < / dph2 >
            dph2 = etree.SubElement(fields, "dph2")
            dph2.text = str(invoice.vat) if invoice.vat not in [0, None] else "0"

            # < cislododli > 20173146 < / cislododli >
            # cislododli = etree.SubElement(fields, "cislododli")
            # cislododli.text = str(self.invoice.customer_registration_id) # todo cislo dodacieho list ?
            # < datvystave >2018-10-22< / datvystave >
            datvystave = etree.SubElement(fields, "datvystave")
            datvystave.text = str(invoice.date_issue)

            # < datzdanpln > 2018 - 10 - 22 < / datzdanpln >
            datzdanpln = etree.SubElement(fields, "datzdanpln")
            datzdanpln.text = str(invoice.date_tax_point)

            # < datsplatno > 2018 - 11 - 05 < / datsplatno >
            datsplatno = etree.SubElement(fields, "datsplatno")
            datsplatno.text = str(invoice.date_due)

            # < datobjed > 2017 - 06 - 14 < / datobjed >
            if hasattr(invoice, "orders") and invoice.orders.exists():
                first_order = invoice.orders.first()
                datobjed = etree.SubElement(fields, "datobjed")
                datobjed.text = str(first_order.created.date())

            # < varsymb > 2012002 < / varsymb >
            varsymb = etree.SubElement(fields, "varsymb")
            varsymb.text = str(invoice.variable_symbol) if invoice.variable_symbol else ""

            # < konstsymb > 000 8 < / konstsymb >
            konstsymb = etree.SubElement(fields, "konstsymb")
            konstsymb.text = str(invoice.constant_symbol) if invoice.constant_symbol else ""

            # < specisymb > < / specisymb >
            specisymb = etree.SubElement(fields, "specisymb")
            specisymb.text = str(invoice.specific_symbol) if invoice.specific_symbol else ""

            # < stredisko > zml. d < / stredisko >
            center = get_invoice_details_manager().center(invoice)

            if center not in EMPTY_VALUES:
                stredisko = etree.SubElement(fields, "stredisko")
                stredisko.text = center

            # < formauhrad > bank
            # trans < / formauhrad >
            formauhrad = etree.SubElement(fields, "formauhrad")
            if invoice.payment_method == Invoice.PAYMENT_METHOD.BANK_TRANSFER:
                formauhrad.text = "bank trans"
            elif invoice.payment_method == Invoice.PAYMENT_METHOD.CASH:
                formauhrad.text = "hotovosť"
            elif invoice.payment_method == Invoice.PAYMENT_METHOD.CASH_ON_DELIVERY:
                formauhrad.text = "dobierka"
            elif invoice.payment_method == Invoice.PAYMENT_METHOD.PAYMENT_CARD:
                formauhrad.text = "kartou"

            # < sposobdopr > < / sposobdopr >
            sposobdopr = etree.SubElement(fields, "sposobdopr")
            sposobdopr.text = ""  # sluzba

            # < cisloobjed > 20176738 < / cisloobjed >
            if hasattr(invoice, "orders") and invoice.orders.exists():
                first_order = invoice.orders.first()
                cisloobjed = etree.SubElement(fields, "cisloobjed")

                if hasattr(first_order, "number"):
                    cisloobjed.text = str(first_order.number)
                elif hasattr(first_order, "order_number"):
                    cisloobjed.text = str(first_order.order_number)
                else:
                    cisloobjed.text = str(first_order)

            # < origcislo > < / origcislo >
            origcislo = etree.SubElement(fields, "origcislo")
            origcislo.text = ""

            # < mena > EUR < / mena >
            mena = etree.SubElement(fields, "mena")
            mena.text = str(invoice.currency)

            # < fixacecst > F < / fixacecst >
            # fixacecst = etree.SubElement(fields, "fixacecst")
            # fixacecst.text = 'F'

            # < kurz_zahr > < / kurz_zahr >
            kurz_zahr = etree.SubElement(fields, "kurz_zahr")
            kurz_zahr.text = ""

            # < kurz_sk > < / kurz_sk >
            kurz_sk = etree.SubElement(fields, "kurz_sk")
            kurz_sk.text = ""

            # < platkar > 0 < / platkar >
            platkar = etree.SubElement(fields, "platkar")
            platkar.text = "0"

            # < cisplatkar > < / cisplatkar >
            cisplatkar = etree.SubElement(fields, "cisplatkar")
            cisplatkar.text = ""

            # < typ_dokl > D < / typ_dokl >
            typ_dokl = etree.SubElement(fields, "typ_dokl")
            typ_dokl.text = "D" if invoice.type == Invoice.TYPE.CREDIT_NOTE else ""

            # < cis_predf > < / cis_predf >
            cis_predf = etree.SubElement(fields, "cis_predf")
            cis_predf.text = ""

            # < cislo_zak > 20176738 < / cislo_zak >
            # cislo_zak = etree.SubElement(fields, "cislo_zak")
            # if invoice.orders.exists():
            #     first_order = invoice.orders.first()
            #     cislo_zak.text = str(first_order.number)

            # < celk_zahr > < / celk_zahr >
            celk_zahr = etree.SubElement(fields, "celk_zahr")
            celk_zahr.text = ""

            # < hmotnost > 0 < / hmotnost >
            hmotnost = etree.SubElement(fields, "hmotnost")
            hmotnost.text = "0"

            # < poznamka > < / poznamka >
            poznamka = etree.SubElement(fields, "poznamka")
            # poznamka.text = str(invoice.note)
            poznamka.text = ""

            # < cenysdph > F < / cenysdph >
            cenysdph = etree.SubElement(fields, "cenysdph")
            cenysdph.text = "F"

            # < origcis2 > 20173146 < / origcis2 >
            origcis2 = etree.SubElement(fields, "origcis2")
            origcis2.text = str(invoice.related_document)

            # < origcisdok > < / origcisdok >
            origcisdok = etree.SubElement(fields, "origcisdok")
            origcisdok.text = ""

            # < KH_LEASING > F < / KH_LEASING >
            KH_LEASING = etree.SubElement(fields, "KH_LEASING")
            KH_LEASING.text = "F"

            # < REZIM_DPH > 0 < / REZIM_DPH >
            # REZIM_DPH = etree.SubElement(fields, "REZIM_DPH")
            # REZIM_DPH.text = '0' if invoice.vat not in [0, None] else '1'

            # < STAT_DPH > < / STAT_DPH >
            # stat_dph = etree.SubElement(fields, "stat_dph")
            # stat_dph.text = str(invoice.customer_country) if REZIM_DPH.text != '0' else str(invoice.customer_country)

            # < VATNUMBER > < / VATNUMBER >
            # VATNUMBER = etree.SubElement(fields, "VATNUMBER")
            # VATNUMBER.text = str(invoice.customer_vat_id) if REZIM_DPH.text != '0' else ''

        output_string = etree.tostring(document, pretty_print=True, xml_declaration=True, encoding="Windows-1250")

        # print(output_string)
        output.write(output_string)


class InvoiceFakvypolXmlMrpExporter(InvoiceXmlMrpListExporter):
    filename = "FAKVYPOL.xml"

    def write_data(self, output):
        # < idr > 241930007 < / idr >
        # < idfak > 24193 < / idfak >
        # < text > Unloading
        # Place: ES - Paterna < / text >
        # < mj > < / mj >
        # < pocetmj > 1 < / pocetmj >
        # < cenamj > -980 < / cenamj >
        # < sadzbadph > 0 < / sadzbadph >
        # < dph > 0 < / dph >
        # < zlava > 0 < / zlava >
        # < slevamj > 0 < / slevamj >
        # < riadok > 7 < / riadok >
        # < hmotnost > 0 < / hmotnost >
        # < typ_pol > S < / typ_pol >
        # < typ_radku > 1 < / typ_radku >
        # < typ_sum > 1 < / typ_sum >
        # < stredisko > zml. d < / stredisko >
        # < cislo_zak > 20176595 < / cislo_zak >

        # build xml structure
        document = etree.Element("document")
        datasets = etree.SubElement(document, "datasets")
        dataset0 = etree.SubElement(datasets, "dataset0")
        rows = etree.SubElement(dataset0, "rows")

        row_counter = 1

        for invoice in self.get_queryset():
            item_row_counter = 1

            for item in invoice.item_set.all():
                title_splitline = item.title.splitlines()
                line_count = len(title_splitline)

                for subtitle_counter, subtitle in enumerate(title_splitline):
                    row = etree.SubElement(rows, "row")
                    fields = etree.SubElement(row, "fields")

                    # < idr > 241930007 < / idr >
                    idr = etree.SubElement(fields, "idr")
                    idr.text = str(row_counter)

                    # < idfak > 24193 < / idfak >
                    idfak = etree.SubElement(fields, "idfak")
                    idfak.text = str(invoice.id)

                    # < cislo_zak > 0 < / cislo_zak >
                    customer_number = get_invoice_details_manager().customer_number(invoice)
                    if customer_number not in EMPTY_VALUES:
                        cislo_zak = etree.SubElement(fields, "cislo_zak")
                        cislo_zak.text = customer_number

                    # < text > Unloading
                    # Place: ES - Paterna < / text >
                    text = etree.SubElement(fields, "text")
                    text.text = str(subtitle)

                    # < mj > < / mj >
                    mj = etree.SubElement(fields, "mj")

                    # < pocetmj > 1 < / pocetmj >
                    pocetmj = etree.SubElement(fields, "pocetmj")

                    # < cenamj > -980 < / cenamj >
                    cenamj = etree.SubElement(fields, "cenamj")

                    # < sadzbadph > 0 < / sadzbadph >
                    sadzbadph = etree.SubElement(fields, "sadzbadph")

                    # < dph > 0 < / dph >
                    dph = etree.SubElement(fields, "dph")

                    # < zlava > 0 < / zlava >
                    zlava = etree.SubElement(fields, "zlava")

                    # < slevamj > 0 < / slevamj >
                    slevamj = etree.SubElement(fields, "slevamj")

                    # < typ_pol > S < / typ_pol >
                    typ_pol = etree.SubElement(fields, "typ_pol")

                    if subtitle_counter < line_count - 1:
                        # not last item line
                        typ_pol.text = ""
                        mj.text = ""
                        pocetmj.text = "0"
                        cenamj.text = "0"
                        sadzbadph.text = "0"
                        dph.text = "0"
                        zlava.text = "0"
                        slevamj.text = "0"
                    else:
                        # last item line
                        typ_pol.text = "S" if get_invoice_details_manager().vat_type(invoice) in [13, 72] else ""
                        mj.text = str(item.get_unit_display())
                        pocetmj.text = str(item.quantity)
                        cenamj.text = str(item.unit_price)
                        sadzbadph.text = str(int(item.tax_rate)) if item.tax_rate is not None else "0"
                        dph.text = str(item.vat) if item.tax_rate is not None else "0"
                        zlava.text = str(item.discount)
                        slevamj.text = (
                            str(round(Decimal(item.unit_price) * Decimal(item.discount / 100), 2))
                            if item.discount != 0
                            else "0"
                        )

                    # < riadok > 7 < / riadok >
                    riadok = etree.SubElement(fields, "riadok")
                    riadok.text = str(item_row_counter)

                    # < hmotnost > 0 < / hmotnost >
                    hmotnost = etree.SubElement(fields, "hmotnost")
                    hmotnost.text = "0"

                    # < typ_radku > 1 < / typ_radku >
                    typ_radku = etree.SubElement(fields, "typ_radku")
                    typ_radku.text = "1"

                    # < typ_sum > 1 < / typ_sum >
                    typ_sum = etree.SubElement(fields, "typ_sum")
                    typ_sum.text = "1"

                    # < stredisko > zml. d < / stredisko >
                    center = get_invoice_details_manager().center(invoice)

                    if center not in EMPTY_VALUES:
                        stredisko = etree.SubElement(fields, "stredisko")
                        stredisko.text = center

                    # < cislo_zak > 20176595 < / cislo_zak >
                    # cislo_zak = etree.SubElement(fields, "cislo_zak")
                    # if invoice.orders.exists():
                    #     first_order = invoice.orders.first()
                    #     cislo_zak.text = str(first_order.number)

                    item_row_counter += 1
                    row_counter += 1

        output_string = etree.tostring(document, pretty_print=True, xml_declaration=True, encoding="Windows-1250")

        # print(output_string)
        output.write(output_string)


class InvoiceFvAdresXmlMrpExporter(InvoiceXmlMrpListExporter):
    filename = "FV_ADRES.xml"

    def write_data(self, output):
        # < idradr > 7541 < / idradr >
        # < firma > Dlouh� Eli�ka < / firma >
        # < ico > 99999995 < / ico >
        # < meno > < / meno >
        # < ulica > N�chodsk� 1 < / ulica >
        # < mesto > Praha
        # 9 < / mesto >
        # < stat >�esk� republika < / stat >
        # < ine > < / ine >
        # < psc > 19300 < / psc >
        # < cisob > < / cisob >
        # < cisorp > < / cisorp >
        # < dic > CZ99999995 < / dic >
        # < telefon > < / telefon >
        # < telefon2 > < / telefon2 >
        # < telefon3 > < / telefon3 >
        # < fax > < / fax >
        # < email > mail @ mail.cz < / email >
        # < fyzosob > T < / fyzosob >
        # < firma2 > < / firma2 >
        # < id > < / id >
        # < splatnost > 10 < / splatnost >
        # < eankod > < / eankod >
        # < eansys > < / eansys >
        # < formauhrad > < / formauhrad >
        # < sposobdopr > < / sposobdopr >
        # < varsymbfv > < / varsymbfv >
        # < varsymbfp > < / varsymbfp >
        # < specsymbfv > < / specsymbfv >
        # < specsymbfp > < / specsymbfp >
        # < na_platno > 0 < / na_platno >
        # < objemail > < / objemail >
        # < fakemail > < / fakemail >
        # < skontoproc > 0 < / skontoproc >
        # < skontodny > 0 < / skontodny >
        # < faksleva > 0 < / faksleva >
        # < cispovol > < / cispovol >
        # < typpovol > 0 < / typpovol >
        # < velobch > F < / velobch >
        # < kodstat > CZ < / kodstat >
        # < ic_dph > < / ic_dph >
        # < usrfld1 > < / usrfld1 >
        # < usrfld2 > < / usrfld2 >
        # < usrfld3 > < / usrfld3 >
        # < usrfld4 > < / usrfld4 >
        # < usrfld5 > < / usrfld5 >

        # build xml structure
        document = etree.Element("document")
        datasets = etree.SubElement(document, "datasets")
        dataset0 = etree.SubElement(datasets, "dataset0")
        rows = etree.SubElement(dataset0, "rows")

        for idx, invoice in enumerate(self.get_queryset()):
            row = etree.SubElement(rows, "row")
            fields = etree.SubElement(row, "fields")

            # < idradr > 7541 < / idradr >
            idradr = etree.SubElement(fields, "idradr")
            idradr.text = str(idx + 1)

            # < firma > Dlouh� Eli�ka < / firma >
            firma = etree.SubElement(fields, "firma")
            firma.text = str(invoice.customer_name)

            # < ico > 99999995 < / ico >
            ico = etree.SubElement(fields, "ico")
            ico.text = InvoiceFakvyXmlMrpExporter.get_customer_ico(invoice)

            # < meno > < / meno >
            meno = etree.SubElement(fields, "meno")
            meno.text = ""

            # < ulica > N�chodsk� 1 < / ulica >
            ulica = etree.SubElement(fields, "ulica")
            ulica.text = str(invoice.customer_street)

            # < mesto > Praha
            # 9 < / mesto >
            mesto = etree.SubElement(fields, "mesto")
            mesto.text = str(invoice.customer_city)

            # < stat >�esk� republika < / stat >
            stat = etree.SubElement(fields, "stat")
            stat.text = str(invoice.get_customer_country_display())

            # < ine > < / ine >
            ine = etree.SubElement(fields, "ine")
            ine.text = ""

            # < psc > 19300 < / psc >
            psc = etree.SubElement(fields, "psc")
            psc.text = str(invoice.customer_zip)

            # < cisob > < / cisob >
            cisob = etree.SubElement(fields, "cisob")
            cisob.text = ""

            # < cisorp > < / cisorp >
            cisorp = etree.SubElement(fields, "cisorp")
            cisorp.text = ""

            # < dic > CZ99999995 < / dic >
            dic = etree.SubElement(fields, "dic")
            dic.text = str(invoice.customer_tax_id) if invoice.customer_tax_id else ""

            # < telefon > < / telefon >
            telefon = etree.SubElement(fields, "telefon")
            telefon.text = str(invoice.customer_phone)

            # < telefon2 > < / telefon2 >
            telefon2 = etree.SubElement(fields, "telefon2")
            telefon2.text = ""

            # < telefon3 > < / telefon3 >
            telefon3 = etree.SubElement(fields, "telefon3")
            telefon3.text = ""

            # < fax > < / fax >
            fax = etree.SubElement(fields, "fax")
            fax.text = ""

            # < email > mail @ mail.cz < / email >
            email = etree.SubElement(fields, "email")
            email.text = str(invoice.customer_email)

            # < fyzosob > T < / fyzosob >
            fyzosob = etree.SubElement(fields, "fyzosob")
            fyzosob.text = "T"

            # < firma2 > < / firma2 >
            firma2 = etree.SubElement(fields, "firma2")
            firma2.text = ""

            # < id > < / id >
            id = etree.SubElement(fields, "id")
            id.text = ""

            # < splatnost > 10 < / splatnost >
            splatnost = etree.SubElement(fields, "splatnost")
            splatnost.text = str(invoice.payment_term)

            # < eankod > < / eankod >
            eankod = etree.SubElement(fields, "eankod")
            eankod.text = ""

            # < eansys > < / eansys >
            eansys = etree.SubElement(fields, "eansys")
            eansys.text = ""

            # < formauhrad > < / formauhrad >
            formauhrad = etree.SubElement(fields, "formauhrad")
            formauhrad.text = ""

            # < sposobdopr > < / sposobdopr >
            sposobdopr = etree.SubElement(fields, "sposobdopr")
            sposobdopr.text = ""

            # < varsymbfv > < / varsymbfv >
            varsymbfv = etree.SubElement(fields, "varsymbfv")
            varsymbfv.text = ""

            # < varsymbfp > < / varsymbfp >
            varsymbfp = etree.SubElement(fields, "varsymbfp")
            varsymbfp.text = ""

            # < specsymbfv > < / specsymbfv >
            specsymbfv = etree.SubElement(fields, "specsymbfv")
            specsymbfv.text = ""

            # < specsymbfp > < / specsymbfp >
            specsymbfp = etree.SubElement(fields, "specsymbfp")
            specsymbfp.text = ""

            # < na_platno > 0 < / na_platno >
            na_platno = etree.SubElement(fields, "na_platno")
            na_platno.text = "0" # todo check

            # < objemail > < / objemail >
            objemail = etree.SubElement(fields, "objemail")
            objemail.text = ""

            # < fakemail > < / fakemail >
            fakemail = etree.SubElement(fields, "fakemail")
            fakemail.text = ""

            # < skontoproc > 0 < / skontoproc >
            skontoproc = etree.SubElement(fields, "skontoproc")
            skontoproc.text = "0" # todo check

            # < skontodny > 0 < / skontodny >
            skontodny = etree.SubElement(fields, "skontodny")
            skontodny.text = "0" # todo check

            # < faksleva > 0 < / faksleva >
            faksleva = etree.SubElement(fields, "faksleva")
            faksleva.text = "0" # todo check

            # < cispovol > < / cispovol >
            cispovol = etree.SubElement(fields, "cispovol")
            cispovol.text = "" # todo check

            # < typpovol > 0 < / typpovol >
            typpovol = etree.SubElement(fields, "typpovol")
            typpovol.text = "0" # todo check

            # < velobch > F < / velobch >
            velobch = etree.SubElement(fields, "velobch")
            velobch.text = "F" # todo check

            # < kodstat > CZ < / kodstat >
            kodstat = etree.SubElement(fields, "kodstat")
            kodstat.text = str(invoice.customer_country)

            # < ic_dph > < / ic_dph >
            ic_dph = etree.SubElement(fields, "ic_dph")
            ic_dph.text = str(invoice.customer_vat_id)

            # < usrfld1 > < / usrfld1 >
            usrfld1 = etree.SubElement(fields, "usrfld1")
            usrfld1.text = ""

            # < usrfld2 > < / usrfld2 >
            usrfld2 = etree.SubElement(fields, "usrfld2")
            usrfld2.text = ""

            # < usrfld3 > < / usrfld3 >
            usrfld3 = etree.SubElement(fields, "usrfld3")
            usrfld3.text = ""

            # < usrfld4 > < / usrfld4 >
            usrfld4 = etree.SubElement(fields, "usrfld4")
            usrfld4.text = ""

            # < usrfld5 > < / usrfld5 >
            usrfld5 = etree.SubElement(fields, "usrfld5")
            usrfld5.text = ""

        output_string = etree.tostring(document, pretty_print=True, xml_declaration=True, encoding="Windows-1250")

        # print(output_string)
        output.write(output_string)
