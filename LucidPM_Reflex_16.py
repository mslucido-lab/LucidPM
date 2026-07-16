"""
Lucido Property Manager - Reflex App
Entry point: registers all pages and shared app config.
"""

import datetime
import reflex as rx
from fastapi import FastAPI, Request
from fastapi.responses import Response

from LucidPM_Reflex.pages.dashboard import dashboard_page, DashboardState
from LucidPM_Reflex.pages.tenants import tenants_page, TenantState
from LucidPM_Reflex.pages.rent_roll import rent_roll_page, RentRollState
from LucidPM_Reflex.pages.property_financials import property_financials_page, PropertyFinancialsState
from LucidPM_Reflex.pages.proforma import proforma_page, ProformaState
from LucidPM_Reflex.pages.waiting_list import waiting_list_page, WaitingListState
from LucidPM_Reflex.pages.properties import properties_page, PropertyState
from LucidPM_Reflex.pages.vendors import vendors_page, VendorState
from LucidPM_Reflex.pages.suites import suites_page, SuiteState
from LucidPM_Reflex.pages.rent_roll_pdf import generate_rent_roll_pdf
from LucidPM_Reflex.pages.proforma_pdf import generate_proforma_pdf
from LucidPM_Reflex.pages.property_financials_pdf import generate_property_financials_pdf
from LucidPM_Reflex.pages import communications_report  # noqa: F401
from LucidPM_Reflex.state import run_query, TEST_DB_NAME

# ── FastAPI app for custom endpoints ─────────────────────────────────────────

api = FastAPI()


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


# ── Reflex app ────────────────────────────────────────────────────────────────

app = rx.App(
    theme=rx.theme(appearance="light", accent_color="blue", radius="medium"),
    api_transformer=api,
)

app.add_page(dashboard_page,            route="/",                  on_load=DashboardState.on_load)
app.add_page(tenants_page,              route="/tenants",           on_load=TenantState.on_load)
app.add_page(rent_roll_page,            route="/rent-roll",         on_load=RentRollState.on_load)
app.add_page(property_financials_page,  route="/property-financials", on_load=PropertyFinancialsState.on_load)
app.add_page(proforma_page,             route="/proforma",          on_load=ProformaState.on_load)
app.add_page(waiting_list_page,         route="/waiting-list",      on_load=WaitingListState.on_load)
app.add_page(properties_page,           route="/admin/properties",  on_load=PropertyState.on_load)
app.add_page(vendors_page,              route="/admin/vendors",     on_load=VendorState.on_load)
app.add_page(suites_page,               route="/admin/suites",      on_load=SuiteState.on_load)
