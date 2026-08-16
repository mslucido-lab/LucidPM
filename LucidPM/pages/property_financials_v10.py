"""
Property Financials page — annual revenue, opex, NOI entry and valuation.

Layout:
  - Property selector + report mode toggle (Single Year / Trend)
  - Cap rate slider
  - Summary table (all years)
  - Selected year entry form (revenue, opex, notes)
  - NOI + valuation metrics
  - Save button
"""

import reflex as rx
import datetime
from typing import Optional

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell


# Dynamic full-page width. Updated by sidebar.py via --lucid-sidebar-width.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"


# ── Data models ───────────────────────────────────────────────────────────────

class FinancialYear(rx.Base):
    fiscal_year: int = 0
    property_financial_id: int = 0   # 0 = not yet saved
    total_revenue: str = ""
    total_opex: str = ""
    noi: str = ""
    noi_raw: float = 0.0
    estimated_value: str = ""
    price_per_sf: str = ""
    noi_margin: str = ""
    notes: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class PropertyFinancialsState(AppState):

    # Selectors
    property_names: list[str] = []
    property_ids: list[int] = []
    selected_property: str = ""
    report_mode: str = "Single Year"   # "Single Year" | "Trend"
    include_projections: bool = True

    # Cap rate (stored as float 4.0–10.0)
    cap_rate: float = 6.0

    # Summary table
    years: list[FinancialYear] = []

    # Selected year form
    selected_year: int = 0
    year_options: list[str] = []
    selected_year_str: str = ""
    f_revenue: str = ""
    f_opex: str = ""
    f_notes: str = ""

    # Derived display (recomputed on save/load)
    noi_preview: str = "—"
    estimated_value_preview: str = "—"
    price_per_sf_preview: str = "—"
    noi_margin_preview: str = "0.0%"
    total_rentable_sqft: float = 0.0

    form_error: str = ""
    form_success: str = ""
    new_year_input: str = ""

    @rx.var
    def selected_property_id(self) -> int:
        if self.selected_property in self.property_names:
            return self.property_ids[self.property_names.index(self.selected_property)]
        return 0

    @rx.var
    def cap_rate_display(self) -> str:
        return f"{self.cap_rate:.2f}%"

    @rx.var
    def pdf_download_url(self) -> str:
        prop = self.selected_property if self.selected_property else ""
        mode = self.report_mode.replace(" ", "%20")
        return (
            f"http://localhost:8000/api/property-financials-pdf"
            f"?property={prop}&mode={mode}&year={self.selected_year}"
            f"&cap_rate={self.cap_rate}&db={self.db}"
        )

    @rx.var
    def displayed_years(self) -> list[FinancialYear]:
        """In Trend mode show only years with data; Single Year shows all."""
        if self.report_mode == "Single Year":
            return self.years
        # Trend: only years that have actual saved data (revenue or opex > 0)
        result = []
        for y in self.years:
            has_data = False
            for val in [y.total_revenue, y.total_opex]:
                try:
                    if float(val.replace("$", "").replace(",", "")) != 0:
                        has_data = True
                        break
                except (ValueError, AttributeError):
                    pass
            if has_data:
                result.append(y)
        return result

    def toggle_db(self):
        """Override to reload data when DB environment switches."""
        super().toggle_db()
        if self.property_names:
            self._load_financials()
        else:
            self._load_properties()
            if self.property_names:
                self.selected_property = self.property_names[0]
                self._load_financials()

    def reload_on_db_change(self):
        """Called by AppState.toggle_db via yield — reloads page data."""
        self._load_properties()
        if self.property_names:
            self.selected_property = self.property_names[0]
            self._load_financials()

    def on_load(self):
        self._load_properties()
        if self.property_names:
            self.selected_property = self.property_names[0]
            self._load_financials()

    def _load_properties(self):
        rows = run_query(
            "SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_names = [str(r["PropertyName"]) for r in rows]
        self.property_ids   = [int(r["PropertyID"]) for r in rows]

    def set_selected_property(self, v: str):
        self.selected_property = v
        self.form_error = ""
        self.form_success = ""
        self._load_financials()

    def set_report_mode(self, v: str):
        self.report_mode = v

    def set_include_projections(self, v: bool):
        self.include_projections = v

    def set_cap_rate(self, v):
        try:
            self.cap_rate = float(v[0]) if isinstance(v, list) else float(v)
        except (TypeError, ValueError, IndexError):
            return
        self._recompute_valuations()
        self._recompute_preview()

    def _load_financials(self):
        if self.selected_property_id == 0:
            return

        # Load existing records
        existing = run_query(
            "SELECT PropertyFinancialID, FiscalYear, TotalRevenue, "
            "TotalOperatingExpenses, Notes "
            "FROM PropertyFinancials "
            "WHERE PropertyID = ? ORDER BY FiscalYear DESC",
            (self.selected_property_id,), db=self.db,
        )
        existing_by_year = {int(r["FiscalYear"]): r for r in existing}

        # Total rentable sq ft
        sqft_rows = run_query(
            "SELECT ISNULL(SUM(SquareFeet), 0) AS total "
            "FROM PropertySuites WHERE PropertyID = ? AND IsActive = 1",
            (self.selected_property_id,), db=self.db,
        )
        try:
            self.total_rentable_sqft = float(sqft_rows[0]["total"] or 0)
        except (TypeError, ValueError, IndexError):
            self.total_rentable_sqft = 0.0

        # Build year list: only years with saved data + current year
        current_year = datetime.date.today().year
        year_set = set(existing_by_year.keys())
        year_set.add(current_year)
        year_list = sorted(year_set, reverse=True)
        self.year_options = [str(y) for y in year_list]

        def fmt_currency(v) -> str:
            try:
                return f"${float(v):,.2f}" if float(v) != 0 else ""
            except (TypeError, ValueError):
                return ""

        rows_out = []
        for yr in year_list:
            rec = existing_by_year.get(yr)
            pfid = int(rec["PropertyFinancialID"]) if rec else 0
            rev  = float(rec["TotalRevenue"] or 0) if rec else 0.0
            opex = float(rec["TotalOperatingExpenses"] or 0) if rec else 0.0
            noi  = rev - opex
            est_val = (noi / (self.cap_rate / 100.0)) if self.cap_rate > 0 and noi > 0 else 0.0
            psf = (est_val / self.total_rentable_sqft) if self.total_rentable_sqft > 0 and est_val > 0 else 0.0
            noi_margin = (noi / rev * 100.0) if rev > 0 else 0.0
            rows_out.append(FinancialYear(
                fiscal_year=yr,
                property_financial_id=pfid,
                total_revenue=fmt_currency(rev),
                total_opex=fmt_currency(opex),
                noi=fmt_currency(noi),
                noi_raw=noi,
                estimated_value=fmt_currency(est_val),
                price_per_sf=f"${psf:,.2f}" if psf > 0 else "",
                noi_margin=f"{noi_margin:.1f}%",
                notes=str(rec["Notes"] or "") if rec else "",
            ))
        self.years = rows_out

        # Default selected year to current
        if current_year in year_list:
            self.selected_year = current_year
            self.selected_year_str = str(current_year)
        elif year_list:
            self.selected_year = year_list[0]
            self.selected_year_str = str(year_list[0])

        self._load_selected_year_form()

    def _load_selected_year_form(self):
        if self.selected_property_id == 0 or self.selected_year == 0:
            return
        rows = run_query(
            "SELECT PropertyFinancialID, TotalRevenue, TotalOperatingExpenses, Notes "
            "FROM PropertyFinancials WHERE PropertyID = ? AND FiscalYear = ?",
            (self.selected_property_id, self.selected_year), db=self.db,
        )
        if rows:
            r = rows[0]
            try:
                self.f_revenue = str(int(float(r.get("TotalRevenue") or 0)))
            except (TypeError, ValueError):
                self.f_revenue = "0"
            try:
                self.f_opex = str(int(float(r.get("TotalOperatingExpenses") or 0)))
            except (TypeError, ValueError):
                self.f_opex = "0"
            self.f_notes = str(r.get("Notes") or "")
        else:
            self.f_revenue = "0"
            self.f_opex = "0"
            self.f_notes = ""
        self._recompute_preview()

    def set_selected_year(self, v: str):
        try:
            self.selected_year = int(v)
            self.selected_year_str = v
        except (TypeError, ValueError):
            return
        self.form_error = ""
        self.form_success = ""
        self._load_selected_year_form()

    def set_f_revenue(self, v: str): self.f_revenue = v; self._recompute_preview()
    def set_f_opex(self, v: str): self.f_opex = v; self._recompute_preview()
    def set_f_notes(self, v: str): self.f_notes = v

    def _recompute_preview(self):
        try:
            rev  = float(self.f_revenue or 0)
            opex = float(self.f_opex or 0)
            noi  = rev - opex
            self.noi_preview = f"${noi:,.2f}"
            noi_margin = round((noi / rev * 100.0), 1) if rev > 0 else 0.0
            self.noi_margin_preview = f"{noi_margin:.1f}%"
            if self.cap_rate > 0 and noi > 0:
                est = noi / (self.cap_rate / 100.0)
                self.estimated_value_preview = f"${est:,.2f}"
                if self.total_rentable_sqft > 0:
                    self.price_per_sf_preview = f"${est / self.total_rentable_sqft:,.2f}/sf"
                else:
                    self.price_per_sf_preview = "N/A"
            else:
                self.estimated_value_preview = "—"
                self.price_per_sf_preview = "—"
        except (TypeError, ValueError):
            self.noi_preview = "—"
            self.estimated_value_preview = "—"
            self.price_per_sf_preview = "—"
            self.noi_margin_preview = "0.0%"

    def _recompute_valuations(self):
        """Recompute EstimatedValue/PricePerSF for all rows after cap rate change."""
        updated = []
        for row in self.years:
            noi = row.noi_raw
            est = (noi / (self.cap_rate / 100.0)) if self.cap_rate > 0 and noi > 0 else 0.0
            psf = (est / self.total_rentable_sqft) if self.total_rentable_sqft > 0 and est > 0 else 0.0
            updated.append(FinancialYear(
                fiscal_year=row.fiscal_year,
                property_financial_id=row.property_financial_id,
                total_revenue=row.total_revenue,
                total_opex=row.total_opex,
                noi=row.noi,
                noi_raw=row.noi_raw,
                estimated_value=f"${est:,.2f}" if est > 0 else "",
                price_per_sf=f"${psf:,.2f}" if psf > 0 else "",
                noi_margin=row.noi_margin,
                notes=row.notes,
            ))
        self.years = updated

    def set_new_year_input(self, v: str):
        self.new_year_input = v

    def add_year(self):
        self.form_error = ""
        try:
            yr = int(self.new_year_input)
        except (TypeError, ValueError):
            self.form_error = "Enter a valid 4-digit year."
            return
        if yr < 1990 or yr > 2100:
            self.form_error = "Year must be between 1990 and 2100."
            return
        # Check if already exists in the table list
        existing_years = [y.fiscal_year for y in self.years]
        if yr in existing_years:
            # Just select it
            self.selected_year = yr
            self.selected_year_str = str(yr)
            self.new_year_input = ""
            self._load_selected_year_form()
            return
        # Add a blank row to the display and select it
        self.years = [FinancialYear(fiscal_year=yr)] + self.years
        self.year_options = sorted(
            list(set([str(yr)] + self.year_options)), reverse=True
        )
        self.selected_year = yr
        self.selected_year_str = str(yr)
        self.new_year_input = ""
        self.f_revenue = "0"
        self.f_opex = "0"
        self.f_notes = ""
        self._recompute_preview()

    def save_financials(self):
        self.form_error = ""
        self.form_success = ""
        if self.selected_property_id == 0:
            self.form_error = "No property selected."
            return
        try:
            rev  = float(self.f_revenue or 0)
            opex = float(self.f_opex or 0)
        except (TypeError, ValueError):
            self.form_error = "Revenue and expenses must be numbers."
            return

        now = datetime.datetime.now()
        existing = run_query(
            "SELECT PropertyFinancialID FROM PropertyFinancials "
            "WHERE PropertyID = ? AND FiscalYear = ?",
            (self.selected_property_id, self.selected_year), db=self.db,
        )
        if existing:
            run_exec(
                "UPDATE PropertyFinancials SET TotalRevenue=?, TotalOperatingExpenses=?, "
                "Notes=?, UpdatedDate=? WHERE PropertyFinancialID=?",
                (rev, opex, self.f_notes, now, int(existing[0]["PropertyFinancialID"])),
                db=self.db,
            )
            self.form_success = f"{self.selected_year} financials saved."
        else:
            run_exec(
                "INSERT INTO PropertyFinancials (PropertyID, FiscalYear, TotalRevenue, "
                "TotalOperatingExpenses, Notes, CreatedDate, UpdatedDate) "
                "VALUES (?,?,?,?,?,?,?)",
                (self.selected_property_id, self.selected_year, rev, opex,
                 self.f_notes, now, now),
                db=self.db,
            )
            self.form_success = f"{self.selected_year} financials created."
        self._load_financials()


# ── UI helpers ────────────────────────────────────────────────────────────────

def metric_tile(label: str, value: rx.Var) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(value, size="6", weight="bold", color=BRAND_DARK),
            rx.text(label, size="1", color="#666"),
            spacing="1", align_items="start",
        ),
        style={
            "background": "#f4f6fa", "border_radius": "8px",
            "padding": "14px 18px", "flex": "1",
        },
    )


