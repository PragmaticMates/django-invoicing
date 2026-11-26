"""
Peppol BIS Billing 3.0 Schematron validation: the CEN EN 16931 rules (BR-*)
and the Peppol rules (PEPPOL-*), as published with BIS 3.0.21 (validation
artefacts 1.3.16).

The rules use XSLT 2.0, which lxml (libxslt) cannot run, so they run on
Saxon through ``saxonche``. They are compiled from the vendored ``.sch``
files with the vendored SchXslt on first use and kept per process.
"""
import threading
from pathlib import Path

from lxml import etree

from invoicing.einvoicing.validation.report import FATAL, WARNING, ValidationReport


ARTEFACTS = Path(__file__).parent / 'artefacts'
VERSION = 'peppol-bis-3.0.21'
SCHEMATRONS = (
    ARTEFACTS / VERSION / 'CEN-EN16931-UBL.sch',
    ARTEFACTS / VERSION / 'PEPPOL-EN16931-UBL.sch',
)
COMPILER = ARTEFACTS / 'schxslt-1.9.5' / '2.0' / 'pipeline-for-svrl.xsl'
SVRL = {'svrl': 'http://purl.oclc.org/dsdl/svrl'}

_lock = threading.Lock()
_processor = None
_stylesheets = None


def _get_stylesheets():
    global _processor, _stylesheets

    if _stylesheets is None:
        from saxonche import PySaxonProcessor

        _processor = PySaxonProcessor(license=False)
        xslt = _processor.new_xslt30_processor()
        compiler = xslt.compile_stylesheet(stylesheet_file=str(COMPILER))
        _stylesheets = [
            xslt.compile_stylesheet(stylesheet_text=compiler.transform_to_string(source_file=str(schematron)))
            for schematron in SCHEMATRONS
        ]

    return _stylesheets


def validate(xml):
    report = ValidationReport()

    with _lock:
        stylesheets = _get_stylesheets()
        document = _processor.parse_xml(xml_text=xml.decode('utf-8'))
        outputs = [stylesheet.transform_to_string(xdm_node=document) for stylesheet in stylesheets]

    for output in outputs:
        svrl = etree.fromstring(output.encode('utf-8'))
        for failure in svrl.xpath('//svrl:failed-assert | //svrl:successful-report', namespaces=SVRL):
            report.add(
                failure.get('id') or '',
                ' '.join((failure.findtext('svrl:text', default='', namespaces=SVRL)).split()),
                'schematron',
                severity=FATAL if failure.get('flag', 'fatal') in ('fatal', 'error') else WARNING,
                location=failure.get('location', ''),
            )

    return report
