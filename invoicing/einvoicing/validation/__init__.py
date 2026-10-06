"""
Validation pipeline for structured invoices.

* ``preflight(invoice)`` checks the invoice before any XML is built
* ``validate(xml)`` checks the built XML: UBL 2.1 XSD, then the Peppol BIS
  Billing 3.0 Schematron rules, then the (unofficial) Slovak national rules

Both return a ``ValidationReport``; anything fatal means: do not send.
"""
from invoicing.einvoicing import conf
from invoicing.einvoicing.validation import schematron, sk, xsd
from invoicing.einvoicing.validation.preflight import preflight
from invoicing.einvoicing.validation.report import FATAL, WARNING, Finding, ValidationReport


__all__ = ['FATAL', 'WARNING', 'Finding', 'ValidationReport', 'preflight', 'validate']


def validate(xml):
    report = xsd.validate(xml)

    if not report.is_valid:
        # the rules below assume a structurally valid document
        return report

    if conf.get('SCHEMATRON'):
        report.extend(schematron.validate(xml))

    report.extend(sk.validate(xml))
    return report
