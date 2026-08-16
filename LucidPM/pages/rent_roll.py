"""
Rent Roll page — as-of-date snapshot of suite occupancy across all properties.

Layout:
  - Filter bar (as-of date, property, basis)
  - Four stat tiles (rentable sq ft, occupied sq ft, vacancy rate, avg rent PSF)
  - Rent roll table (one row per suite)

Lease matching logic ported from Streamlit page_rent_roll():
  - Active leases: start <= as_of_date <= end (or open-ended)
  - Holdover: fixed-term lease expired but tenant still Active status
  - Owner Occupied: Bank basis treats these as occupied at underwriting rent
  - Unlinked: active leases with no matching suite record
"""

import reflex as rx
import datetime

from LucidPM.state import (
    AppState, run_query,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM.components.sidebar import page_shell

# Dynamic page width. Updated by sidebar resizer via CSS variable.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"


# ── Data model ────────────────────────────────────────────────────────────────

class RentRollRow(rx.Base):
    property_name: str = ""
    suite: str = ""
    sq_ft: str = ""
    occupancy: str = ""
    occupant: str = ""
    rental_rate: str = ""
    lease_type: str = ""
    lease_start: str = ""
    lease_end: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class RentRollState(AppState):

    # Filters
    as_of_date: str = ""
    property_filter: str = "All"
    basis: str = "Tax"
    property_options: list[str] = ["All"]

    # Results
    rows: list[RentRollRow] = []
    total_rentable_sqft: str = ""
    total_occupied_sqft: str = ""
    vacancy_rate: str = ""
    avg_annual_psf: str = ""

    is_loading: bool = False

    def on_load(self):
        # Default as_of_date to today
        self.as_of_date = datetime.date.today().strftime("%Y-%m-%d")
        self._load_property_options()
        self.compute_rent_roll()

    def _load_property_options(self):
        rows = run_query(
            "SELECT PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_options = ["All"] + [r["PropertyName"] for r in rows]

    def set_as_of_date(self, v: str):
        self.as_of_date = v

    def set_property_filter(self, v: str):
        self.property_filter = v

    def set_basis(self, v: str):
        self.basis = v

    def run_report(self):
        self.compute_rent_roll()

    def reload_on_db_change(self):
        """Called by AppState.toggle_db via yield — reloads rent roll data."""
        self._load_property_options()
        self.compute_rent_roll()

    def compute_rent_roll(self):
        self.is_loading = True
        try:
            self._do_compute()
        finally:
            self.is_loading = False

    def _do_compute(self):
        # Parse as_of_date
        try:
            as_of = datetime.datetime.strptime(self.as_of_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            as_of = datetime.date.today()

        # ── Load suites ──
        suite_sql = (
            "SELECT ps.SuiteID, ps.PropertyID, ps.SuiteLabel, ps.SquareFeet, "
            "ps.SuiteUseType, ps.UnderwritingRent, p.PropertyName "
            "FROM PropertySuites ps "
            "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
            "WHERE ps.IsActive = 1 "
        )
        suite_params = []
        if self.property_filter != "All":
            suite_sql += "AND p.PropertyName = ? "
            suite_params.append(self.property_filter)
        suite_sql += "ORDER BY p.PropertyName, ps.SortOrder, ps.SuiteLabel"
        suites = run_query(suite_sql, tuple(suite_params), db=self.db)

        # ── Load leases with tenant info ──
        lease_sql = (
            "SELECT l.LeaseID, l.TenantID, l.PropertyID, l.SuiteID, "
            "l.LeaseStart, l.LeaseEnd, l.RentAmount, "
            "COALESCE(lrs.RentAmount, l.RentAmount) AS EffectiveRent, "
            "ltt.LeaseTermTypeName, "
            "t.TenantName, t.Suite AS TenantSuite, t.SuiteID AS TenantSuiteID, "
            "ts.TenantStatusName "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "LEFT JOIN LeaseRentSchedule lrs "
            "ON lrs.LeaseID = l.LeaseID "
            "AND lrs.EffectiveStartDate <= ? "
            "AND (lrs.EffectiveEndDate IS NULL OR lrs.EffectiveEndDate >= ?) "
        )
        lease_params = [as_of, as_of]
        if self.property_filter != "All":
            lease_sql += "WHERE EXISTS (SELECT 1 FROM Properties p WHERE p.PropertyID = l.PropertyID AND p.PropertyName = ?) "
            lease_params.append(self.property_filter)
        leases = run_query(lease_sql, tuple(lease_params), db=self.db)

        # ── Categorize leases ──
        active_leases = []
        holdover_leases = []
        fixed_term_types = {"fixed term", "option term", "multi-year", "multi year"}

        for l in leases:
            status = str(l.get("TenantStatusName") or "").strip()
            if status.lower() == "default":
                continue
            raw_start = l.get("LeaseStart")
            raw_end   = l.get("LeaseEnd")
            if raw_start is None:
                continue
            start = raw_start.date() if hasattr(raw_start, "date") else raw_start
            end   = raw_end.date() if raw_end and hasattr(raw_end, "date") else raw_end

            if start <= as_of and (end is None or end >= as_of):
                active_leases.append(l)
            elif (
                status.lower() == "active"
                and end is not None
                and end < as_of
                and str(l.get("TenantSuite") or "").strip()
                and str(l.get("LeaseTermTypeName") or "").strip().lower() in fixed_term_types
            ):
                holdover_leases.append(l)

        # ── Build output rows ──
        def fmt_dt(v) -> str:
            if v is None:
                return ""
            d = v.date() if hasattr(v, "date") else v
            return d.strftime("%m/%d/%Y")

        def fmt_sqft(v) -> str:
            try:
                return f"{float(v):,.0f}" if v is not None else ""
            except (TypeError, ValueError):
                return ""

        def fmt_money(v) -> str:
            try:
                return f"${float(v):,.2f}" if v is not None else ""
            except (TypeError, ValueError):
                return ""

        def find_lease(suite_id: int, prop_id: int, suite_label: str, pool: list) -> dict | None:
            # Match by SuiteID
            for l in pool:
                if l.get("SuiteID") is not None and int(l["SuiteID"]) == suite_id:
                    return l
            # Fallback: TenantSuiteID + PropertyID
            for l in pool:
                tsid = l.get("TenantSuiteID")
                if tsid is not None and int(tsid) == suite_id and int(l.get("PropertyID", -1)) == prop_id:
                    return l
            # Fallback: suite label text match
            for l in pool:
                if (int(l.get("PropertyID", -1)) == prop_id and
                        str(l.get("TenantSuite") or "").strip().upper() == suite_label.upper()):
                    return l
            return None

        output_rows = []
        matched_lease_ids = set()

        for s in suites:
            sid        = int(s["SuiteID"])
            prop_id    = int(s["PropertyID"])
            label      = str(s.get("SuiteLabel") or "").strip()
            prop_name  = str(s.get("PropertyName") or "")
            sqft       = s.get("SquareFeet")
            use_type   = str(s.get("SuiteUseType") or "Standard").strip()
            under_rent = s.get("UnderwritingRent")

            active_match  = find_lease(sid, prop_id, label, active_leases)
            holdover_match = find_lease(sid, prop_id, label, holdover_leases) if active_match is None else None

            if active_match is None and holdover_match is None:
                # Vacant — unless Owner Occupied on Bank basis
                is_oo_bank = self.basis == "Bank" and use_type == "Owner Occupied"
                output_rows.append(RentRollRow(
                    property_name=prop_name,
                    suite=label,
                    sq_ft=fmt_sqft(sqft),
                    occupancy="Occupied" if is_oo_bank else "Vacant",
                    occupant="Owner Occupied" if is_oo_bank else "",
                    rental_rate=fmt_money(under_rent) if is_oo_bank else "",
                    lease_type="Owner Occupied" if is_oo_bank else "",
                    lease_start="",
                    lease_end="",
                ))
            elif active_match is not None:
                matched_lease_ids.add(int(active_match["LeaseID"]))
                output_rows.append(RentRollRow(
                    property_name=prop_name,
                    suite=label,
                    sq_ft=fmt_sqft(sqft),
                    occupancy="Occupied",
                    occupant=str(active_match.get("TenantName") or "").strip(),
                    rental_rate=fmt_money(active_match.get("EffectiveRent")),
                    lease_type=str(active_match.get("LeaseTermTypeName") or ""),
                    lease_start=fmt_dt(active_match.get("LeaseStart")),
                    lease_end=fmt_dt(active_match.get("LeaseEnd")),
                ))
            else:
                matched_lease_ids.add(int(holdover_match["LeaseID"]))
                output_rows.append(RentRollRow(
                    property_name=prop_name,
                    suite=label,
                    sq_ft=fmt_sqft(sqft),
                    occupancy="Occupied",
                    occupant=str(holdover_match.get("TenantName") or "").strip(),
                    rental_rate=fmt_money(holdover_match.get("EffectiveRent")),
                    lease_type="Month-to-Month (holdover)",
                    lease_start=fmt_dt(holdover_match.get("LeaseStart")),
                    lease_end="",
                ))

        # Unlinked active leases — active but no matching suite record
        suite_ids = {int(s["SuiteID"]) for s in suites}
        for l in active_leases:
            if int(l["LeaseID"]) in matched_lease_ids:
                continue
            sid = l.get("SuiteID")
            if sid is not None and int(sid) in suite_ids:
                continue
            prop_rows = run_query(
                "SELECT PropertyName FROM Properties WHERE PropertyID=?",
                (int(l["PropertyID"]),), db=self.db,
            ) if l.get("PropertyID") else []
            prop_name = str(prop_rows[0]["PropertyName"]) if prop_rows else ""
            output_rows.append(RentRollRow(
                property_name=prop_name,
                suite=str(l.get("TenantSuite") or "").strip(),
                sq_ft="",
                occupancy="Occupied (unlinked)",
                occupant=str(l.get("TenantName") or "").strip(),
                rental_rate=fmt_money(l.get("RentAmount")),
                lease_type=str(l.get("LeaseTermTypeName") or ""),
                lease_start=fmt_dt(l.get("LeaseStart")),
                lease_end=fmt_dt(l.get("LeaseEnd")),
            ))

        self.rows = output_rows

        # ── Compute stats ──
        total_rentable = 0.0
        total_occupied = 0.0
        psf_entries = []  # (sqft, monthly_rent)

        for s in suites:
            try:
                sqft = float(s.get("SquareFeet") or 0)
            except (TypeError, ValueError):
                sqft = 0.0
            total_rentable += sqft

        for row in output_rows:
            if not row.occupancy.lower().startswith("occupied"):
                continue
            # Parse sq_ft back from formatted string
            try:
                sqft = float(row.sq_ft.replace(",", "")) if row.sq_ft else 0.0
            except (TypeError, ValueError):
                sqft = 0.0
            total_occupied += sqft
            # Parse rental rate
            try:
                rate = float(row.rental_rate.replace("$", "").replace(",", "")) if row.rental_rate else 0.0
            except (TypeError, ValueError):
                rate = 0.0
            if sqft > 0 and rate > 0:
                psf_entries.append((sqft, rate))

        vacancy_rate = ((total_rentable - total_occupied) / total_rentable) if total_rentable > 0 else 0.0

        avg_psf = None
        if psf_entries:
            total_annual = sum(rate * 12 for _, rate in psf_entries)
            total_sf = sum(sf for sf, _ in psf_entries)
            avg_psf = total_annual / total_sf if total_sf > 0 else None

        self.total_rentable_sqft = f"{total_rentable:,.0f}"
        self.total_occupied_sqft = f"{total_occupied:,.0f}"
        self.vacancy_rate = f"{vacancy_rate:.1%}"
        self.avg_annual_psf = f"${avg_psf:,.2f}/sf" if avg_psf is not None else "—"

    @rx.var
    def pdf_download_url(self) -> str:
        """Builds the PDF endpoint URL pointing to the Reflex backend on port 8000."""
        params = f"?as_of={self.as_of_date}&property={self.property_filter}&basis={self.basis}&db={self.db}"
        return "http://localhost:8000/api/rent-roll-pdf" + params


# ── UI helpers ────────────────────────────────────────────────────────────────

def stat_tile(label: str, value: rx.Var) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(value, size="7", weight="bold", color=BRAND_DARK),
            rx.text(label, size="2", color="#666"),
            spacing="1",
            align_items="start",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_radius": "12px",
            "padding": "20px 24px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
            "flex": "1",
        },
    )


def rent_roll_row_ui(r: RentRollRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(r.property_name, size="2", color="#555")),
        rx.table.cell(rx.text(r.suite, size="2", weight="bold")),
        rx.table.cell(rx.text(r.sq_ft, size="2", color="#555")),
        rx.table.cell(
            rx.cond(
                r.occupancy == "Vacant",
                rx.badge("Vacant", color_scheme="gray", variant="soft"),
                rx.cond(
                    r.occupancy.contains("unlinked"),
                    rx.badge("Unlinked", color_scheme="orange", variant="soft"),
                    rx.badge("Occupied", color_scheme="green", variant="soft"),
                ),
            )
        ),
        rx.table.cell(rx.text(r.occupant, size="2")),
        rx.table.cell(rx.text(r.rental_rate, size="2", weight="bold", color=BRAND_DARK)),
        rx.table.cell(rx.text(r.lease_type, size="2", color="#555")),
        rx.table.cell(rx.text(r.lease_start, size="2", color="#555")),
        rx.table.cell(rx.text(r.lease_end, size="2", color="#555")),
    )


