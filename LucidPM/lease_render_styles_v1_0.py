"""
lease_render_styles.py

ReportLab paragraph styles and page layout constants for lease document rendering.

Version: 1.0.0
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch

PAGE_SETUP = {
    "pagesize": letter,
    "leftMargin": 0.75 * inch,
    "rightMargin": 0.75 * inch,
    "topMargin": 0.75 * inch,
    "bottomMargin": 0.75 * inch,
}

LEASE_MONOSPACE = ParagraphStyle(
    name="LeaseMonospace",
    fontName="Courier",
    fontSize=9,
    leading=12,
)
