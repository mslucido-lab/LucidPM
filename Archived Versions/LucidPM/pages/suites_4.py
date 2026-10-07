"""
Manage Suites page — list + inline form.
"""

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell

SUITE_USE_TYPES = ["Standard", "Owner Occupied"]


# ── Data model ────────────────────────────────────────────────────────────────

class SuiteSummary(rx.Base):
    suite_id: int = 0
    suite_label: str = ""
    property_name: str = ""
    sq_ft: str = ""
    use_type: str = ""
    underwriting_rent: str = ""
    sort_order: int = 0
    active: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class SuiteState(AppState):

    # List + filters
    suite_list: list[SuiteSummary] = []
    property_filter: str = "All"
    active_filter: str = "All"
    property_filter_options: list[str] = ["All"]

    # Property lookup (name → id)
    property_names: list[str] = []
    property_ids: list[int] = []

    # Selected / form mode
    selected_suite_id: int = 0
    suite_mode: str = "new"   # "new" | "edit"

    # Form fields
    f_property: str = ""
    f_label: str = ""
    f_sq_ft: str = ""
    f_use_type: str = "Standard"
    f_underwriting_rent: str = ""
    f_sort_order: str = "0"
    f_active: bool = True
    f_notes: str = ""

    form_error: str = ""
    form_success: str = ""
    use_type_options: list[str] = SUITE_USE_TYPES

    @rx.var
    def editing_banner_text(self) -> str:
        return f"Editing: {self.f_label} — {self.f_property}"

    def on_load(self):
        self._load_property_options()
        self.load_suite_list()
        self.new_suite()

    def _load_property_options(self):
        rows = run_query(
            "SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_names = [str(r["PropertyName"]) for r in rows]
        self.property_ids   = [int(r["PropertyID"]) for r in rows]
        self.property_filter_options = ["All"] + self.property_names
        if self.property_names:
            self.f_property = self.property_names[0]

    def load_suite_list(self):
        conditions = []
        params = []
        if self.property_filter != "All":
            conditions.append("p.PropertyName = ?")
            params.append(self.property_filter)
        if self.active_filter == "Yes":
            conditions.append("ps.IsActive = 1")
        elif self.active_filter == "No":
            conditions.append("ps.IsActive = 0")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = run_query(
            "SELECT ps.SuiteID, ps.SuiteLabel, p.PropertyName, "
            "ps.SquareFeet, ps.SuiteUseType, ps.UnderwritingRent, "
            "ps.SortOrder, ps.IsActive "
            "FROM PropertySuites ps "
            "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
            f"{where} ORDER BY p.PropertyName, ps.SortOrder, ps.SuiteLabel",
            tuple(params), db=self.db,
        )
        def fmt_money(v) -> str:
            try:
                return f"${float(v):,.0f}" if v is not None else ""
            except (TypeError, ValueError):
                return ""

        def fmt_sqft(v) -> str:
            try:
                return f"{float(v):,.0f}" if v is not None else ""
            except (TypeError, ValueError):
                return ""

        self.suite_list = [
            SuiteSummary(
                suite_id=int(r["SuiteID"]),
                suite_label=str(r.get("SuiteLabel") or ""),
                property_name=str(r.get("PropertyName") or ""),
                sq_ft=fmt_sqft(r.get("SquareFeet")),
                use_type=str(r.get("SuiteUseType") or "Standard"),
                underwriting_rent=fmt_money(r.get("UnderwritingRent")),
                sort_order=int(r.get("SortOrder") or 0),
                active="Yes" if r.get("IsActive") else "No",
            )
            for r in rows
        ]

    def set_property_filter(self, v: str):
        self.property_filter = v
        self.load_suite_list()

    def set_active_filter(self, v: str):
        self.active_filter = v
        self.load_suite_list()

    def select_suite(self, suite_id: int):
        self.selected_suite_id = suite_id
        self.suite_mode = "edit"
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT ps.SuiteLabel, p.PropertyName, ps.SquareFeet, ps.SuiteUseType, "
            "ps.UnderwritingRent, ps.SortOrder, ps.IsActive, ps.Notes "
            "FROM PropertySuites ps "
            "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
            "WHERE ps.SuiteID = ?",
            (suite_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.f_label    = str(r.get("SuiteLabel") or "")
        self.f_property = str(r.get("PropertyName") or (self.property_names[0] if self.property_names else ""))
        sq = r.get("SquareFeet")
        self.f_sq_ft    = str(int(float(sq))) if sq is not None else ""
        self.f_use_type = str(r.get("SuiteUseType") or "Standard")
        ur = r.get("UnderwritingRent")
        self.f_underwriting_rent = str(int(float(ur))) if ur is not None else ""
        self.f_sort_order = str(int(r.get("SortOrder") or 0))
        self.f_active   = bool(r.get("IsActive"))
        self.f_notes    = str(r.get("Notes") or "")

    def new_suite(self):
        self.selected_suite_id = 0
        self.suite_mode = "new"
        self.form_error = ""
        self.form_success = ""
        self.f_label = self.f_sq_ft = self.f_underwriting_rent = self.f_notes = ""
        self.f_property = self.property_names[0] if self.property_names else ""
        self.f_use_type = "Standard"
        self.f_sort_order = "0"
        self.f_active = True

    def save_suite(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_label.strip():
            self.form_error = "Suite label is required."
            return
        if not self.f_property or self.f_property not in self.property_names:
            self.form_error = "Property is required."
            return
        prop_id = self.property_ids[self.property_names.index(self.f_property)]

        try:
            sq_ft = float(self.f_sq_ft) if self.f_sq_ft.strip() else None
        except ValueError:
            sq_ft = None
        try:
            ur = float(self.f_underwriting_rent) if self.f_underwriting_rent.strip() else None
        except ValueError:
            ur = None
        try:
            sort_order = int(self.f_sort_order) if self.f_sort_order.strip() else 0
        except ValueError:
            sort_order = 0

        import datetime
        now = datetime.datetime.now()

        if self.suite_mode == "edit":
            run_exec(
                "UPDATE PropertySuites SET PropertyID=?, SuiteLabel=?, SquareFeet=?, "
                "SuiteUseType=?, UnderwritingRent=?, SortOrder=?, IsActive=?, Notes=?, UpdatedDate=? "
                "WHERE SuiteID=?",
                (prop_id, self.f_label.strip(), sq_ft, self.f_use_type,
                 ur, sort_order, self.f_active, self.f_notes, now,
                 self.selected_suite_id),
                db=self.db,
            )
            # Keep denormalized Suite text on Tenants in sync
            run_exec("UPDATE Tenants SET Suite=? WHERE SuiteID=?",
                     (self.f_label.strip(), self.selected_suite_id), db=self.db)
            self.form_success = "Suite saved."
        else:
            run_exec(
                "INSERT INTO PropertySuites (PropertyID, SuiteLabel, SquareFeet, SuiteUseType, "
                "UnderwritingRent, SortOrder, IsActive, Notes, CreatedDate, UpdatedDate) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (prop_id, self.f_label.strip(), sq_ft, self.f_use_type,
                 ur, sort_order, self.f_active, self.f_notes, now, now),
                db=self.db,
            )
            self.form_success = "Suite created."
            self.new_suite()
        self.load_suite_list()

    # Setters
    def set_f_property(self, v): self.f_property = v
    def set_f_label(self, v): self.f_label = v
    def set_f_sq_ft(self, v): self.f_sq_ft = v
    def set_f_use_type(self, v): self.f_use_type = v
    def set_f_underwriting_rent(self, v): self.f_underwriting_rent = v
    def set_f_sort_order(self, v): self.f_sort_order = v
    def set_f_active(self, v): self.f_active = v
    def set_f_notes(self, v): self.f_notes = v


# ── UI helpers ────────────────────────────────────────────────────────────────

def edit_banner(text: rx.Var) -> rx.Component:
    return rx.box(
        rx.text("✏️ " + text, size="2", weight="bold", color=BRAND_DARK),
        style={
            "background": "#f0f4ff", "border": "1px solid #c5d0f0",
            "border_left": f"4px solid {BRAND_PRIMARY}",
            "border_radius": "6px", "padding": "8px 14px", "width": "100%",
        },
    )


# ── List table ────────────────────────────────────────────────────────────────

def suite_row(s: SuiteSummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(s.property_name, size="2", color="#555")),
        rx.table.cell(rx.text(s.suite_label, size="2", weight="bold")),
        rx.table.cell(rx.text(s.sq_ft, size="2", color="#555")),
        rx.table.cell(rx.text(s.use_type, size="2", color="#555")),
        rx.table.cell(rx.text(s.underwriting_rent, size="2", color="#555")),
        rx.table.cell(
            rx.cond(
                s.active == "Yes",
                rx.badge("Active", color_scheme="green", variant="soft"),
                rx.badge("Inactive", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=SuiteState.select_suite(s.suite_id))
        ),
        style=rx.cond(
            SuiteState.selected_suite_id == s.suite_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


# ── Form ─────────────────────────────────────────────────────────────────────

def suite_form() -> rx.Component:
    return rx.vstack(
        rx.divider(),
        rx.cond(
            SuiteState.suite_mode == "edit",
            edit_banner(SuiteState.editing_banner_text),
            rx.text("New suite", size="3", weight="bold", color=BRAND_DARK),
        ),
        # Row 1: property, suite label, use type
        rx.grid(
            rx.vstack(
                rx.text("Property *", size="1", color="#666"),
                rx.select(SuiteState.property_filter_options[1:],  # exclude "All"
                          value=SuiteState.f_property,
                          on_change=SuiteState.set_f_property, size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Suite label *", size="1", color="#666"),
                rx.input(value=SuiteState.f_label, on_change=SuiteState.set_f_label,
                         placeholder="e.g. 101, Suite A", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Use type", size="1", color="#666"),
                rx.select(SuiteState.use_type_options, value=SuiteState.f_use_type,
                          on_change=SuiteState.set_f_use_type, size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="3", spacing="4", width="100%",
        ),
        # Row 2: sq ft, underwriting rent, sort order
        rx.grid(
            rx.vstack(
                rx.text("Square feet", size="1", color="#666"),
                rx.input(value=SuiteState.f_sq_ft, on_change=SuiteState.set_f_sq_ft,
                         placeholder="e.g. 1200", type="number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Underwriting rent", size="1", color="#666"),
                rx.input(value=SuiteState.f_underwriting_rent,
                         on_change=SuiteState.set_f_underwriting_rent,
                         placeholder="Monthly $", type="number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Sort order", size="1", color="#666"),
                rx.input(value=SuiteState.f_sort_order, on_change=SuiteState.set_f_sort_order,
                         placeholder="0", type="number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="3", spacing="4", width="100%",
        ),
        # Notes
        rx.vstack(
            rx.text("Notes", size="1", color="#666"),
            rx.text_area(value=SuiteState.f_notes, on_change=SuiteState.set_f_notes,
                         placeholder="Additional notes...", width="100%", rows="3"),
            spacing="1", width="100%",
        ),
        # Active toggle
        rx.hstack(
            rx.switch(checked=SuiteState.f_active, on_change=SuiteState.set_f_active),
            rx.vstack(
                rx.text("Active", size="2", weight="bold"),
                rx.text("Inactive suites won't appear in tenant or lease dropdowns", size="1", color="#666"),
                spacing="0",
            ),
            align="center", spacing="3",
        ),
        rx.cond(SuiteState.form_error != "",
                rx.callout(SuiteState.form_error, color="red", variant="soft"),
                rx.fragment()),
        rx.cond(SuiteState.form_success != "",
                rx.callout(SuiteState.form_success, color="green", variant="soft"),
                rx.fragment()),
        rx.hstack(
            rx.button(
                rx.cond(SuiteState.suite_mode == "edit", "Save suite", "Create suite"),
                on_click=SuiteState.save_suite, color_scheme="blue", size="2",
            ),
            rx.button("Cancel", on_click=SuiteState.new_suite, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Page content ──────────────────────────────────────────────────────────────

SUITES_RESIZER_SCRIPT = """
(function() {
    function initResizer() {
        var resizer = document.getElementById('suites-panel-resizer');
        var leftPanel = document.getElementById('suites-list-panel');
        if (!resizer || !leftPanel) { setTimeout(initResizer, 300); return; }
        var isResizing = false, startX = 0, startWidth = 0;
        resizer.addEventListener('mousedown', function(e) {
            isResizing = true; startX = e.clientX; startWidth = leftPanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none'; e.preventDefault();
        });
        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            var newWidth = Math.min(Math.max(startWidth + (e.clientX - startX), 260), 900);
            leftPanel.style.width = newWidth + 'px'; leftPanel.style.minWidth = newWidth + 'px';
        });
        document.addEventListener('mouseup', function() {
            if (isResizing) { isResizing = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; }
        });
    }
    initResizer();
})();
"""


# ── Page content ──────────────────────────────────────────────────────────────

def suites_content() -> rx.Component:
    return rx.box(
        rx.script(SUITES_RESIZER_SCRIPT),
        # Page heading + new button
        rx.hstack(
            rx.heading("Manage suites", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.button("+ New suite", on_click=SuiteState.new_suite,
                      variant="outline", color_scheme="blue", size="2"),
            align="center", width="100%",
            padding_bottom="12px",
        ),
        # Split panel
        rx.hstack(
            # Left: filters + list
            rx.box(
                rx.hstack(
                    rx.select(
                        SuiteState.property_filter_options,
                        value=SuiteState.property_filter,
                        on_change=SuiteState.set_property_filter,
                        size="1",
                    ),
                    rx.select(
                        ["All", "Yes", "No"],
                        value=SuiteState.active_filter,
                        on_change=SuiteState.set_active_filter,
                        size="1",
                    ),
                    spacing="2",
                    padding_bottom="12px",
                ),
                rx.cond(
                    SuiteState.suite_list.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Property"),
                                rx.table.column_header_cell("Suite"),
                                rx.table.column_header_cell("Sq ft"),
                                rx.table.column_header_cell("Use type"),
                                rx.table.column_header_cell("Underwriting rent"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(SuiteState.suite_list, suite_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No suites found.", color="#888", size="2"),
                ),
                id="suites-list-panel",
                style={
                    "width": "660px",
                    "min_width": "660px",
                    "max_height": "calc(100vh - 120px)",
                    "overflow_y": "auto",
                    "background": "white",
                    "border": "1px solid #dde3f0",
                    "border_radius": "12px",
                    "padding": "20px",
                    "flex_shrink": "0",
                },
            ),
            # Drag handle
            rx.box(
                rx.box(style={"width": "4px", "height": "40px", "background": "#c5d0f0", "border_radius": "2px"}),
                id="suites-panel-resizer",
                style={
                    "width": "12px", "min_width": "12px", "cursor": "col-resize",
                    "display": "flex", "align_items": "center", "justify_content": "center",
                    "align_self": "stretch", "flex_shrink": "0",
                    "_hover": {"background": "#f0f4ff"},
                    "border_radius": "4px", "transition": "background 0.15s",
                },
            ),
            # Right: form
            rx.box(
                suite_form(),
                style={
                    "flex": "1",
                    "min_width": "0",
                    "max_height": "calc(100vh - 120px)",
                    "overflow_y": "auto",
                    "background": "white",
                    "border": "1px solid #dde3f0",
                    "border_radius": "12px",
                    "padding": "20px",
                },
            ),
            spacing="0",
            width="100%",
            align_items="start",
        ),
        padding="24px",
        width="100%",
    )


def suites_page() -> rx.Component:
    return page_shell(suites_content(), current_path="/admin/suites")