# ── Page content ──────────────────────────────────────────────────────────────

def rent_roll_content() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Heading + PDF button
            rx.hstack(
                rx.heading("Rent roll", size="5", color=BRAND_DARK),
                rx.spacer(),
                rx.cond(
                    RentRollState.rows.length() > 0,
                    rx.link(
                        rx.button("⬇ Download PDF", variant="outline",
                                  color_scheme="blue", size="2"),
                        href=RentRollState.pdf_download_url,
                        is_external=True,
                    ),
                    rx.fragment(),
                ),
                align="center", width="100%",
            ),

            # Filter bar
            rx.hstack(
                rx.vstack(
                    rx.text("As of date", size="1", color="#666"),
                    rx.input(value=RentRollState.as_of_date,
                             on_change=RentRollState.set_as_of_date,
                             type="date", size="2"),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Property", size="1", color="#666"),
                    rx.select(RentRollState.property_options,
                              value=RentRollState.property_filter,
                              on_change=RentRollState.set_property_filter,
                              size="2"),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Basis", size="1", color="#666"),
                    rx.select(
                        ["Tax", "Bank"],
                        value=RentRollState.basis,
                        on_change=RentRollState.set_basis,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.button(
                    "Run report",
                    on_click=RentRollState.run_report,
                    color_scheme="blue",
                    size="2",
                    style={"align_self": "flex-end"},
                ),
                spacing="4",
                align="end",
                wrap="wrap",
                width="100%",
            ),

            # Stat tiles
            rx.hstack(
                stat_tile("Total rentable sq ft", RentRollState.total_rentable_sqft),
                stat_tile("Total occupied sq ft", RentRollState.total_occupied_sqft),
                stat_tile("Vacancy rate", RentRollState.vacancy_rate),
                stat_tile("Avg occupied annual rent PSF", RentRollState.avg_annual_psf),
                spacing="4",
                width="100%",
            ),

            # Table
            rx.cond(
                RentRollState.rows.length() > 0,
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Property"),
                                rx.table.column_header_cell("Suite"),
                                rx.table.column_header_cell("Sq ft"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Occupant"),
                                rx.table.column_header_cell("Rent/mo"),
                                rx.table.column_header_cell("Lease type"),
                                rx.table.column_header_cell("Start"),
                                rx.table.column_header_cell("End"),
                            )
                        ),
                        rx.table.body(rx.foreach(RentRollState.rows, rent_roll_row_ui)),
                        width="100%",
                        variant="surface",
                    ),
                    width="100%",
                    overflow_x="auto",
                ),
                rx.cond(
                    RentRollState.is_loading,
                    rx.text("Computing rent roll...", color="#888", size="2"),
                    rx.text("No data — select filters and click Run report.", color="#888", size="2"),
                ),
            ),

            spacing="5",
            width="100%",
            align_items="start",
            padding="24px",
        ),
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
    )


def rent_roll_page() -> rx.Component:
    return page_shell(rent_roll_content(), current_path="/rent-roll")
