"""
Proforma page — monthly rent projection by suite for a selected year.

v6.1 — Fixes proforma lease-to-suite matching by using lease SuiteID/SuiteLabel instead of tenant current Suite.

Layout:
  - Filters: year, property, basis
  - Month × Suite table with Totals row and PPSF row
  - Changed-cell highlighting (rent increases)
  - PDF download via FastAPI endpoint

All calculation logic ported from Streamlit page_proforma() and helpers.

v6.2 — Uses lease-level suite matching and carries known future lease rent for pre-commencement months.

v6.3 — Uses LeaseTerminationDate as the effective end date for terminated leases and removes future-lease carry-forward fallback.
"""

import reflex as rx
import datetime
from typing import Optional

from LucidPM_Reflex.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell


# Dynamic full-page width. Updated by sidebar.py via --lucid-sidebar-width.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ── Data models ───────────────────────────────────────────────────────────────

class ProformaCell(rx.Base):
    value: str = ""
    is_changed: bool = False    # rent increase vs prior month
    is_total_row: bool = False
    is_ppsf_row: bool = False
    is_month_col: bool = False
    is_total_col: bool = False


class ProformaRow(rx.Base):
    month: str = ""
    cells: list[ProformaCell] = []
    is_total_row: bool = False
    is_ppsf_row: bool = False


# ── State ─────────────────────────────────────────────────────────────────────

