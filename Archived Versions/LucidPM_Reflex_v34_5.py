"""
Lucido Property Manager - Reflex App
Entry point: registers all pages and shared app config.

Patch v34.2: adds native attachment file picker endpoint and preserves Communications Hub routes.
"""

import datetime
import os
import reflex as rx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response, JSONResponse

from LucidPM_Reflex.pages.dashboard import dashboard_page, DashboardState
from LucidPM_Reflex.pages.tenants import tenants_page, TenantState
from LucidPM_Reflex.pages.rent_roll import rent_roll_page, RentRollState
from LucidPM_Reflex.pages.property_financials import property_financials_page, PropertyFinancialsState
from LucidPM_Reflex.pages.property_financials_analytics import page_property_financials_analytics, PropertyFinancialsAnalyticsState
from LucidPM_Reflex.pages.proforma import proforma_page, ProformaState
from LucidPM_Reflex.pages.waiting_list import waiting_list_page, WaitingListState
from LucidPM_Reflex.pages.lease_package_builder import lease_package_builder_page, LeasePackageBuilderState 
from LucidPM_Reflex.pages.properties import properties_page, PropertyState
from LucidPM_Reflex.pages.vendors import vendors_page, VendorState
from LucidPM_Reflex.pages.suites import suites_page, SuiteState
from LucidPM_Reflex.pages.lease_documents import lease_documents_page, LeaseDocumentState
from LucidPM_Reflex.pages.admin_settings import admin_settings_page, AdminSettingsState
from LucidPM_Reflex.pages.work_items import work_items_page, WorkItemState
from LucidPM_Reflex.pages.leases_expiring import leases_expiring_page, LeasesExpiringState
from LucidPM_Reflex.pages.rent_roll_pdf import generate_rent_roll_pdf
from LucidPM_Reflex.pages.proforma_pdf import generate_proforma_pdf
from LucidPM_Reflex.pages.property_financials_pdf import generate_property_financials_pdf
from LucidPM_Reflex.pages.communications import communications_page, CommunicationsState
from LucidPM_Reflex.state import run_query, TEST_DB_NAME

# ── FastAPI app for custom endpoints ─────────────────────────────────────────

api = FastAPI()

