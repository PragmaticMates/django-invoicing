"""
VAT category codes (UNCL5305 subset used by EN 16931) and how an item's
category is resolved.

The core ``Item`` model only knows ``tax_rate``, where ``None`` covers
"not a VAT payer", reverse charge and exemptions alike. That is ambiguous,
so a category is inferred only when it cannot be anything else; every other
case needs an explicit category.
"""
from decimal import Decimal


class VatCategoryError(ValueError):
    pass


class VatCategory:
    STANDARD = 'S'
    ZERO_RATED = 'Z'
    EXEMPT = 'E'
    REVERSE_CHARGE = 'AE'
    INTRA_COMMUNITY = 'K'
    EXPORT = 'G'
    NOT_SUBJECT = 'O'

    CHOICES = (
        (STANDARD, 'Standard rate'),
        (ZERO_RATED, 'Zero rated goods'),
        (EXEMPT, 'Exempt from VAT'),
        (REVERSE_CHARGE, 'VAT reverse charge'),
        (INTRA_COMMUNITY, 'Intra-community supply'),
        (EXPORT, 'Export outside the EU'),
        (NOT_SUBJECT, 'Not subject to VAT'),
    )

    ALL = frozenset(code for code, label in CHOICES)

    # Categories whose VAT breakdown carries a rate (BT-119). For the others
    # the rate is 0 (E, AE, K, G) or must be absent altogether (O).
    WITH_RATE = frozenset({STANDARD, ZERO_RATED, EXEMPT, REVERSE_CHARGE, INTRA_COMMUNITY, EXPORT})

    # Categories which require an exemption reason, as text (BT-120) or code (BT-121)
    REQUIRES_EXEMPTION_REASON = frozenset({EXEMPT, REVERSE_CHARGE, INTRA_COMMUNITY, EXPORT, NOT_SUBJECT})


# Default VATEX code (BT-121) per category, used when the invoice gives none.
# E has no default: the legal ground of an exemption has to be stated explicitly.
DEFAULT_EXEMPTION_REASON_CODES = {
    VatCategory.REVERSE_CHARGE: 'VATEX-EU-AE',
    VatCategory.INTRA_COMMUNITY: 'VATEX-EU-IC',
    VatCategory.EXPORT: 'VATEX-EU-G',
    VatCategory.NOT_SUBJECT: 'VATEX-EU-O',
}


def resolve_category(*, tax_rate, supplier_has_vat_id, explicit=None):
    """
    Returns the VAT category code of one item.

    ``explicit`` wins when given, but has to agree with ``tax_rate``.
    Without it: a positive rate is S, a zero rate is Z, and no rate from a
    supplier without a VAT ID is O. No rate from a VAT payer may mean reverse
    charge or an exemption, which cannot be told apart, so it raises.
    """
    rate = None if tax_rate is None else Decimal(tax_rate)

    if explicit:
        if explicit not in VatCategory.ALL:
            raise VatCategoryError(f'Unknown VAT category {explicit!r}')

        if explicit == VatCategory.STANDARD and not (rate and rate > 0):
            raise VatCategoryError('VAT category S needs a positive tax rate')

        if explicit != VatCategory.STANDARD and rate:
            raise VatCategoryError(f'VAT category {explicit} cannot have a tax rate of {rate}%')

        if explicit == VatCategory.ZERO_RATED and rate is None:
            raise VatCategoryError('VAT category Z needs a tax rate of 0%')

        return explicit

    if rate is not None:
        return VatCategory.STANDARD if rate > 0 else VatCategory.ZERO_RATED

    if not supplier_has_vat_id:
        return VatCategory.NOT_SUBJECT

    raise VatCategoryError(
        'Item has no tax rate but the supplier has a VAT ID: '
        'set the VAT category explicitly (reverse charge, exempt, ...)'
    )


def category_rate(category, tax_rate):
    """VAT rate (BT-119/BT-152) as it belongs into the document, or None if it must be absent."""
    if category not in VatCategory.WITH_RATE:
        return None

    if category == VatCategory.STANDARD:
        return Decimal(tax_rate)

    return Decimal(0)
