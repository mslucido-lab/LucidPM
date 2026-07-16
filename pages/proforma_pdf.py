"""
Proforma PDF generation utility.
Called by the /api/proforma-pdf backend endpoint.
Ports proforma_pdf_bytes() from Streamlit, adapted for Reflex row data format.
"""

import io
import os
import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)

BASE_DIR = r"C:\Dell Inspirion\TenantCRM\LucidPM_Reflex\LucidPM_Reflex"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

MONTH_ABBR = {
    "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
    "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
    "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec",
    "Totals": "Totals", "PPSF": "PPSF",
}


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


def _split_suite_header(col_name: str) -> tuple[str, str, bool]:
    text = str(col_name or "").strip()
    if text in ("", "Month", "Totals"):
        return text, "", False
    if " # " in text:
        left, right = text.split(" # ", 1)
        return left.strip(), f"# {right.strip()}", True
    return "", text, False


def generate_proforma_pdf(
    rows: list[dict],          # list of ProformaRow-like dicts {month, cells[]}
    suite_headers: list[str],  # suite labels + "Totals"
    property_name: str,
    year: int,
    basis: str,
    property_address: str = "",
    tax_account_number: str = "",
) -> bytes:
    """
    Generate proforma PDF from already-computed row data.

    rows: each dict has keys: month (str), cells (list of dicts with value/is_changed/is_total_row/is_ppsf_row)
    suite_headers: list of column labels (suites + "Totals")
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=24, rightMargin=24,
        topMargin=24, bottomMargin=24,
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
    left_col_width = max(available_width - right_col_width, 300)

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

    story.append(Paragraph(f"Proforma for {year}", styles["Title"]))
    story.append(Paragraph(f"Basis: {basis}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # ── Build table data ──────────────────────────────────────────────────────
    # Column headers: Month + suite_headers
    all_cols = ["Month"] + list(suite_headers)
    col_count = len(all_cols)

    # Check if any suite needs two-line header
    use_two_line = any(
        " # " in str(h) for h in suite_headers if h not in ("Totals",)
    )

    totals_col_idx = all_cols.index("Totals") if "Totals" in all_cols else None

    if use_two_line:
        hrow1, hrow2 = [], []
        for col in all_cols:
            if col in ("Month", "Totals"):
                hrow1.append(col)
                hrow2.append("")
            else:
                building, suite, _ = _split_suite_header(col)
                hrow1.append(building)
                hrow2.append(suite)
        header_data = [hrow1, hrow2]
        repeat_rows = 2
        body_start = 2
    else:
        hrow = []
        for col in all_cols:
            if col in ("Month", "Totals"):
                hrow.append(col)
            else:
                _, suite, _ = _split_suite_header(col)
                hrow.append(suite or col)
        header_data = [hrow]
        repeat_rows = 1
        body_start = 1

    # Body rows
    body_data = []
    changed_positions = set()  # (row_idx_in_table, col_idx)
    totals_row_idx = None
    ppsf_row_idx = None

    for row in rows:
        month = str(row.get("month", ""))
        abbr_month = MONTH_ABBR.get(month, month)
        cells = row.get("cells", [])

        # cells[0] is month label, rest are suite values
        row_vals = [abbr_month]
        actual_row_idx = body_start + len(body_data)

        if month == "Totals":
            totals_row_idx = actual_row_idx
        elif month == "PPSF":
            ppsf_row_idx = actual_row_idx

        for i, cell in enumerate(cells):
            if i == 0:  # skip month cell, already added
                continue
            val = str(cell.get("value", ""))
            row_vals.append(val)
            if cell.get("is_changed") and month not in ("Totals", "PPSF"):
                changed_positions.add((actual_row_idx, i))

        body_data.append(row_vals)

    table_data = header_data + body_data

    # Column widths
    first_col_width = 52
    remaining = max(available_width - first_col_width, 200)
    other_width = remaining / max(col_count - 1, 1)
    col_widths = [first_col_width] + [other_width] * (col_count - 1)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=repeat_rows)

    style = TableStyle([
        ("GRID",   (0, 0), (-1, -1), 0.25, colors.black),
        ("ALIGN",  (0, 0), (0, -1), "LEFT"),
        ("ALIGN",  (1, body_start), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])

    # Header styling
    if use_two_line:
        style.add("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#d9d9d9"))
        style.add("FONTNAME",   (0, 0), (-1, 1), "Helvetica-Bold")
        style.add("ALIGN",      (1, 0), (-1, 1), "CENTER")
        style.add("FONTSIZE",   (0, 0), (-1, 1), 7)
        style.add("FONTSIZE",   (0, 2), (-1, -1), 8)
        style.add("TOPPADDING", (0, 0), (-1, 1), 4)
        style.add("BOTTOMPADDING", (0, 0), (-1, 1), 4)
        style.add("SPAN", (0, 0), (0, 1))
        if totals_col_idx is not None:
            style.add("SPAN", (totals_col_idx, 0), (totals_col_idx, 1))
        style.add("BACKGROUND", (0, 2), (0, -1), colors.HexColor("#fce4d6"))
    else:
        style.add("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9"))
        style.add("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold")
        style.add("ALIGN",      (1, 0), (-1, 0), "CENTER")
        style.add("FONTSIZE",   (0, 0), (-1, 0), 7)
        style.add("FONTSIZE",   (0, 1), (-1, -1), 8)
        style.add("TOPPADDING", (0, 0), (-1, 0), 4)
        style.add("BOTTOMPADDING", (0, 0), (-1, 0), 4)
        style.add("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#fce4d6"))

    # Totals row — green
    if totals_row_idx is not None:
        style.add("BACKGROUND", (0, totals_row_idx), (-1, totals_row_idx), colors.HexColor("#e2f0d9"))
        style.add("FONTNAME",   (0, totals_row_idx), (-1, totals_row_idx), "Helvetica-Bold")

    # PPSF row — blue
    if ppsf_row_idx is not None:
        style.add("BACKGROUND", (0, ppsf_row_idx), (-1, ppsf_row_idx), colors.HexColor("#ddebf7"))
        style.add("FONTNAME",   (0, ppsf_row_idx), (-1, ppsf_row_idx), "Helvetica-Bold")

    # Totals column — green
    if totals_col_idx is not None:
        style.add("BACKGROUND", (totals_col_idx, body_start), (totals_col_idx, -1), colors.HexColor("#e2f0d9"))
        style.add("FONTNAME",   (totals_col_idx, body_start), (totals_col_idx, -1), "Helvetica-Bold")

    # Changed cells — green highlight
    for row_i, col_i in changed_positions:
        style.add("BACKGROUND", (col_i, row_i), (col_i, row_i), colors.HexColor("#e2f0d9"))
        style.add("FONTNAME",   (col_i, row_i), (col_i, row_i), "Helvetica-Bold")

    tbl.setStyle(style)
    story.append(tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Tax basis: Owner Occupied suites at $0. "
        "Bank basis: uses suite Underwriting Rent. "
        "Vacant suites show recommended rent (last known +5%). "
        "Green cells indicate rent change vs prior month.",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