@api.get("/api/pick-files")
async def pick_files():
    """Open a native Windows file dialog on a dedicated thread."""
    import asyncio
    import tkinter as tk
    from tkinter import filedialog
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.responses import JSONResponse

    def _open_dialog():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        root.lift()
        root.focus_force()
        root.update()
        paths = filedialog.askopenfilenames(
            parent=root,
            title="Select files to attach",
            initialdir=r"C:\\Dell Inspirion\\TenantCRM\\LeaseDocuments\\Generated",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        root.destroy()
        return list(paths)

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            paths = await loop.run_in_executor(pool, _open_dialog)
        return JSONResponse({"paths": paths})
    except Exception as ex:
        return JSONResponse({"paths": [], "error": str(ex)})

@api.get("/api/rent-roll-pdf")
async def rent_roll_pdf_endpoint(request: Request):
    params      = request.query_params
    as_of_str   = params.get("as_of", "")
    prop_filter = params.get("property", "All")
    basis       = params.get("basis", "Tax")
    db          = params.get("db", TEST_DB_NAME)

    try:
        as_of = datetime.datetime.strptime(as_of_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        as_of = datetime.date.today()

    fixed_term_types = {"fixed term", "option term", "multi-year", "multi year"}

    suite_sql = (
        "SELECT ps.SuiteID, ps.PropertyID, ps.SuiteLabel, ps.SquareFeet, "
        "ps.SuiteUseType, ps.UnderwritingRent, p.PropertyName "
        "FROM PropertySuites ps "
        "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
        "WHERE ps.IsActive = 1 "
    )
    suite_params = []
    if prop_filter != "All":
        suite_sql += "AND p.PropertyName = ? "
        suite_params.append(prop_filter)
    suite_sql += "ORDER BY p.PropertyName, ps.SortOrder, ps.SuiteLabel"
    suites = run_query(suite_sql, tuple(suite_params), db=db)

    lease_sql = (
        "SELECT l.LeaseID, l.SuiteID AS LeaseSuiteID, l.PropertyID, "
        "l.LeaseStart, l.LeaseEnd, l.RentAmount, ts.TenantStatusName, "
        "t.SuiteID AS TenantSuiteID, t.Suite AS TenantSuite, "
        "ltt.LeaseTermTypeName, t.TenantName "
        "FROM Leases l "
        "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
        "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
        "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
        "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
        "WHERE (l.LeaseStart <= ? AND (l.LeaseEnd IS NULL OR l.LeaseEnd >= ?)) "
        "AND ISNULL(ts.TenantStatusName, '') != 'Default' "
    )
    lease_params = [as_of, as_of]
    if prop_filter != "All":
        lease_sql += "AND p.PropertyName = ? "
        lease_params.append(prop_filter)
    leases = run_query(lease_sql, tuple(lease_params), db=db)

    holdover_sql = (
        "SELECT l.LeaseID, l.SuiteID AS LeaseSuiteID, l.PropertyID, "
        "l.LeaseStart, l.LeaseEnd, l.RentAmount, "
        "t.SuiteID AS TenantSuiteID, t.Suite AS TenantSuite, "
        "ltt.LeaseTermTypeName, t.TenantName "
        "FROM Leases l "
        "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
        "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
        "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
        "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
        "WHERE l.LeaseEnd < ? AND l.LeaseEnd IS NOT NULL "
        "AND ts.TenantStatusName = 'Active' "
        "AND ISNULL(t.Suite, '') != '' "
    )
    holdover_params = [as_of]
    if prop_filter != "All":
        holdover_sql += "AND p.PropertyName = ? "
        holdover_params.append(prop_filter)
    holdover_leases = [
        l for l in run_query(holdover_sql, tuple(holdover_params), db=db)
        if str(l.get("LeaseTermTypeName") or "").strip().lower() in fixed_term_types
    ]

    def find_lease(suite_id, prop_id, suite_label, pool):
        for l in pool:
            sid = l.get("LeaseSuiteID")
            if sid is not None and int(sid) == suite_id:
                return l
        for l in pool:
            tsid = l.get("TenantSuiteID")
            if tsid is not None and int(tsid) == suite_id and int(l.get("PropertyID", -1)) == prop_id:
                return l
        for l in pool:
            if (int(l.get("PropertyID", -1)) == prop_id and
                    str(l.get("TenantSuite") or "").strip().upper() == suite_label.upper()):
                return l
        return None

    def fmt_dt(v):
        if v is None: return ""
        d = v.date() if hasattr(v, "date") else v
        return d.strftime("%m/%d/%Y")

    def fmt_money(v):
        try: return f"${float(v):,.2f}" if v is not None else ""
        except: return ""

    def fmt_sqft(v):
        try: return f"{float(v):,.0f}" if v is not None else ""
        except: return ""

    rows = []
    total_rentable = total_occupied = 0.0
    psf_entries = []

    for s in suites:
        sid        = int(s["SuiteID"])
        prop_id    = int(s["PropertyID"])
        label      = str(s.get("SuiteLabel") or "").strip()
        prop_name  = str(s.get("PropertyName") or "")
        sqft_raw   = s.get("SquareFeet")
        use_type   = str(s.get("SuiteUseType") or "Standard").strip()
        under_rent = s.get("UnderwritingRent")

        try: sqft_num = float(sqft_raw or 0)
        except: sqft_num = 0.0
        total_rentable += sqft_num

        am = find_lease(sid, prop_id, label, leases)
        hm = find_lease(sid, prop_id, label, holdover_leases) if am is None else None

        if am is not None:
            total_occupied += sqft_num
            rent = am.get("RentAmount")
            try:
                if sqft_num > 0 and float(rent or 0) > 0:
                    psf_entries.append((sqft_num, float(rent)))
            except: pass
            rows.append({"property_name": prop_name, "suite": label,
                "sq_ft": fmt_sqft(sqft_raw), "occupancy": "Occupied",
                "occupant": str(am.get("TenantName") or "").strip(),
                "rental_rate": fmt_money(rent),
                "lease_type": str(am.get("LeaseTermTypeName") or ""),
                "lease_start": fmt_dt(am.get("LeaseStart")),
                "lease_end": fmt_dt(am.get("LeaseEnd"))})
        elif hm is not None:
            total_occupied += sqft_num
            rows.append({"property_name": prop_name, "suite": label,
                "sq_ft": fmt_sqft(sqft_raw), "occupancy": "Occupied",
                "occupant": str(hm.get("TenantName") or "").strip(),
                "rental_rate": fmt_money(hm.get("RentAmount")),
                "lease_type": "Month-to-Month (holdover)",
                "lease_start": "", "lease_end": ""})
        else:
            is_oo = basis == "Bank" and use_type == "Owner Occupied"
            if is_oo: total_occupied += sqft_num
            rows.append({"property_name": prop_name, "suite": label,
                "sq_ft": fmt_sqft(sqft_raw),
                "occupancy": "Occupied" if is_oo else "Vacant",
                "occupant": "Owner Occupied" if is_oo else "",
                "rental_rate": fmt_money(under_rent) if is_oo else "",
                "lease_type": "Owner Occupied" if is_oo else "",
                "lease_start": "", "lease_end": ""})

    vac_pct = ((total_rentable - total_occupied) / total_rentable * 100) if total_rentable > 0 else 0.0
    avg_psf = None
    if psf_entries:
        avg_psf = sum(r * 12 for _, r in psf_entries) / sum(sf for sf, _ in psf_entries)

    prop_detail_rows = []
    prop_address = ""
    tax_acct = ""
    if prop_filter != "All":
        prop_detail_rows = run_query(
            "SELECT ISNULL(PropertyAddress1,'') + "
            "CASE WHEN PropertyCity IS NOT NULL THEN ', ' + PropertyCity ELSE '' END + "
            "CASE WHEN PropertyState IS NOT NULL THEN ', ' + PropertyState ELSE '' END + "
            "CASE WHEN PropertyZip IS NOT NULL THEN ' ' + PropertyZip ELSE '' END AS Address, "
            "ISNULL(TaxAccountNumber,'') AS TaxAccountNumber "
            "FROM Properties WHERE PropertyName = ?",
            (prop_filter,), db=db,
        )
        if prop_detail_rows:
            prop_address = str(prop_detail_rows[0].get("Address") or "").strip()
            tax_acct = str(prop_detail_rows[0].get("TaxAccountNumber") or "").strip()

    prop_label = prop_filter if prop_filter != "All" else "All Properties"
    pdf_bytes = generate_rent_roll_pdf(
        rows=rows, as_of_date=as_of, property_name=prop_label, basis=basis,
        property_address=prop_address, tax_account_number=tax_acct,
        total_rentable_sqft=total_rentable, total_occupied_sqft=total_occupied,
        vacancy_rate_pct=vac_pct, avg_annual_psf=avg_psf,
    )
    filename = f"rent_roll_{as_of.strftime('%Y%m%d')}_{prop_label.replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/api/proforma-pdf")
async def proforma_pdf_endpoint(request: Request):
    """Generate proforma PDF. Params: year, property, basis, db"""
    params       = request.query_params
    year_str     = params.get("year", str(datetime.date.today().year))
    prop_filter  = params.get("property", "All")
    basis        = params.get("basis", "Tax")
    db           = params.get("db", TEST_DB_NAME)

    try:
        year = int(year_str)
    except (ValueError, TypeError):
        year = datetime.date.today().year

    # Re-run computation server-side using same logic as ProformaState._do_compute
    from LucidPM_Reflex.pages.proforma import ProformaState
    state = ProformaState()
    state.use_test_db = (db == TEST_DB_NAME)
    state.proforma_year = year
    state.basis = basis

    # Load properties to resolve name → id
    prop_rows = run_query("SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName", db=db)
    prop_names = [str(r["PropertyName"]) for r in prop_rows]
    prop_ids   = [int(r["PropertyID"]) for r in prop_rows]
    state.property_names = prop_names
    state.property_ids   = prop_ids
    state.selected_property = prop_filter if prop_filter in prop_names else (prop_names[0] if prop_names else "")

    state._do_compute()

    # Get property address and tax account
    prop_address = ""
    tax_acct = ""
    if prop_filter != "All":
        detail = run_query(
            "SELECT ISNULL(PropertyAddress1,'') + "
            "CASE WHEN PropertyCity IS NOT NULL THEN ', ' + PropertyCity ELSE '' END + "
            "CASE WHEN PropertyState IS NOT NULL THEN ', ' + PropertyState ELSE '' END + "
            "CASE WHEN PropertyZip IS NOT NULL THEN ' ' + PropertyZip ELSE '' END AS Address, "
            "ISNULL(TaxAccountNumber,'') AS TaxAccountNumber "
            "FROM Properties WHERE PropertyName = ?",
            (prop_filter,), db=db,
        )
        if detail:
            prop_address = str(detail[0].get("Address") or "").strip()
            tax_acct = str(detail[0].get("TaxAccountNumber") or "").strip()

    # Convert rows to serializable format for PDF generator
    rows_for_pdf = []
    for row in state.rows:
        cells_data = [{"value": c.value, "is_changed": c.is_changed,
                       "is_total_row": c.is_total_row, "is_ppsf_row": c.is_ppsf_row}
                      for c in row.cells]
        rows_for_pdf.append({"month": row.month, "cells": cells_data})

    pdf_bytes = generate_proforma_pdf(
        rows=rows_for_pdf,
        suite_headers=state.suite_headers,
        property_name=prop_filter if prop_filter != "All" else "All Properties",
        year=year,
        basis=basis,
        property_address=prop_address,
        tax_account_number=tax_acct,
    )

    filename = f"proforma_{prop_filter.replace(' ', '_')}_{year}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/api/property-financials-pdf")
