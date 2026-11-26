"""UBL 2.1 XML Schema validation (OASIS UBL 2.1 schemas, vendored)."""
import threading
from pathlib import Path

from lxml import etree

from invoicing.einvoicing.validation.report import ValidationReport


MAINDOC = Path(__file__).parent / 'artefacts' / 'ubl-2.1' / 'xsd' / 'maindoc'
SCHEMAS = {
    'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2': MAINDOC / 'UBL-Invoice-2.1.xsd',
    'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2': MAINDOC / 'UBL-CreditNote-2.1.xsd',
}

_cache = {}
_lock = threading.Lock()


def _schema(namespace):
    with _lock:
        if namespace not in _cache:
            _cache[namespace] = etree.XMLSchema(etree.parse(str(SCHEMAS[namespace])))
        return _cache[namespace]


def validate(xml):
    report = ValidationReport()

    try:
        document = etree.fromstring(xml)
    except etree.XMLSyntaxError as error:
        report.add('XML', f'Not well-formed XML: {error}', 'xsd')
        return report

    namespace = etree.QName(document).namespace
    if namespace not in SCHEMAS:
        report.add('UBL', f'Not a UBL Invoice or CreditNote: {document.tag}', 'xsd')
        return report

    schema = _schema(namespace)
    if not schema.validate(document):
        for error in schema.error_log:
            report.add('XSD', error.message, 'xsd', location=f'line {error.line}')

    return report
