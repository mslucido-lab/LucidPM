"""
Dashboard page — summary metrics with property filter and basis toggle.

Controls:
  - Basis toggle (Tax / Bank) — affects rent roll occupancy calculation
  - Property checkboxes — filters ALL metrics to selected properties
    Loads property names from DB; defaults to all selected
"""

import reflex as rx
import datetime

from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY


# ── State ─────────────────────────────────────────────────────────────────────

class DashboardState(AppState):

    # Controls
    basis: str = "Tax"
    property_options: list[str] = []
    selected_properties: list[str] = []

    # Rent roll summary
    dash_occupancy_pct: str = "—"
    dash_monthly_rent: str = "—"
    dash_vacant_count: str = "—"
    dash_occupied_count: str = "—"
    dash_as_of: str = ""

    # Operational metrics
    dash_active_tenants: str = "—"
    dash_open_work_items: str = "—"
    dash_leases_expiring_90d: str = "—"
    dash_overdue_followups: str = "—"

    @rx.var
    def all_selected(self) -> bool:
        return len(self.selected_properties) == len(self.property_options) and len(self.property_options) > 0

    @rx.var
    def filter_subtitle(self) -> str:
        if self.all_selected or not self.selected_properties:
            return f"As of {self.dash_as_of} · All properties · {self.basis} basis"
        if len(self.selected_properties) == 1:
            return f"As of {self.dash_as_of} · {self.selected_properties[0]} · {self.basis} basis"
        return f"As of {self.dash_as_of} · {len(self.selected_properties)} properties · {self.basis} basis"

    def on_load(self):
        self.dash_as_of = datetime.date.today().strftime("%m/%d/%Y")
        self._load_properties()
        self._refresh_all()

    def _load_properties(self):
        rows = run_query("SELECT PropertyName FROM Properties ORDER BY PropertyName", db=self.db)
        names = [str(r["PropertyName"]) for r in rows]
        self.property_options = names
        self.selected_properties = names.copy()

    def _property_filter_sql(self, alias: str = "p") -> tuple:
        if not self.selected_properties or self.all_selected:
            return "", []
        placeholders = ", ".join(["?" for _ in self.selected_properties])
        return f"AND {alias}.PropertyName IN ({placeholders})", list(self.selected_properties)

    def set_basis(self, v: str):
        self.basis = v
        self._refresh_all()

    def toggle_all_properties(self, checked: bool):
        self.selected_properties = self.property_options.copy() if checked else []
        self._refresh_all()

    def toggle_property(self, name: str, checked: bool):
        if checked:
            if name not in self.selected_properties:
                self.selected_properties = self.selected_properties + [name]
        else:
            self.selected_properties = [p for p in self.selected_properties if p != name]
        self._refresh_all()

    def _refresh_all(self):
        self._load_rent_roll_summary()
        self._load_operational_metrics()

    def _load_rent_roll_summary(self):
        today = datetime.date.today()
        prop_clause, prop_params = self._property_filter_sql("p")

        # Load active suites
        suites = run_query(
            "SELECT ps.SuiteID, ps.PropertyID, ps.SuiteLabel, "
            "ps.SuiteUseType, ps.UnderwritingRent "
            "FROM PropertySuites ps "
            "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
            f"WHERE ps.IsActive = 1 {prop_clause}",
            tuple(prop_params), db=self.db,
        )

        # Load active leases with tenant and suite info
        leases = run_query(
            "SELECT l.LeaseID, l.SuiteID AS LeaseSuiteID, l.PropertyID, "
            "l.RentAmount, ts.TenantStatusName, "
            "t.SuiteID AS TenantSuiteID, t.Suite AS TenantSuite, "
            "ltt.LeaseTermTypeName "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            f"WHERE (l.LeaseStart <= ? AND (l.LeaseEnd IS NULL OR l.LeaseEnd >= ?)) "
            f"AND ISNULL(ts.TenantStatusName, '') != 'Default' {prop_clause}",
            tuple([today, today] + prop_params), db=self.db,
        )

        # Holdover leases — expired fixed-term but tenant still Active
        fixed_term_types = {"fixed term", "option term", "multi-year", "multi year"}
        holdover_leases = run_query(
            "SELECT l.LeaseID, l.SuiteID AS LeaseSuiteID, l.PropertyID, "
            "l.RentAmount, t.SuiteID AS TenantSuiteID, t.Suite AS TenantSuite, "
            "ltt.LeaseTermTypeName "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            f"WHERE l.LeaseEnd < ? AND l.LeaseEnd IS NOT NULL "
            f"AND ts.TenantStatusName = 'Active' "
            f"AND ISNULL(t.Suite, '') != '' {prop_clause}",
            tuple([today] + prop_params), db=self.db,
        )
        holdover_leases = [
            l for l in holdover_leases
            if str(l.get("LeaseTermTypeName") or "").strip().lower() in fixed_term_types
        ]

        def find_lease(suite_id: int, prop_id: int, suite_label: str, pool: list):
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

        occupied = 0
        vacant = 0
        monthly_rent = 0.0

        for s in suites:
            sid       = int(s["SuiteID"])
            prop_id   = int(s["PropertyID"])
            label     = str(s.get("SuiteLabel") or "").strip()
            use_type  = str(s.get("SuiteUseType") or "Standard").strip()
            under_rent = s.get("UnderwritingRent")

            active_match   = find_lease(sid, prop_id, label, leases)
            holdover_match = find_lease(sid, prop_id, label, holdover_leases) if active_match is None else None

            if active_match is not None:
                occupied += 1
                try:
                    monthly_rent += float(active_match.get("RentAmount") or 0)
                except (TypeError, ValueError):
                    pass
            elif holdover_match is not None:
                occupied += 1
                try:
                    monthly_rent += float(holdover_match.get("RentAmount") or 0)
                except (TypeError, ValueError):
                    pass
            else:
                # Bank basis: Owner Occupied counts as occupied
                if self.basis == "Bank" and use_type == "Owner Occupied":
                    occupied += 1
                    try:
                        monthly_rent += float(under_rent or 0)
                    except (TypeError, ValueError):
                        pass
                else:
                    vacant += 1

        total_suites = len(suites)
        occ_pct = (occupied / total_suites * 100) if total_suites > 0 else 0.0

        self.dash_occupied_count = str(occupied)
        self.dash_vacant_count = str(vacant)
        self.dash_occupancy_pct = f"{occ_pct:.0f}%"
        self.dash_monthly_rent = f"${monthly_rent:,.0f}"

    def _load_operational_metrics(self):
        today = datetime.date.today()
        ninety_days = today + datetime.timedelta(days=90)
        prop_clause, prop_params = self._property_filter_sql("p")

        rows = run_query(
            "SELECT COUNT(*) AS n FROM Tenants t "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            f"WHERE ts.TenantStatusName = 'Active' {prop_clause}",
            tuple(prop_params), db=self.db,
        )
        self.dash_active_tenants = str(rows[0]["n"]) if rows else "—"

        rows = run_query(
            "SELECT COUNT(*) AS n FROM WorkItems w "
            "LEFT JOIN WorkItemStatuses ws ON w.StatusID = ws.WorkItemStatusID "
            "LEFT JOIN Properties p ON w.PropertyID = p.PropertyID "
            f"WHERE ISNULL(ws.StatusName, w.Status) NOT IN ('Completed','Canceled') {prop_clause}",
            tuple(prop_params), db=self.db,
        )
        self.dash_open_work_items = str(rows[0]["n"]) if rows else "—"

        rows = run_query(
            "SELECT COUNT(*) AS n FROM Leases l "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            f"WHERE l.LeaseEnd >= ? AND l.LeaseEnd <= ? {prop_clause}",
            tuple([today, ninety_days] + prop_params), db=self.db,
        )
        self.dash_leases_expiring_90d = str(rows[0]["n"]) if rows else "—"

        rows = run_query(
            "SELECT COUNT(*) AS n FROM Communications c "
            "LEFT JOIN Tenants t ON c.TenantID = t.TenantID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            f"WHERE c.NextActionDate < ? AND c.NextActionDate IS NOT NULL {prop_clause}",
            tuple([today] + prop_params), db=self.db,
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


def _property_checkbox(name: str) -> rx.Component:
    return rx.hstack(
        rx.checkbox(
            checked=DashboardState.selected_properties.contains(name),
            on_change=lambda v: DashboardState.toggle_property(name, v),
        ),
        rx.text(name, size="2"),
        align="center",
        spacing="2",
        style={"cursor": "pointer"},
    )


def _control_bar() -> rx.Component:
    return rx.box(
        rx.hstack(
            # Basis toggle — sliding pill
            rx.vstack(
                rx.text("Basis", size="1", color="#888", weight="bold",
                        style={"text_transform": "uppercase", "letter_spacing": "0.05em"}),
                rx.box(
                    rx.hstack(
                        rx.text(
                            "Tax",
                            size="2", weight="bold",
                            color=rx.cond(DashboardState.basis == "Tax", "white", "#666"),
                            style={
                                "padding": "5px 20px",
                                "border_radius": "999px",
                                "background": rx.cond(
                                    DashboardState.basis == "Tax",
                                    BRAND_PRIMARY,
                                    "transparent",
                                ),
                                "cursor": "pointer",
                                "transition": "background 0.15s ease, color 0.15s ease",
                                "user_select": "none",
                            },
                            on_click=DashboardState.set_basis("Tax"),
                        ),
                        rx.text(
                            "Bank",
                            size="2", weight="bold",
                            color=rx.cond(DashboardState.basis == "Bank", "white", "#666"),
                            style={
                                "padding": "5px 20px",
                                "border_radius": "999px",
                                "background": rx.cond(
                                    DashboardState.basis == "Bank",
                                    BRAND_PRIMARY,
                                    "transparent",
                                ),
                                "cursor": "pointer",
                                "transition": "background 0.15s ease, color 0.15s ease",
                                "user_select": "none",
                            },
                            on_click=DashboardState.set_basis("Bank"),
                        ),
                        spacing="0",
                    ),
                    style={
                        "background": "#e2e8f0",
                        "border_radius": "999px",
                        "padding": "3px",
                        "display": "inline-flex",
                        "box_shadow": "inset 0 1px 2px rgba(0,0,0,0.08)",
                    },
                ),
                spacing="1",
                align_items="start",
            ),

            rx.separator(orientation="vertical", style={"height": "44px"}),

            # Property checkboxes
            rx.vstack(
                rx.text("Properties", size="1", color="#888", weight="bold",
                        style={"text_transform": "uppercase", "letter_spacing": "0.05em"}),
                rx.hstack(
                    rx.hstack(
                        rx.checkbox(
                            checked=DashboardState.all_selected,
                            on_change=DashboardState.toggle_all_properties,
                        ),
                        rx.text("All", size="2", weight="bold"),
                        align="center", spacing="2",
                        style={"cursor": "pointer"},
                    ),
                    rx.foreach(DashboardState.property_options, _property_checkbox),
                    spacing="4",
                    align="center",
                    wrap="wrap",
                ),
                spacing="1",
                align_items="start",
            ),

            spacing="5",
            align="center",
            width="100%",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_radius": "10px",
            "padding": "14px 20px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.04)",
        },
    )


def _rent_roll_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Rent roll", size="4", weight="bold", color=BRAND_DARK),
                    rx.text(DashboardState.filter_subtitle, size="1", color="#888"),
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


# ── Page ──────────────────────────────────────────────────────────────────────

def dashboard_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Dashboard", size="7", color=BRAND_DARK),
        _control_bar(),
        _rent_roll_card(),
        rx.grid(
            _metric_card("Active tenants", DashboardState.dash_active_tenants, "👥"),
            _metric_card("Open work items", DashboardState.dash_open_work_items, "🛠"),
            _metric_card("Leases expiring (90d)", DashboardState.dash_leases_expiring_90d, "📄"),
            _metric_card("Overdue follow-ups", DashboardState.dash_overdue_followups, "⏰"),
            columns="4",
            spacing="4",
            width="100%",
        ),
        spacing="5",
        width="100%",
        max_width="1200px",
        align_items="start",
        padding="24px",
    )


def dashboard_page() -> rx.Component:
    return page_shell(dashboard_content(), current_path="/")
