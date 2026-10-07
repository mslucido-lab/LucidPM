"""
Dashboard page — summary metrics with rent roll card linking to /rent-roll.
"""

import reflex as rx
import datetime

from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY


# ── State ─────────────────────────────────────────────────────────────────────

class DashboardState(AppState):

    # Rent roll summary (today's snapshot, all properties, Tax basis)
    dash_occupancy_pct: str = "—"
    dash_monthly_rent: str = "—"
    dash_vacant_count: str = "—"
    dash_occupied_count: str = "—"
    dash_as_of: str = ""

    # Other metrics
    dash_active_tenants: str = "—"
    dash_open_work_items: str = "—"
    dash_leases_expiring_90d: str = "—"
    dash_overdue_followups: str = "—"

    def on_load(self):
        self.dash_as_of = datetime.date.today().strftime("%m/%d/%Y")
        self._load_rent_roll_summary()
        self._load_operational_metrics()

    def _load_rent_roll_summary(self):
        today = datetime.date.today()

        # Get all active leases as of today
        leases = run_query(
            "SELECT l.LeaseID, l.SuiteID, l.RentAmount, t.TenantStatusName "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "WHERE (l.LeaseStart <= ? AND (l.LeaseEnd IS NULL OR l.LeaseEnd >= ?)) "
            "AND ts.TenantStatusName != 'Default'",
            (today, today), db=self.db,
        )

        # Count active suites
        suites = run_query(
            "SELECT COUNT(*) AS total FROM PropertySuites WHERE IsActive = 1",
            db=self.db,
        )
        total_suites = int(suites[0]["total"]) if suites else 0

        occupied = len(leases)
        vacant = max(0, total_suites - occupied)
        occ_pct = (occupied / total_suites * 100) if total_suites > 0 else 0.0

        try:
            monthly_rent = sum(float(l.get("RentAmount") or 0) for l in leases)
        except (TypeError, ValueError):
            monthly_rent = 0.0

        self.dash_occupied_count = str(occupied)
        self.dash_vacant_count = str(vacant)
        self.dash_occupancy_pct = f"{occ_pct:.0f}%"
        self.dash_monthly_rent = f"${monthly_rent:,.0f}"

    def _load_operational_metrics(self):
        today = datetime.date.today()
        ninety_days = today + datetime.timedelta(days=90)

        # Active tenants
        rows = run_query(
            "SELECT COUNT(*) AS n FROM Tenants t "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "WHERE ts.TenantStatusName = 'Active'",
            db=self.db,
        )
        self.dash_active_tenants = str(rows[0]["n"]) if rows else "—"

        # Open work items
        rows = run_query(
            "SELECT COUNT(*) AS n FROM WorkItems w "
            "LEFT JOIN WorkItemStatuses ws ON w.StatusID = ws.WorkItemStatusID "
            "WHERE ISNULL(ws.StatusName, w.Status) NOT IN ('Completed','Canceled')",
            db=self.db,
        )
        self.dash_open_work_items = str(rows[0]["n"]) if rows else "—"

        # Leases expiring in 90 days
        rows = run_query(
            "SELECT COUNT(*) AS n FROM Leases "
            "WHERE LeaseEnd >= ? AND LeaseEnd <= ?",
            (today, ninety_days), db=self.db,
        )
        self.dash_leases_expiring_90d = str(rows[0]["n"]) if rows else "—"

        # Overdue follow-ups
        rows = run_query(
            "SELECT COUNT(*) AS n FROM Communications "
            "WHERE NextActionDate < ? AND NextActionDate IS NOT NULL",
            (today,), db=self.db,
        )
        self.dash_overdue_followups = str(rows[0]["n"]) if rows else "—"


# ── UI helpers ────────────────────────────────────────────────────────────────

def _metric_card(label: str, value: rx.Var, icon: str) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(icon, size="6"),
            rx.text(value, size="8", weight="bold", color=BRAND_DARK),
            rx.text(label, size="2", color="#666"),
            spacing="1",
            align_items="start",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_radius": "12px",
            "padding": "20px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
        },
    )


def _rent_roll_card() -> rx.Component:
    """Summary card — shows today's occupancy snapshot, links to full rent roll."""
    return rx.box(
        rx.vstack(
            # Card header
            rx.hstack(
                rx.vstack(
                    rx.text("Rent roll", size="4", weight="bold", color=BRAND_DARK),
                    rx.text(
                        "As of " + DashboardState.dash_as_of + " · All properties · Tax basis",
                        size="1", color="#888",
                    ),
                    spacing="0",
                    align_items="start",
                ),
                rx.spacer(),
                rx.link(
                    rx.button("View full rent roll →",
                              variant="outline", color_scheme="blue", size="2"),
                    href="/rent-roll",
                ),
                align="center", width="100%",
            ),
            rx.divider(),
            # Four stat tiles inside the card
            rx.hstack(
                _rent_roll_stat("Occupancy", DashboardState.dash_occupancy_pct),
                _rent_roll_stat("Occupied suites", DashboardState.dash_occupied_count),
                _rent_roll_stat("Vacant suites", DashboardState.dash_vacant_count),
                _rent_roll_stat("Monthly rent", DashboardState.dash_monthly_rent),
                spacing="4",
                width="100%",
            ),
            spacing="4",
            width="100%",
            align_items="start",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}",
            "border_radius": "12px",
            "padding": "20px 24px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
            "width": "100%",
        },
    )


def _rent_roll_stat(label: str, value: rx.Var) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(value, size="6", weight="bold", color=BRAND_DARK),
            rx.text(label, size="1", color="#666"),
            spacing="1",
            align_items="start",
        ),
        style={
            "background": "#f4f6fa",
            "border_radius": "8px",
            "padding": "14px 18px",
            "flex": "1",
        },
    )


# ── Page ──────────────────────────────────────────────────────────────────────

def dashboard_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Dashboard", size="7", color=BRAND_DARK),

        # Rent roll summary card — full width
        _rent_roll_card(),

        # Operational metric cards
        rx.grid(
            _metric_card("Active tenants", DashboardState.dash_active_tenants, "👥"),
            _metric_card("Open work items", DashboardState.dash_open_work_items, "🛠"),
            _metric_card("Leases expiring (90d)", DashboardState.dash_leases_expiring_90d, "📄"),
            _metric_card("Overdue follow-ups", DashboardState.dash_overdue_followups, "⏰"),
            columns="4",
            spacing="4",
            width="100%",
        ),

        spacing="6",
        width="100%",
        max_width="1200px",
        align_items="start",
        padding="24px",
    )


def dashboard_page() -> rx.Component:
    return page_shell(dashboard_content(), current_path="/")
