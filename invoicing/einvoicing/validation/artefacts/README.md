# Vendored validation artefacts

Unmodified copies. Update them deliberately, in their own commit, and re-run
the einvoicing test suite (golden files included).

| Directory | Source | Version | Licence |
|---|---|---|---|
| `ubl-2.1/xsd/` | OASIS UBL 2.1, <https://docs.oasis-open.org/ubl/os-UBL-2.1/UBL-2.1.zip> (`xsd/common`, Invoice and CreditNote maindocs) | UBL 2.1 OS (2013-11-04) | OASIS IPR policy, notice in each file |
| `peppol-bis-3.0.21/CEN-EN16931-UBL.sch` | <https://docs.peppol.eu/poacc/billing/3.0/files/CEN-EN16931-UBL.sch> | EN 16931 validation artefacts 1.3.16 (2026-04-10) | EUPL 1.2 |
| `peppol-bis-3.0.21/PEPPOL-EN16931-UBL.sch` | <https://docs.peppol.eu/poacc/billing/3.0/files/PEPPOL-EN16931-UBL.sch> | Peppol BIS Billing 3.0.21, May 2026 release (mandatory from 2026-08-17) | OpenPeppol, reproduced with permission from CEN |
| `schxslt-1.9.5/` | SchXslt, <https://codeberg.org/SchXslt/schxslt> (`core/src/main/resources/xslt/2.0`) | 1.9.5 | MIT |

SHA-256 at the time of vendoring:

```
268d4f7a2688676695e6c69cba6fba69a6802604fee12cb544a6b30ff09555a3  CEN-EN16931-UBL.sch
62e5b67892f12755352d78b06f63229a02cc2eccc748677c56efbc8dbcb336e3  PEPPOL-EN16931-UBL.sch
```

The Schematron files are compiled to XSLT with SchXslt at first use (see
`../schematron.py`) and run on Saxon-HE (`saxonche`), because they need XSLT 2.0.

There are no official Slovak rules to vendor: the Financial Administration
publishes its national requirements only as a human-readable table. See
`../sk.py`.
