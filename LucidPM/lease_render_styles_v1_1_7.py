"""
lease_render_styles.py

ReportLab paragraph styles and page layout constants for lease document rendering.

Version: 1.1.6
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

PAGE_SETUP = {
    "pagesize": letter,
    "leftMargin": 0.75 * inch,
    "rightMargin": 0.75 * inch,
    "topMargin": 0.70 * inch,
    "bottomMargin": 0.95 * inch,
}

SIGNATURE_FOOTER_TEXT = "________              ________              ________<br/>Landlord                 Tenant                    Tenant"

LEASE_STYLES: dict[str, ParagraphStyle] = {}


def _style(name: str, **kwargs) -> ParagraphStyle:
    style = ParagraphStyle(name=name, **kwargs)
    LEASE_STYLES[name] = style
    return style


DOC_TITLE = _style(
    "DOC_TITLE",
    fontName="Times-Bold",
    fontSize=12,
    leading=15,
    alignment=TA_CENTER,
    spaceBefore=4,
    spaceAfter=10,
)

JURISDICTION = _style(
    "JURISDICTION",
    fontName="Times-Roman",
    fontSize=10,
    leading=12,
    alignment=TA_RIGHT,
    spaceAfter=10,
)

PARTY_NAME = _style(
    "PARTY_NAME",
    fontName="Times-Bold",
    fontSize=11,
    leading=13,
    alignment=TA_LEFT,
    spaceBefore=4,
    spaceAfter=1,
)

PARTY_LABEL = _style(
    "PARTY_LABEL",
    fontName="Times-Italic",
    fontSize=9,
    leading=11,
    alignment=TA_LEFT,
    spaceAfter=8,
)

WITNESSETH = _style(
    "WITNESSETH",
    fontName="Times-Bold",
    fontSize=10,
    leading=12,
    alignment=TA_CENTER,
    spaceBefore=6,
    spaceAfter=8,
)

ARTICLE_HEADER = _style(
    "ARTICLE_HEADER",
    fontName="Times-Bold",
    fontSize=10,
    leading=12,
    alignment=TA_LEFT,
    keepWithNext=True,
    spaceBefore=6,
    spaceAfter=8,
)

CLAUSE_BODY = _style(
    "CLAUSE_BODY",
    fontName="Times-Roman",
    fontSize=10,
    leading=13,
    alignment=TA_JUSTIFY,
    leftIndent=0.25 * inch,
    firstLineIndent=0,
    spaceBefore=0,
    spaceAfter=6,
)

INDENTED_BODY = _style(
    "INDENTED_BODY",
    parent=CLAUSE_BODY,
    leftIndent=0.50 * inch,
    firstLineIndent=0,
)

PAYMENT_SCHEDULE = _style(
    "PAYMENT_SCHEDULE",
    fontName="Times-Roman",  # switched from Courier for visual consistency with lease body text
    fontSize=9,
    leading=11,
    alignment=TA_LEFT,
    spaceBefore=6,
    spaceAfter=8,
)

SIGNATURE_FOOTER = _style(
    "SIGNATURE_FOOTER",
    fontName="Times-Roman",
    fontSize=8,
    leading=9,
    alignment=TA_CENTER,
)

LEASE_MONOSPACE = PAYMENT_SCHEDULE


ARTICLE_CENTERED = _style(
    "ARTICLE_CENTERED",
    fontName="Times-Bold",
    fontSize=11,
    leading=13,
    alignment=TA_CENTER,
    keepWithNext=True,
    spaceBefore=12,
    spaceAfter=6,
)

SIGNATURE_BLOCK = _style(
    "SIGNATURE_BLOCK",
    fontName="Times-Roman",
    fontSize=10,
    leading=12,
    alignment=TA_LEFT,
    spaceBefore=12,
    spaceAfter=10,
)