async def property_financials_pdf_endpoint(request: Request):
    """Generate property financials PDF. Params: property, mode, cap_rate, year, db"""
    params      = request.query_params
    prop_filter = params.get("property", "")
    mode        = params.get("mode", "Single Year")
    db          = params.get("db", TEST_DB_NAME)
    year_str    = params.get("year", str(datetime.date.today().year))
    cap_rate    = float(params.get("cap_rate", "6.0"))

    try:
        fiscal_year = int(year_str)
    except (ValueError, TypeError):
        fiscal_year = datetime.date.today().year

    # Get property ID
    prop_rows = run_query("SELECT PropertyID, PropertyName FROM Properties WHERE PropertyName=?",
                          (prop_filter,), db=db)
    if not prop_rows:
        return Response(content=b"Property not found", status_code=404)
    prop_id = int(prop_rows[0]["PropertyID"])

    # Get total rentable sq ft
    sqft_rows = run_query(
        "SELECT ISNULL(SUM(SquareFeet),0) AS total FROM PropertySuites WHERE PropertyID=? AND IsActive=1",
        (prop_id,), db=db,
    )
    total_sqft = float(sqft_rows[0]["total"] or 0) if sqft_rows else 0.0

    # Get property address
    detail = run_query(
        "SELECT ISNULL(PropertyAddress1,'') + "
        "CASE WHEN PropertyCity IS NOT NULL THEN ', ' + PropertyCity ELSE '' END + "
        "CASE WHEN PropertyState IS NOT NULL THEN ', ' + PropertyState ELSE '' END + "
        "CASE WHEN PropertyZip IS NOT NULL THEN ' ' + PropertyZip ELSE '' END AS Address, "
        "ISNULL(TaxAccountNumber,'') AS TaxAccountNumber "
        "FROM Properties WHERE PropertyID=?",
        (prop_id,), db=db,
    )
    prop_address = str(detail[0].get("Address") or "").strip() if detail else ""
    tax_acct = str(detail[0].get("TaxAccountNumber") or "").strip() if detail else ""

    # Load financials
    fin_rows = run_query(
        "SELECT FiscalYear, TotalRevenue, TotalOperatingExpenses, Notes "
        "FROM PropertyFinancials WHERE PropertyID=? ORDER BY FiscalYear DESC",
        (prop_id,), db=db,
    )
    existing = {int(r["FiscalYear"]): r for r in fin_rows}

    # Single year
    rec = existing.get(fiscal_year, {})
    revenue = float(rec.get("TotalRevenue") or 0) if rec else 0.0
    opex    = float(rec.get("TotalOperatingExpenses") or 0) if rec else 0.0
    notes   = str(rec.get("Notes") or "") if rec else ""

    # Trend rows — only years with data
    trend_rows = []
    for yr, r in sorted(existing.items(), reverse=True):
        rev  = float(r.get("TotalRevenue") or 0)
        opx  = float(r.get("TotalOperatingExpenses") or 0)
        noi  = rev - opx
        est  = (noi / (cap_rate / 100.0)) if cap_rate > 0 and noi > 0 else 0.0
        psf  = (est / total_sqft) if total_sqft > 0 and est > 0 else 0.0
        if rev != 0 or opx != 0:
            trend_rows.append({
                "fiscal_year": yr,
                "total_revenue_raw": rev,
                "total_opex_raw": opx,
                "noi_raw": noi,
                "est_value_raw": est,
                "psf_raw": psf,
            })

    pdf_bytes = generate_property_financials_pdf(
        property_name=prop_filter,
        report_mode=mode,
        cap_rate=cap_rate,
        total_rentable_sqft=total_sqft,
        fiscal_year=fiscal_year,
        revenue=revenue,
        opex=opex,
        notes=notes,
        trend_rows=trend_rows,
        property_address=prop_address,
        tax_account_number=tax_acct,
    )

    filename = f"property_financials_{prop_filter.replace(' ', '_')}_{fiscal_year}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/api/communications-pdf")
