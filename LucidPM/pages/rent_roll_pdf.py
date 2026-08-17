"""
Rent roll PDF generation — ported from Streamlit rent_roll_pdf_bytes().
Uses ReportLab, landscape letter, same layout as Streamlit version.
"""

import io
import os
import datetime
from typing import Optional

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image
)

def _logo_path(filename: str) -> Optional[str]:
    """Return absolute path to a logo file if it exists, else None."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", filename),
        filename,
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def get_owner_and_logo(property_name: str) -> tuple[str, Optional[str]]:
    """Return (owner_name, logo_filename) per property — matches Streamlit logic."""
    name = str(property_name or "").strip().lower()
    if name == "broadway":
        return "Dor-Sal Capital Partners, LLC", "Dor-Sal Capital Partners Logo.png"
    if name == "walnut":
        return "Lucido Properties SP, LLC", "Lucido Properties Logo.png"
    if name == "euless":
        return "Lucido Properties 508, LLC", "Lucido Properties Logo.png"
    return "", "Lucido Properties Logo.png"


def get_disclaimer(property_name: str) -> str:
    name = str(property_name or "").strip().lower()
    if name in ["broadway", "walnut"]:
        return ("All leases are modified-gross leases. In nearly all leases, Tenant is "
                "responsible for monthly base rent and electricity. Landlord is responsible "
                "for Taxes, Insurance, Maintenance and Repairs.")
    if name == "euless":
        return "All leases are NNN with Base Rent + CAM."
    return ""


def fmt_date(d) -> str:
    if d is None:
        return ""
    if isinstance(d, (datetime.datetime, datetime.date)):
        return d.strftime("%m/%d/%Y")
    return str(d)


def generate_rent_roll_pdf(
    rows: list[dict],
    as_of_date: datetime.date,
    property_name: str = "All Properties",
    basis: str = "Tax",
    property_address: str = "",
    tax_account_number: str = "",
    total_rentable_sqft: float = 0.0,
    total_occupied_sqft: float = 0.0,
    vacancy_rate_pct: float = 0.0,
    avg_annual_psf: Optional[float] = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=24, rightMargin=24,
        topMargin=24, bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    story = []

    # ── Per-property owner and logo ───────────────────────────────────────────
    owner_name, logo_filename = get_owner_and_logo(property_name)
    logo = ""
    if logo_filename:
        logo_file = _logo_path(logo_filename)
        if logo_file:
            try:
                logo = Image(logo_file, width=170, height=70)
            except Exception:
                logo = ""

    # ── Header: property info left, logo right ────────────────────────────────
    info_lines = [f"Property: {property_name}"]
    if property_address.strip():
        info_lines.append(f"Property Address: {property_address.strip()}")
    if tax_account_number.strip():
        info_lines.append(f"Tax Account No.: {tax_account_number.strip()}")
    if owner_name.strip():
        info_lines.append(f"Owner: {owner_name.strip()}")

    info_para = Paragraph("<br/>".join(info_lines), styles["Normal"])

    available_width = float(doc.width)
    right_col_width = 180
    left_col_width = max(available_width - right_col_width, 300)

    header_tbl = Table(
        [[info_para, logo]],
        colWidths=[left_col_width, right_col_width],
    )
    header_tbl.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN",  (0, 0), (0, 0), "LEFT"),
        ("ALIGN",  (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))

    # ── Title ─────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        f"Rent Roll as of {fmt_date(as_of_date)}",
        styles["Title"],
    ))
    story.append(Spacer(1, 10))

    # ── Summary stats ─────────────────────────────────────────────────────────
    summary_lines = [
        "<b>Summary</b>",
        f"Total Rentable SF: {total_rentable_sqft:,.0f}",
        f"Occupied SF: {total_occupied_sqft:,.0f}",
        f"Vacancy Rate: {vacancy_rate_pct:.2f}%",
    ]
    if avg_annual_psf is not None:
        summary_lines.append(f"Average Occupied Annual Rent PSF: ${avg_annual_psf:,.2f}")
    story.append(Paragraph("<br/>".join(summary_lines), styles["Normal"]))
    story.append(Spacer(1, 12))

    # ── Data table ────────────────────────────────────────────────────────────
    col_headers = [
        "Property", "Suite", "Sq Ft", "Status",
        "Occupant", "Rent/mo", "Lease Type", "Start", "End",
    ]
    col_keys = [
        "property_name", "suite", "sq_ft", "occupancy",
        "occupant", "rental_rate", "lease_type", "lease_start", "lease_end",
    ]
    col_widths = [100, 70, 50, 65, 145, 65, 100, 60, 60]

    data = [col_headers]
    for row in rows:
        data.append([str(row.get(k) or "") for k in col_keys])

    tbl = Table(data, repeatRows=1, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#D9E2F3")),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.black),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F7F9FC")]),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
    ]))
    story.append(tbl)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    disclaimer = get_disclaimer(property_name)
    if disclaimer:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<i>{disclaimer}</i>", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