def year_row(y: FinancialYear) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(y.fiscal_year, size="2", weight="bold")),
        rx.table.cell(rx.text(y.total_revenue, size="2")),
        rx.table.cell(rx.text(y.total_opex, size="2")),
        rx.table.cell(rx.text(y.noi, size="2", weight="bold")),
        rx.table.cell(rx.text(y.noi_margin, size="2")),
        rx.table.cell(rx.text(y.estimated_value, size="2", color=BRAND_PRIMARY)),
        rx.table.cell(rx.text(y.price_per_sf, size="2", color="#555")),
        rx.table.cell(
            rx.button(
                "Select",
                size="1", variant="soft", color_scheme="blue",
                on_click=PropertyFinancialsState.set_selected_year(y.fiscal_year),
            )
        ),
        style=rx.cond(
            PropertyFinancialsState.selected_year == y.fiscal_year,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


# ── Page content ──────────────────────────────────────────────────────────────

def property_financials_content() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.heading("Property financials", size="5", color=BRAND_DARK),
                rx.spacer(),
                rx.cond(
                    PropertyFinancialsState.selected_property != "",
                    rx.link(
                        rx.button("⬇ Download PDF", variant="outline",
                                  color_scheme="blue", size="2"),
                        href=PropertyFinancialsState.pdf_download_url,
                        is_external=True,
                    ),
                    rx.fragment(),
                ),
                align="center", width="100%",
            ),

            # Controls row
            rx.hstack(
                rx.vstack(
                    rx.text("Property", size="1", color="#666"),
                    rx.cond(
                        PropertyFinancialsState.property_names.length() > 0,
                        rx.select(
                            PropertyFinancialsState.property_names,
                            value=PropertyFinancialsState.selected_property,
                            on_change=PropertyFinancialsState.set_selected_property,
                            size="2",
                        ),
                        rx.text("Loading...", size="2", color="#888"),
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Report mode", size="1", color="#666"),
                    rx.hstack(
                        rx.text(
                            "Single Year",
                            size="2", weight="bold",
                            color=rx.cond(PropertyFinancialsState.report_mode == "Single Year", "white", "#666"),
                            style={
                                "padding": "5px 14px", "border_radius": "999px", "cursor": "pointer",
                                "user_select": "none", "transition": "all 0.15s",
                                "background": rx.cond(
                                    PropertyFinancialsState.report_mode == "Single Year",
                                    BRAND_PRIMARY, "transparent",
                                ),
                            },
                            on_click=PropertyFinancialsState.set_report_mode("Single Year"),
                        ),
                        rx.text(
                            "Trend",
                            size="2", weight="bold",
                            color=rx.cond(PropertyFinancialsState.report_mode == "Trend", "white", "#666"),
                            style={
                                "padding": "5px 14px", "border_radius": "999px", "cursor": "pointer",
                                "user_select": "none", "transition": "all 0.15s",
                                "background": rx.cond(
                                    PropertyFinancialsState.report_mode == "Trend",
                                    BRAND_PRIMARY, "transparent",
                                ),
                            },
                            on_click=PropertyFinancialsState.set_report_mode("Trend"),
                        ),
                        spacing="0",
                        style={"background": "#e2e8f0", "border_radius": "999px",
                               "padding": "3px", "display": "inline-flex"},
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text(
                        "Cap rate: " + PropertyFinancialsState.cap_rate_display,
                        size="1", color="#666",
                    ),
                    rx.slider(
                        min=4.0, max=10.0, step=0.25,
                        value=[PropertyFinancialsState.cap_rate],
                        on_change=lambda v: PropertyFinancialsState.set_cap_rate(v[0]),
                        width="200px",
                    ),
                    spacing="1",
                ),
                spacing="6", align="end", wrap="wrap", width="100%",
            ),

            # Summary table
            rx.cond(
                PropertyFinancialsState.displayed_years.length() > 0,
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Year"),
                                rx.table.column_header_cell("Revenue"),
                                rx.table.column_header_cell("Operating Exp"),
                                rx.table.column_header_cell("NOI"),
                                rx.table.column_header_cell("NOI Margin"),
                                rx.table.column_header_cell("Est. Value"),
                                rx.table.column_header_cell("Price/SF"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(PropertyFinancialsState.displayed_years, year_row)),
                        width="100%", variant="surface",
                    ),
                    width="100%", overflow_x="auto",
                ),
                rx.text("No data yet — add a year below.", color="#888", size="2"),
            ),

            # Add year
            rx.hstack(
                rx.input(
                    value=PropertyFinancialsState.new_year_input,
                    on_change=PropertyFinancialsState.set_new_year_input,
                    placeholder="e.g. 2027",
                    type="number",
                    size="2",
                    width="120px",
                ),
                rx.button(
                    "+ Add year",
                    on_click=PropertyFinancialsState.add_year,
                    variant="outline",
                    color_scheme="blue",
                    size="2",
                ),
                align="center",
                spacing="2",
            ),

            # Selected year entry form
            rx.divider(),
            rx.text(
                "Year entry — " + PropertyFinancialsState.selected_year.to_string(),
                size="3", weight="bold", color=BRAND_DARK,
            ),
            rx.grid(
                rx.vstack(
                    rx.text("Total revenue ($)", size="1", color="#666"),
                    rx.input(
                        value=PropertyFinancialsState.f_revenue,
                        on_change=PropertyFinancialsState.set_f_revenue,
                        placeholder="0", type="number", size="2", width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Total operating expenses ($)", size="1", color="#666"),
                    rx.input(
                        value=PropertyFinancialsState.f_opex,
                        on_change=PropertyFinancialsState.set_f_opex,
                        placeholder="0", type="number", size="2", width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                columns="2", spacing="4", width="100%",
            ),
            rx.vstack(
                rx.text("Notes", size="1", color="#666"),
                rx.text_area(
                    value=PropertyFinancialsState.f_notes,
                    on_change=PropertyFinancialsState.set_f_notes,
                    placeholder="Projections, assumptions, context...",
                    width="100%", rows="3",
                ),
                spacing="1", width="100%",
            ),

            # NOI + Valuation tiles
            rx.hstack(
                metric_tile("NOI", PropertyFinancialsState.noi_preview),
                metric_tile("NOI Margin", PropertyFinancialsState.noi_margin_preview),
                rx.cond(
                    PropertyFinancialsState.report_mode == "Single Year",
                    rx.fragment(
                        metric_tile("Estimated value", PropertyFinancialsState.estimated_value_preview),
                        metric_tile("Price per SF", PropertyFinancialsState.price_per_sf_preview),
                    ),
                    rx.fragment(),
                ),
                spacing="4", width="100%",
            ),

            rx.cond(
                PropertyFinancialsState.form_error != "",
                rx.callout(PropertyFinancialsState.form_error, color="red", variant="soft"),
                rx.fragment(),
            ),
            rx.cond(
                PropertyFinancialsState.form_success != "",
                rx.callout(PropertyFinancialsState.form_success, color="green", variant="soft"),
                rx.fragment(),
            ),
            rx.button(
                "Save year",
                on_click=PropertyFinancialsState.save_financials,
                color_scheme="blue", size="2",
            ),

            rx.text(
                "Tax basis shows Owner Occupied suites at $0. "
                "Estimated value = NOI ÷ cap rate.",
                size="1", color="#888",
            ),

            spacing="5", width="100%", align_items="start", padding="24px",
        ),
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
    )


def property_financials_page() -> rx.Component:
    return page_shell(property_financials_content(), current_path="/property-financials")