class ProformaState(AppState):

    # Filters
    proforma_year: int = 0
    selected_property: str = ""
    basis: str = "Tax"
    property_names: list[str] = []
    property_ids: list[int] = []
    year_options: list[str] = []   # stored as strings for rx.select compatibility
    selected_year_str: str = ""    # display binding for the select

    # Table
    suite_headers: list[str] = []   # suite labels + "Totals"
    rows: list[ProformaRow] = []
    is_loading: bool = False

    @rx.var
    def pdf_download_url(self) -> str:
        prop = self.selected_property if self.selected_property else "All"
        return (
            f"http://localhost:8000/api/proforma-pdf"
            f"?year={self.proforma_year}&property={prop}&basis={self.basis}&db={self.db}"
        )

    def on_load(self):
        self.proforma_year = datetime.date.today().year
        self.year_options = [str(y) for y in range(datetime.date.today().year + 2, 2000, -1)]
        self.selected_year_str = str(self.proforma_year)
        self._load_properties()
        if self.property_names:
            self.selected_property = self.property_names[0]
            self.compute_proforma()

    def _load_properties(self):
        rows = run_query(
            "SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_names = [str(r["PropertyName"]) for r in rows]
        self.property_ids   = [int(r["PropertyID"]) for r in rows]

    def set_proforma_year(self, v: str):
        try:
            self.proforma_year = int(v)
            self.selected_year_str = v
        except (TypeError, ValueError):
            pass

    def set_selected_property(self, v: str):
        self.selected_property = v

    def set_basis(self, v: str):
        self.basis = v

    def run_proforma(self):
        self.compute_proforma()

    def toggle_db(self):
        """Override to recompute when DB environment switches."""
        super().toggle_db()
        if self.property_names:
            self.compute_proforma()
        else:
            self._load_properties()
            if self.property_names:
                self.selected_property = self.property_names[0]
                self.compute_proforma()

    def reload_on_db_change(self):
        """Called by AppState.toggle_db via yield — reloads page data."""
        self._load_properties()
        if self.property_names:
            self.selected_property = self.property_names[0]
            self.compute_proforma()

    # ── Calculation helpers ───────────────────────────────────────────────────

    def _month_bounds(self, year: int, month: int):
        start = datetime.date(year, month, 1)
        if month == 12:
            end = datetime.date(year, 12, 31)
        else:
            end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
        return start, end

    def _build_segments(self, lease: dict, schedule: list[dict]) -> list[dict]:
        """Build rent segments from lease + rent schedule rows."""
        def to_date(v):
            if v is None:
                return None
            if isinstance(v, datetime.datetime):
                return v.date()
            if isinstance(v, datetime.date):
                return v
            return None

        lease_start = to_date(lease.get("LeaseStart"))
        lease_end   = to_date(lease.get("LeaseEnd")) or datetime.date(9999, 12, 31)

        # A terminated lease still contributes rent through the actual termination date.
        # LeaseStatus alone is not enough for proforma math because it has no timing.
        status = str(lease.get("LeaseStatus") or "").strip()
        termination_date = to_date(lease.get("LeaseTerminationDate"))
        if status == "Terminated" and termination_date is not None:
            lease_end = min(lease_end, termination_date)

        try:
            base_rent = float(lease.get("RentAmount") or 0)
        except (TypeError, ValueError):
            base_rent = 0.0

        if lease_start is None or lease_start > lease_end:
            return []

        if not schedule:
            return [{"start": lease_start, "end": lease_end, "rent": base_rent}]

        # Filter schedule rows for this lease, sort by start date
        sched = sorted(
            [r for r in schedule if r.get("LeaseID") == lease.get("LeaseID")
             and r.get("EffectiveStartDate") is not None],
            key=lambda r: to_date(r["EffectiveStartDate"]) or datetime.date(9999, 12, 31)
        )

        if not sched:
            return [{"start": lease_start, "end": lease_end, "rent": base_rent}]

        segments = []
        first_eff = to_date(sched[0]["EffectiveStartDate"])
        if first_eff and lease_start < first_eff:
            segments.append({
                "start": lease_start,
                "end": min(lease_end, first_eff - datetime.timedelta(days=1)),
                "rent": base_rent,
            })

        for i, row in enumerate(sched):
            eff = to_date(row["EffectiveStartDate"])
            if eff is None:
                continue
            explicit_end = to_date(row.get("EffectiveEndDate"))
            next_eff = to_date(sched[i + 1]["EffectiveStartDate"]) if i + 1 < len(sched) else None
            seg_start = max(lease_start, eff)
            seg_end = lease_end
            if explicit_end is not None:
                seg_end = min(seg_end, explicit_end)
            elif next_eff is not None:
                seg_end = min(seg_end, next_eff - datetime.timedelta(days=1))
            if seg_start <= seg_end:
                try:
                    rent_amt = float(row.get("RentAmount") or 0)
                except (TypeError, ValueError):
                    rent_amt = 0.0
                segments.append({"start": seg_start, "end": seg_end, "rent": rent_amt})

        segments = [s for s in segments if s["start"] <= s["end"]]
        if not segments:
            segments = [{"start": lease_start, "end": lease_end, "rent": base_rent}]
        return sorted(segments, key=lambda x: x["start"])

    def _calc_month_amount(self, segments: list[dict], year: int, month: int, lease_start: datetime.date = None, rent_due_day: int = None) -> float:
        import calendar
        month_start, month_end = self._month_bounds(year, month)
        valid = [s for s in segments if float(s.get("rent") or 0) > 0]
        valid = sorted(valid, key=lambda x: x["start"])

        def prorate(rent: float, start_day: int, end_day: int, days_in_month: int) -> float:
            days_occupied = max(0, end_day - start_day + 1)
            return round(rent / days_in_month * days_occupied, 2)

        for seg in valid:
            rent = float(seg["rent"])

            # Segment is already active on the 1st of the month.
            if seg["start"] <= month_start <= seg["end"]:
                # If the segment ends mid-month, prorate through the effective end date.
                if seg["end"] < month_end:
                    days_in_month = calendar.monthrange(year, month)[1]
                    return prorate(rent, 1, seg["end"].day, days_in_month)
                return round(rent, 2)

            # Segment starts inside this month.
            if month_start <= seg["start"] <= month_end:
                ls = seg["start"]
                seg_end = min(seg["end"], month_end)

                # If RentDueDay is 1 and lease starts mid-month, prorate first month.
                if rent_due_day == 1 and ls.day > 1:
                    days_in_month = calendar.monthrange(ls.year, ls.month)[1]
                    return prorate(rent, ls.day, seg_end.day, days_in_month)

                # If the segment also ends mid-month, prorate to the effective end date.
                if seg_end < month_end:
                    days_in_month = calendar.monthrange(year, month)[1]
                    return prorate(rent, ls.day, seg_end.day, days_in_month)

                return round(rent, 2)

        return 0.0

    def _recommended_rent(self, current_rent: Optional[float]) -> Optional[float]:
        if current_rent is None or current_rent <= 0:
            return None
        pct = 0.05
        min_inc = 50.0
        round_to = 5
        inc = max(current_rent * pct, min_inc)
        rec = current_rent + inc
        if round_to > 0:
            rec = round(rec / round_to) * round_to
        return rec

    def compute_proforma(self):
        self.is_loading = True
        try:
            self._do_compute()
        finally:
            self.is_loading = False

    def _do_compute(self):
        if not self.selected_property or self.proforma_year == 0:
            return

        def to_date(v):
            if v is None:
                return None
            if isinstance(v, datetime.datetime):
                return v.date()
            if isinstance(v, datetime.date):
                return v
            return None

        # Resolve property ID
        if self.selected_property not in self.property_names:
            return
        prop_id = self.property_ids[self.property_names.index(self.selected_property)]

        # ── Load suites ──
        suite_rows = run_query(
            "SELECT SuiteLabel, SquareFeet, SuiteUseType, UnderwritingRent, SortOrder "
            "FROM PropertySuites WHERE PropertyID = ? AND IsActive = 1 "
            "ORDER BY SortOrder, SuiteLabel",
            (prop_id,), db=self.db,
        )
        suites = [str(r["SuiteLabel"]).strip() for r in suite_rows if r.get("SuiteLabel")]
        if not suites:
            self.rows = []
            self.suite_headers = []
            return

        suite_sqft     = {str(r["SuiteLabel"]).strip(): r.get("SquareFeet") for r in suite_rows}
        suite_use_type = {str(r["SuiteLabel"]).strip(): str(r.get("SuiteUseType") or "Standard") for r in suite_rows}
        suite_ur       = {str(r["SuiteLabel"]).strip(): r.get("UnderwritingRent") for r in suite_rows}

        # ── Load tenants ──
        tenant_rows = run_query(
            "SELECT TenantID, Suite FROM Tenants "
            "WHERE PropertyID = ? AND ISNULL(LTRIM(RTRIM(Suite)), '') != ''",
            (prop_id,), db=self.db,
        )
        suite_to_tenant_ids: dict[str, set] = {}
        for t in tenant_rows:
            s = str(t.get("Suite") or "").strip()
            if s:
                suite_to_tenant_ids.setdefault(s, set()).add(int(t["TenantID"]))

        # ── Load leases ──
        # Include terminated leases. _build_segments() shortens their effective end
        # date to LeaseTerminationDate so historical rent remains in the proforma
        # through the actual termination date.
        lease_rows = run_query(
            "SELECT l.LeaseID, l.TenantID, l.LeaseStart, l.LeaseEnd, l.RentAmount, "
            "l.RentDueDay, l.LeaseStatus, l.LeaseTerminationDate, "
            "COALESCE(ps.SuiteLabel, t.Suite) AS TenantSuite "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "WHERE l.PropertyID = ? "
            "ORDER BY l.LeaseStart, l.LeaseID",
            (prop_id,), db=self.db,
        )

        # ── Load rent schedule ──
        schedule_rows = run_query(
            "SELECT s.LeaseRentScheduleID, s.LeaseID, s.EffectiveStartDate, "
            "s.EffectiveEndDate, s.RentAmount "
            "FROM LeaseRentSchedule s "
            "INNER JOIN Leases l ON s.LeaseID = l.LeaseID "
            "WHERE l.PropertyID = ? ORDER BY s.LeaseID, s.EffectiveStartDate",
            (prop_id,), db=self.db,
        )

        # ── Precompute segments per lease ──
        lease_segments: dict[int, list[dict]] = {}
        for l in lease_rows:
            lid = int(l["LeaseID"])
            lease_segments[lid] = self._build_segments(l, schedule_rows)

        # ── Last known rent per suite (for vacant suite recommended rent) ──
        last_known_rent: dict[str, float] = {}
        for l in sorted(lease_rows, key=lambda x: to_date(x.get("LeaseStart")) or datetime.date(1900, 1, 1)):
            suite = str(l.get("TenantSuite") or "").strip()
            if not suite:
                continue
            segs = lease_segments.get(int(l["LeaseID"]), [])
            if segs:
                last_seg = sorted(segs, key=lambda s: s["start"])[-1]
                r = float(last_seg.get("rent") or 0)
                if r > 0:
                    last_known_rent[suite] = r

        # ── Compute month data ──
        year = self.proforma_year
        data: list[dict] = []   # {month, suite_values...}
        annual_totals: dict[str, float] = {s: 0.0 for s in suites}
        changed_cells: set = set()

        prev_vals: dict[str, float] = {}
        prev_tenant_ids: dict[str, set] = {}

        for month_idx, month_name in enumerate(MONTH_NAMES):
            month_num = month_idx + 1
            month_start, month_end = self._month_bounds(year, month_num)
            row_vals: dict[str, float] = {}
            month_total = 0.0

            for suite in suites:
                use_type = suite_use_type.get(suite, "Standard")
                ur = suite_ur.get(suite)

                if use_type == "Owner Occupied":
                    if self.basis == "Bank" and ur is not None:
                        try:
                            amount = float(ur)
                        except (TypeError, ValueError):
                            amount = 0.0
                    else:
                        amount = 0.0
                    row_vals[suite] = amount
                    annual_totals[suite] += amount
                    month_total += amount
                    continue

                tenant_ids = suite_to_tenant_ids.get(suite, set())
                # Prefer the lease-level suite assignment. Tenant.Suite can be stale or point to a
                # different/current suite, which can pull an old lease into the wrong suite.
                suite_leases = [
                    l for l in lease_rows
                    if str(l.get("TenantSuite") or "").strip() == suite
                ]
                # Fallback for older lease records without SuiteID / TenantSuite data.
                if not suite_leases and tenant_ids:
                    suite_leases = [l for l in lease_rows if int(l["TenantID"]) in tenant_ids]
                suite_leases = sorted(suite_leases, key=lambda x: to_date(x.get("LeaseStart")) or datetime.date(1900, 1, 1))

                amount = 0.0
                active_found = False
                curr_tenant_ids: set = set()
                new_commencement = False

                for l in suite_leases:
                    ls = to_date(l.get("LeaseStart"))
                    le = to_date(l.get("LeaseEnd")) or datetime.date(9999, 12, 31)
                    if str(l.get("LeaseStatus") or "").strip() == "Terminated":
                        term_date = to_date(l.get("LeaseTerminationDate"))
                        if term_date is not None:
                            le = min(le, term_date)
                    if ls is None:
                        continue
                    if ls <= month_end and le >= month_start:
                        active_found = True
                        lid = int(l["LeaseID"])
                        segs = lease_segments.get(lid, [])
                        due_day = int(l.get("RentDueDay") or 1)
                        amount += self._calc_month_amount(segs, year, month_num, lease_start=ls, rent_due_day=due_day)
                        curr_tenant_ids.add(str(int(l["TenantID"])))
                        if month_start <= ls <= month_end:
                            new_commencement = True

                if not active_found:
                    rec = self._recommended_rent(last_known_rent.get(suite))
                    if rec and rec > 0:
                        # Don't show recommended rent in the same month a lease ended mid-month,
                        # including a terminated lease with a LeaseTerminationDate.
                        allow = True
                        for l in suite_leases:
                            le = to_date(l.get("LeaseTerminationDate")) if str(l.get("LeaseStatus") or "").strip() == "Terminated" else to_date(l.get("LeaseEnd"))
                            if le and le.year == year and le.month == month_num and le.day > 1:
                                allow = False
                                break
                        if allow:
                            amount = rec

                # Changed cell detection
                prev = prev_vals.get(suite)
                suppress = (
                    bool(prev_tenant_ids.get(suite))
                    and bool(curr_tenant_ids)
                    and prev_tenant_ids.get(suite, set()).isdisjoint(curr_tenant_ids)
                    and new_commencement
                )
                if (prev is not None and prev > 0 and amount > 0
                        and round(amount, 2) != round(prev, 2) and not suppress):
                    changed_cells.add((month_name, suite))

                prev_vals[suite] = amount
                prev_tenant_ids[suite] = curr_tenant_ids
                row_vals[suite] = round(amount, 2)
                annual_totals[suite] += round(amount, 2)
                month_total += round(amount, 2)

            row_vals["Totals"] = round(month_total, 2)
            row_vals["_month"] = month_name
            data.append(row_vals)

        # ── Build display rows ──
        def fmt0(v) -> str:
            try:
                f = float(v)
                return f"${f:,.0f}" if f else ""
            except (TypeError, ValueError):
                return ""

        def fmt2(v) -> str:
            try:
                return f"${float(v):,.2f}"
            except (TypeError, ValueError):
                return ""

        all_suites_plus_total = suites + ["Totals"]
        self.suite_headers = all_suites_plus_total

        rows_out: list[ProformaRow] = []

        # Month rows
        for d in data:
            month_name = d["_month"]
            cells = [ProformaCell(value=month_name, is_month_col=True)]
            for s in suites:
                v = d.get(s, 0.0)
                cells.append(ProformaCell(
                    value=fmt0(v),
                    is_changed=(month_name, s) in changed_cells,
                ))
            cells.append(ProformaCell(value=fmt0(d.get("Totals", 0.0)), is_total_col=True))
            rows_out.append(ProformaRow(month=month_name, cells=cells))

        # Totals row
        total_cells = [ProformaCell(value="Totals", is_month_col=True, is_total_row=True)]
        grand_total = sum(annual_totals.values())
        for s in suites:
            total_cells.append(ProformaCell(value=fmt0(annual_totals[s]), is_total_row=True))
        total_cells.append(ProformaCell(value=fmt0(grand_total), is_total_row=True, is_total_col=True))
        rows_out.append(ProformaRow(month="Totals", cells=total_cells, is_total_row=True))

        # PPSF row
        ppsf_cells = [ProformaCell(value="PPSF", is_month_col=True, is_ppsf_row=True)]
        total_sqft = 0.0
        for s in suites:
            sqft = suite_sqft.get(s)
            try:
                sqft_f = float(sqft) if sqft is not None else 0.0
            except (TypeError, ValueError):
                sqft_f = 0.0
            if sqft_f > 0:
                ppsf_cells.append(ProformaCell(
                    value=fmt2(annual_totals[s] / sqft_f),
                    is_ppsf_row=True,
                ))
                total_sqft += sqft_f
            else:
                ppsf_cells.append(ProformaCell(value="", is_ppsf_row=True))
        total_ppsf = fmt2(grand_total / total_sqft) if total_sqft > 0 else ""
        ppsf_cells.append(ProformaCell(value=total_ppsf, is_ppsf_row=True, is_total_col=True))
        rows_out.append(ProformaRow(month="PPSF", cells=ppsf_cells, is_ppsf_row=True))

        self.rows = rows_out


# ── UI helpers ────────────────────────────────────────────────────────────────

def cell_style(c: ProformaCell) -> dict:
    return rx.cond(
        c.is_total_row,
        {"background": "#e2f0d9", "font_weight": "700"},
        rx.cond(
            c.is_ppsf_row,
            {"background": "#ddebf7", "font_weight": "700"},
            rx.cond(
                c.is_month_col,
                {"background": "#fce4d6", "font_weight": "700"},
                rx.cond(
                    c.is_total_col,
                    {"background": "#e2f0d9", "font_weight": "700"},
                    rx.cond(
                        c.is_changed,
                        {"background": "#e2f0d9", "font_weight": "700"},
                        {"background": "transparent"},
                    ),
                ),
            ),
        ),
    )


def proforma_cell(c: ProformaCell) -> rx.Component:
    return rx.table.cell(
        rx.text(c.value, size="2"),
        style=cell_style(c),
    )


def proforma_row_ui(r: ProformaRow) -> rx.Component:
    return rx.table.row(
        rx.foreach(r.cells, proforma_cell),
    )


def suite_header_cell(s: str) -> rx.Component:
    """Split suite label on ' # ' into two lines. Works for '1614-2 # 204' pattern."""
    return rx.table.column_header_cell(
        rx.cond(
            s.contains(" # "),
            rx.vstack(
                rx.text(s.split(" # ")[0], size="1", weight="bold"),
                rx.text("# " + s.split(" # ")[1], size="1", color="#555"),
                spacing="0", align_items="start",
            ),
            rx.text(s, size="1", weight="bold"),
        ),
        style={"white_space": "nowrap", "min_width": "60px"},
    )


# ── Page content ──────────────────────────────────────────────────────────────

def proforma_content() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading("Proforma", size="5", color=BRAND_DARK),
                rx.spacer(),
                rx.cond(
                    ProformaState.rows.length() > 0,
                    rx.link(
                        rx.button("⬇ Download PDF", variant="outline",
                                  color_scheme="blue", size="2"),
                        href=ProformaState.pdf_download_url,
                        is_external=True,
                    ),
                    rx.fragment(),
                ),
                align="center", width="100%",
            ),

            # Filter bar
            rx.hstack(
                rx.vstack(
                    rx.text("Year", size="1", color="#666"),
                    rx.select(
                        ProformaState.year_options,
                        value=ProformaState.selected_year_str,
                        on_change=ProformaState.set_proforma_year,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Property", size="1", color="#666"),
                    rx.cond(
                        ProformaState.property_names.length() > 0,
                        rx.select(
                            ProformaState.property_names,
                            value=ProformaState.selected_property,
                            on_change=ProformaState.set_selected_property,
                            size="2",
                        ),
                        rx.text("Loading...", size="2", color="#888"),
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Basis", size="1", color="#666"),
                    rx.select(
                        ["Tax", "Bank"],
                        value=ProformaState.basis,
                        on_change=ProformaState.set_basis,
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.button(
                    "Run",
                    on_click=ProformaState.run_proforma,
                    color_scheme="blue", size="2",
                    style={"align_self": "flex-end"},
                ),
                spacing="4", align="end", wrap="wrap", width="100%",
            ),

            # Proforma table
            rx.cond(
                ProformaState.rows.length() > 0,
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell(
                                    rx.text("Month", size="2", weight="bold")
                                ),
                                rx.foreach(ProformaState.suite_headers, suite_header_cell),
                            )
                        ),
                        rx.table.body(rx.foreach(ProformaState.rows, proforma_row_ui)),
                        width="100%", variant="surface",
                    ),
                    width="100%",
                    overflow_x="auto",
                ),
                rx.cond(
                    ProformaState.is_loading,
                    rx.text("Computing proforma...", color="#888", size="2"),
                    rx.text("Select filters and click Run.", color="#888", size="2"),
                ),
            ),

            rx.text(
                "Tax basis: Owner Occupied suites at $0. "
                "Bank basis: uses suite Underwriting Rent. "
                "Vacant suites show recommended rent (last known +5%). "
                "Green cells = rent change vs prior month.",
                size="1", color="#888",
            ),

            spacing="5", width="100%", align_items="start", padding="24px",
        ),
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
    )


def proforma_page() -> rx.Component:
    return page_shell(proforma_content(), current_path="/proforma")