async def communications_pdf_endpoint(request: Request):
    """Generate communications report PDF. Params: tenant_id, start, end, db"""
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    params        = request.query_params
    tenant_id_str = params.get("tenant_id", "")
    start         = params.get("start", "")
    end           = params.get("end", "")
    db            = params.get("db", TEST_DB_NAME)

    try:
        tenant_id = int(tenant_id_str)
    except (ValueError, TypeError):
        return Response(content=b"Invalid tenant_id", status_code=400)

    # Tenant name
    name_rows   = run_query("SELECT [TenantName] FROM [Tenants] WHERE [TenantID] = ?", (tenant_id,), db=db)
    tenant_name = str(name_rows[0]["TenantName"]).strip() if name_rows else f"Tenant {tenant_id}"

    # Property map
    prop_rows   = run_query("SELECT [PropertyID], [PropertyName] FROM [Properties]", db=db)
    prop_map    = {int(r["PropertyID"]): str(r["PropertyName"]) for r in prop_rows}

    # Column-sniff
    col_rows  = run_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='Communications'",
        db=db,
    )
    available = {r["COLUMN_NAME"] for r in col_rows}
    preferred = ["CommunicationID", "CommDate", "Method", "Subject", "TemplateName",
                 "Outcome", "Body", "NextActionDate", "Notes", "PropertyID"]
    cols = [f"[{c}]" for c in preferred if c in available]

    sql    = f"SELECT {', '.join(cols)} FROM [Communications] WHERE [TenantID] = ?"
    params_list: list = [tenant_id]
    if start and "CommDate" in available:
        sql += " AND [CommDate] >= ?"
        params_list.append(datetime.datetime.fromisoformat(start))
    if end and "CommDate" in available:
        sql += " AND [CommDate] <= ?"
        params_list.append(datetime.datetime.fromisoformat(end) + datetime.timedelta(days=1) - datetime.timedelta(seconds=1))
    if "CommDate" in available:
        sql += " ORDER BY [CommDate] ASC"

    rows = run_query(sql, tuple(params_list), db=db)

    def _fdt(v):
        if v is None:
            return ""
        if isinstance(v, datetime.datetime):
            return v.strftime("%m/%d/%Y %H:%M")
        if isinstance(v, datetime.date):
            return v.strftime("%m/%d/%Y")
        return str(v)

    # Build PDF
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story  = [
        Paragraph(f"Communications Report — {tenant_name}", styles["Title"]),
        Paragraph(f"{start} to {end}", styles["Normal"]),
        Spacer(1, 12),
    ]

    if not rows:
        story.append(Paragraph("No communications found.", styles["Normal"]))
    else:
        for row in rows:
            pid       = row.get("PropertyID")
            prop_name = prop_map.get(int(pid), "") if pid is not None else ""
            parts     = [p for p in [_fdt(row.get("CommDate")), str(row.get("Method") or ""), str(row.get("Subject") or "")] if p]
            header    = " | ".join(parts) or "Communication"
            if prop_name:
                header += f"  [{prop_name}]"
            story.append(Paragraph(header, styles["Heading4"]))
            if row.get("TemplateName"):
                story.append(Paragraph(f"Template: {row['TemplateName']}", styles["Normal"]))
            if row.get("Outcome"):
                story.append(Paragraph(f"Outcome: {row['Outcome']}", styles["Normal"]))
            if row.get("Notes"):
                story.append(Paragraph(str(row["Notes"]).replace("\n", "<br/>"), styles["Normal"]))
            if row.get("NextActionDate"):
                story.append(Paragraph(f"Next action: {_fdt(row['NextActionDate'])}", styles["Normal"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)

    filename = f"tenant_{tenant_id}_communications.pdf"
    return Response(
        content=buffer.read(), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/api/leases-expiring-pdf")
async def leases_expiring_pdf_endpoint(request: Request):
    """Generate leases expiring PDF. Params: horizon, db"""
    import io, math
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from LucidPM_Reflex.pages.leases_expiring import (
        _build_events, _to_date, _rent_as_of, _rent_on_date,
        _recommended_rent, _has_successor, _fmt_currency,
    )

    params       = request.query_params
    horizon_days = int(params.get("horizon", "60"))
    db           = params.get("db", TEST_DB_NAME)

    today   = datetime.date.today()
    horizon = today + datetime.timedelta(days=horizon_days)

    # ── Data queries (same as LeasesExpiringState.load_events) ────────────
    prop_rows   = run_query("SELECT PropertyID, PropertyName FROM Properties", db=db)
    prop_map    = {int(r["PropertyID"]): str(r["PropertyName"]) for r in prop_rows}

    tenant_rows = run_query(
        "SELECT t.TenantID, t.TenantName FROM Tenants t "
        "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
        "WHERE ISNULL(ts.TenantStatusName, '') IN ('Active', 'Default', '')",
        db=db,
    )
    tenant_map = {int(r["TenantID"]): str(r["TenantName"]) for r in tenant_rows}

    term_rows = run_query("SELECT LeaseTermTypeID, LeaseTermTypeName FROM LeaseTermTypes", db=db)
    term_map  = {int(r["LeaseTermTypeID"]): str(r["LeaseTermTypeName"]) for r in term_rows}

    leases = run_query(
        "SELECT l.LeaseID, l.TenantID, l.PropertyID, l.SuiteID, "
        "l.LeaseTermTypeID, l.LeaseStart, l.LeaseEnd, l.RentAmount, "
        "t.Suite AS TenantSuite, t.SuiteID AS TenantSuiteID "
        "FROM Leases l "
        "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
        "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
        "WHERE ISNULL(ts.TenantStatusName, '') IN ('Active', 'Default', '')",
        db=db,
    )

    lease_ids = [int(r["LeaseID"]) for r in leases if r.get("LeaseID")]
    sched = []
    for i in range(0, len(lease_ids), 100):
        batch = lease_ids[i:i+100]
        placeholders = ",".join(["?"] * len(batch))
        sched += run_query(
            f"SELECT LeaseID, EffectiveStartDate, EffectiveEndDate, RentAmount "
            f"FROM LeaseRentSchedule WHERE LeaseID IN ({placeholders})",
            tuple(batch), db=db,
        )

    events = _build_events(leases, sched, prop_map, tenant_map, term_map, today, horizon)

    # ── PDF build ─────────────────────────────────────────────────────────
    BRAND_PRIMARY_RGB = colors.HexColor("#4A63A8")
    BRAND_DARK_RGB    = colors.HexColor("#2F4C97")
    EXPIRATION_BG     = colors.HexColor("#fce4ec")
    ESCALATION_BG     = colors.HexColor("#e8f5e9")
    HEADER_BG         = colors.HexColor("#EEF2FA")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(letter),
        leftMargin=0.5*inch, rightMargin=0.5*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title", parent=styles["Normal"],
        fontSize=16, textColor=BRAND_DARK_RGB, fontName="Helvetica-Bold",
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#666666"),
        spaceAfter=6,
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#888888"),
    )

    story = [
        Paragraph("Leases Expiring Report", title_style),
        Paragraph(
            f"Next {horizon_days} days &nbsp;·&nbsp; "
            f"{today.strftime('%m/%d/%Y')} – {horizon.strftime('%m/%d/%Y')} &nbsp;·&nbsp; "
            f"{'TEST' if db != 'TenantCRM' else 'PRODUCTION'} database",
            sub_style,
        ),
        HRFlowable(width="100%", thickness=1, color=BRAND_PRIMARY_RGB, spaceAfter=8),
    ]

    if not events:
        story.append(Paragraph("No lease expirations or anniversaries in this window.", styles["Normal"]))
    else:
        col_headers = ["Date", "Type", "Tenant", "Property",
                       "Current Rent", "Rec. Rent", "Rec. Increase", "Needs Schedule"]

        table_data = [col_headers]
        row_types  = []  # track event type for row coloring

        for e in events:
            table_data.append([
                e["EventDate"].strftime("%m/%d/%Y"),
                e["EventType"],
                str(e["TenantName"] or ""),
                str(e["PropertyName"] or ""),
                _fmt_currency(e["RentAmount"]),
                _fmt_currency(e["RecommendedRent"]),
                _fmt_currency(e["RecommendedIncrease"]),
                "Yes" if e["NeedsSchedule"] else "",
            ])
            row_types.append(e["EventType"])

        col_widths = [0.85*inch, 0.85*inch, 2.4*inch, 1.2*inch,
                      1.0*inch, 1.0*inch, 1.1*inch, 0.85*inch]

        style_cmds = [
            # Header row
            ("BACKGROUND",   (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR",    (0, 0), (-1, 0), BRAND_DARK_RGB),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
            ("TOPPADDING",   (0, 0), (-1, 0), 6),
            # Body
            ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 1), (-1, -1), 8),
            ("TOPPADDING",   (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FF")]),
            # Grid
            ("GRID",         (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D8EE")),
            ("LINEBELOW",    (0, 0), (-1, 0),  0.75, BRAND_PRIMARY_RGB),
            # Alignment
            ("ALIGN",        (4, 0), (-1, -1), "RIGHT"),
            ("ALIGN",        (0, 0), (3, -1),  "LEFT"),
        ]

        # Color event type cells by type
        for i, etype in enumerate(row_types):
            row_idx = i + 1
            if etype == "Expiration":
                style_cmds.append(("BACKGROUND", (1, row_idx), (1, row_idx), EXPIRATION_BG))
                style_cmds.append(("TEXTCOLOR",  (1, row_idx), (1, row_idx), colors.HexColor("#b71c1c")))
                style_cmds.append(("FONTNAME",   (1, row_idx), (1, row_idx), "Helvetica-Bold"))
            else:
                style_cmds.append(("BACKGROUND", (1, row_idx), (1, row_idx), ESCALATION_BG))
                style_cmds.append(("TEXTCOLOR",  (1, row_idx), (1, row_idx), colors.HexColor("#1b5e20")))
                style_cmds.append(("FONTNAME",   (1, row_idx), (1, row_idx), "Helvetica-Bold"))
            # Rec. Rent green, Rec. Increase blue
            style_cmds.append(("TEXTCOLOR", (5, row_idx), (5, row_idx), colors.HexColor("#2e7d32")))
            style_cmds.append(("FONTNAME",  (5, row_idx), (5, row_idx), "Helvetica-Bold"))
            style_cmds.append(("TEXTCOLOR", (6, row_idx), (6, row_idx), colors.HexColor("#1565c0")))

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle(style_cmds))
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "Expiration — fixed-term lease ending in window. &nbsp;"
            "Escalation — next rent anniversary for active lease. &nbsp;"
            "Needs Schedule — no effective rent schedule row found; header rent used.",
            note_style,
        ))

    doc.build(story)
    buffer.seek(0)

    filename = f"leases_expiring_{horizon_days}d_{today.strftime('%Y%m%d')}.pdf"
    return Response(
        content=buffer.read(), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@api.get("/api/lease-generated-pdf")
async def lease_generated_pdf_endpoint(request: Request):
    """Download a generated lease package PDF by LeaseGeneratedDocumentID."""
    params = request.query_params
    generated_id_str = params.get("generated_id", "")
    db = params.get("db", TEST_DB_NAME)

    try:
        generated_id = int(generated_id_str)
    except (ValueError, TypeError):
        return Response(content=b"Invalid generated_id", status_code=400)

    rows = run_query(
        "SELECT LeaseGeneratedDocumentID, GeneratedFileName, StoredFilePath "
        "FROM LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID = ?",
        (generated_id,),
        db=db,
    )
    if not rows:
        return Response(content=b"Generated lease package not found", status_code=404)

    row = rows[0]
    file_path = str(row.get("StoredFilePath") or "").strip()
    filename = str(row.get("GeneratedFileName") or os.path.basename(file_path) or "lease_package.pdf").strip()

    if not file_path or not os.path.isfile(file_path):
        msg = f"Generated PDF file not found on disk: {file_path}"
        return Response(content=msg.encode("utf-8"), status_code=404)

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/api/application-report-pdf")
@api.get("/api/application-report-pdf/")
def application_report_pdf(request: Request, background_tasks: BackgroundTasks):
    import os as _os
    import tempfile
    from fastapi.responses import JSONResponse
    from LucidPM_Reflex.pages.tenants import (
        _parse_notes_dict, NOTES_FIELD_MAP,
        _build_application_report_pdf,
    )

    params = request.query_params
    tenant_id_raw = str(params.get("tenant_id", "")).strip()
    try:
        tenant_id = int(tenant_id_raw)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid tenant_id"}, status_code=400)

    requested_db = str(params.get("db", "")).strip()
    db_candidates = []
    if requested_db:
        db_candidates.append(requested_db)
    for candidate in [TEST_DB_NAME, "TenantCRM"]:
        if candidate and candidate not in db_candidates:
            db_candidates.append(candidate)

    tenant = None
    active_db = requested_db or TEST_DB_NAME
    for candidate_db in db_candidates:
        rows = run_query(
            "SELECT t.TenantName, t.Notes FROM Tenants t WHERE t.TenantID = ?",
            (tenant_id,),
            db=candidate_db,
        )
        if rows:
            tenant = rows[0]
            active_db = candidate_db
            break

    if not tenant:
        return JSONResponse({"error": "Tenant not found", "tenant_id": tenant_id}, status_code=404)

    contacts = run_query(
        "SELECT TOP 1 FirstName, LastName, WorkPhone, Email1 FROM Contacts "
        "WHERE TenantID = ? AND IsPrimary = 1 ORDER BY ContactID",
        (tenant_id,),
        db=active_db,
    )
    contact = contacts[0] if contacts else {}

    si_rows = run_query(
        "SELECT csi.Last4SSN, csi.DL_Last4, csi.DOB "
        "FROM ContactSensitiveInfo csi "
        "INNER JOIN Contacts c ON csi.ContactID = c.ContactID "
        "WHERE c.TenantID = ? AND c.IsPrimary = 1",
        (tenant_id,),
        db=active_db,
    )
    si = si_rows[0] if si_rows else {}

    raw = _parse_notes_dict(str(tenant.get("Notes") or ""))
    fields = {v: raw.get(k, "") for k, v in NOTES_FIELD_MAP.items()}

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    output_path = tmp.name
    tmp.close()

    _build_application_report_pdf(
        output_path=output_path,
        tenant_name=str(tenant.get("TenantName") or ""),
        contact=contact,
        si=si,
        fields=fields,
    )

    safe_name = (
        str(tenant.get("TenantName", "Applicant"))
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("&", "and")
    )

    try:
        with open(output_path, "rb") as f:
            pdf_bytes = f.read()
    finally:
        try:
            if output_path and _os.path.exists(output_path):
                _os.unlink(output_path)
        except Exception:
            pass

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Application_{safe_name}.pdf"'},
    )

# ── Reflex app ────────────────────────────────────────────────────────────────

app = rx.App(
    theme=rx.theme(appearance="light", accent_color="blue", radius="medium"),
    api_transformer=api,
)

app.add_page(dashboard_page,            route="/",                  on_load=DashboardState.on_load)
app.add_page(tenants_page,              route="/tenants",           on_load=TenantState.on_load)
app.add_page(rent_roll_page,            route="/rent-roll",         on_load=RentRollState.on_load)
app.add_page(property_financials_page,  route="/property-financials", on_load=PropertyFinancialsState.on_load)
app.add_page(page_property_financials_analytics, route="/property-financials-analytics", on_load=PropertyFinancialsAnalyticsState.on_load)
app.add_page(proforma_page,             route="/proforma",          on_load=ProformaState.on_load)
app.add_page(waiting_list_page,         route="/waiting-list",      on_load=WaitingListState.on_load)
app.add_page(lease_package_builder_page, route="/lease-package-builder", on_load=LeasePackageBuilderState.on_load)
app.add_page(properties_page,           route="/admin/properties",  on_load=PropertyState.on_load)
app.add_page(vendors_page,              route="/admin/vendors",     on_load=VendorState.on_load)
app.add_page(suites_page,               route="/admin/suites",      on_load=SuiteState.on_load)
app.add_page(lease_documents_page, route="/admin/lease-templates", on_load=LeaseDocumentState.on_load)
app.add_page(admin_settings_page,       route="/admin/settings",    on_load=AdminSettingsState.on_load)
app.add_page(communications_page, route="/communications", on_load=CommunicationsState.on_load)
# Backward-compatible alias so older cached/sidebar links do not 404 during rollout.
app.add_page(communications_page, route="/communications-report", on_load=CommunicationsState.on_load)
app.add_page(work_items_page, route="/work-items", on_load=WorkItemState.on_load)
app.add_page(leases_expiring_page, route="/leases-expiring", on_load=LeasesExpiringState.on_load)
