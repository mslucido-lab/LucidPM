"""
Property Financials PDF generation utility.
Called by the /api/property-financials-pdf backend endpoint.
Supports Single Year and Trend report modes.
"""

import io
import os
import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)

BASE_DIR = r"C:\Dell Inspirion\TenantCRM\LucidPM\LucidPM"


def _logo_path(filename: str) -> Optional[str]:
    for candidate in [
        os.path.join(BASE_DIR, filename),
        os.path.join(os.path.dirname(__file__), "..", filename),
        filename,
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def _get_owner_and_logo(property_name: str) -> tuple[str, Optional[str]]:
    name = str(property_name or "").strip().lower()
    if name == "broadway":
        return "Dor-Sal Capital Partners, LLC", "Dor-Sal Capital Partners Logo.png"
    if name == "walnut":
        return "Lucido Properties SP, LLC", "Lucido Properties Logo.png"
    if name == "euless":
        return "Lucido Properties 508, LLC", "Lucido Properties Logo.png"
    return "", "Lucido Properties Logo.png"


def generate_property_financials_pdf(
    property_name: str,
    report_mode: str,           # "Single Year" or "Trend"
    cap_rate: float,
    total_rentable_sqft: float,
    # Single Year fields
    fiscal_year: Optional[int] = None,
    revenue: float = 0.0,
    opex: float = 0.0,
    notes: str = "",
    # Trend fields
    trend_rows: Optional[list[dict]] = None,  # [{fiscal_year, revenue, opex, noi, est_value, price_per_sf}]
    property_address: str = "",
    tax_account_number: str = "",
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36, rightMargin=36,
        topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    owner_name, logo_filename = _get_owner_and_logo(property_name)
    logo = ""
    if logo_filename:
        logo_file = _logo_path(logo_filename)
        if logo_file:
            try:
                logo = Image(logo_file, width=170, height=70)
            except Exception:
                logo = ""

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
    left_col_width = max(available_width - right_col_width, 200)

    header_tbl = Table([[info_para, logo]], colWidths=[left_col_width, right_col_width])
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
    story.append(Spacer(1, 8))

    title = f"Property Financials — {report_mode}"
    if report_mode == "Single Year" and fiscal_year:
        title += f" ({fiscal_year})"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"Cap Rate: {cap_rate:.2f}%", styles["Normal"]))
    story.append(Spacer(1, 12))

    def fmt(v) -> str:
        try:
            return f"${float(v):,.2f}"
        except (TypeError, ValueError):
            return ""

    if report_mode == "Single Year" and fiscal_year is not None:
        noi = revenue - opex
        est_val = (noi / (cap_rate / 100.0)) if cap_rate > 0 and noi > 0 else 0.0
        psf = (est_val / total_rentable_sqft) if total_rentable_sqft > 0 and est_val > 0 else 0.0

        data = [
            ["Metric", "Value"],
            ["Fiscal Year",              str(fiscal_year)],
            ["Total Revenue",            fmt(revenue)],
            ["Total Operating Expenses", fmt(opex)],
            ["NOI",                      fmt(noi)],
            ["NOI Margin",               f"{((noi / revenue) * 100.0):.1f}%" if revenue > 0 else "0.0%"],
            ["Estimated Value",          fmt(est_val)],
            ["Price per SF",             f"${psf:,.2f}" if psf > 0 else "N/A"],
            ["Total Rentable SF",        f"{total_rentable_sqft:,.0f}"],
        ]
        if notes.strip():
            data.append(["Notes", notes.strip()])

        tbl = Table(data, colWidths=[available_width * 0.45, available_width * 0.55])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("ALIGN",      (1, 1), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F7F9FC")]),
            # Highlight NOI row
            ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#e2f0d9")),
            ("FONTNAME",   (0, 4), (-1, 4), "Helvetica-Bold"),
        ]))
        story.append(tbl)

    else:
        # Trend mode — table of all years with data
        rows = trend_rows or []
        header = ["Year", "Revenue", "Operating Exp", "NOI", "NOI Margin", "Est. Value", "Price/SF"]
        data = [header]
        for r in rows:
            yr   = str(r.get("fiscal_year", ""))
            rev  = fmt(r.get("total_revenue_raw", 0))
            opx  = fmt(r.get("total_opex_raw", 0))
            noi  = fmt(r.get("noi_raw", 0))
            est  = fmt(r.get("est_value_raw", 0))
            margin = f"{float(r.get('noi_margin', 0)):.1f}%"
            psf  = f"${float(r.get('psf_raw', 0)):,.2f}" if r.get("psf_raw") else ""
            data.append([yr, rev, opx, noi, margin, est, psf])

        col_w = available_width / 7
        tbl = Table(data, colWidths=[col_w] * 7, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
            ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 9),
            ("GRID",           (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
            ("ALIGN",          (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F7F9FC")]),
        ]))
        story.append(tbl)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
