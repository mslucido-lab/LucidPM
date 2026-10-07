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
    api_base_url,
    AppState, run_query,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM.components.sidebar import page_shell
from LucidPM.lease_suites import build_rent_roll

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
        """Populate presentation state from the shared Rent Roll builder."""
        try:
            as_of = datetime.datetime.strptime(self.as_of_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            as_of = datetime.date.today()
        result = build_rent_roll(as_of, self.property_filter, self.basis, self.db)
        self.rows = [RentRollRow(**row) for row in result["rows"]]
        self.total_rentable_sqft = f"{result['total_rentable']:,.0f}"
        self.total_occupied_sqft = f"{result['total_occupied']:,.0f}"
        self.vacancy_rate = f"{result['vacancy_rate']:.1%}"
        avg_psf = result["avg_annual_psf"]
        self.avg_annual_psf = f"${avg_psf:,.2f}/sf" if avg_psf is not None else "—"

    @rx.var
    def pdf_download_url(self) -> str:
        """Builds the PDF endpoint URL pointing to the Reflex backend (see state.api_base_url)."""
        params = f"?as_of={self.as_of_date}&property={self.property_filter}&basis={self.basis}&db={self.db}"
        return f"{api_base_url()}/api/rent-roll-pdf" + params


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
