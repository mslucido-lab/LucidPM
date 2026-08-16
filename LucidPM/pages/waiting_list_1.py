"""
Waiting List page — prospect pipeline for available suites.

Layout:
  - Filter bar (search, property, status)
  - Prospect list (left panel)
  - Edit/Create form (right panel)

Full CRUD with same fields as Streamlit page_waiting_list().
"""

import reflex as rx
import datetime

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell

PROSPECT_STATUSES = ["Waiting", "Contacted", "Application Submitted", "Converted to Tenant", "Closed"]
PROSPECT_SOURCES  = ["Messenger", "Phone", "Text", "Website", "Referral", "Walk in", "Other"]

STATUS_COLORS = {
    "Waiting":                "blue",
    "Contacted":              "orange",
    "Application Submitted":  "purple",
    "Converted to Tenant":    "green",
    "Closed":                 "gray",
}


# ── Data model ────────────────────────────────────────────────────────────────

class ProspectRow(rx.Base):
    prospect_id: int = 0
    name: str = ""
    property_name: str = ""
    phone: str = ""
    email: str = ""
    desired_size: str = ""
    desired_move_in: str = ""
    source: str = ""
    status: str = ""
    last_contact: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class WaitingListState(AppState):

    # Filters
    search: str = ""
    property_filter: str = "All"
    status_filter: str = "All"
    property_options: list[str] = ["All"]

    # List
    prospects: list[ProspectRow] = []

    # Selected prospect
    selected_id: int = 0
    is_new: bool = False

    # Form fields
    f_name: str = ""
    f_property: str = ""
    f_phone: str = ""
    f_email: str = ""
    f_unit_type: str = ""
    f_desired_size: str = ""
    f_move_in_date: str = ""
    f_budget: str = ""
    f_source: str = ""
    f_status: str = "Waiting"
    f_last_contact: str = ""
    f_notes: str = ""
    f_converted_tenant_id: int = 0

    form_error: str = ""
    form_success: str = ""

    # Property lookup for form
    prop_names: list[str] = []
    prop_ids: list[int] = []

    @rx.var
    def form_title(self) -> str:
        return "Edit prospect" if self.selected_id > 0 and not self.is_new else "New prospect"

    @rx.var
    def filtered_prospects(self) -> list[ProspectRow]:
        results = []
        q = self.search.strip().lower()
        for p in self.prospects:
            if q and q not in p.name.lower() and q not in p.phone.lower() and q not in p.email.lower():
                continue
            if self.property_filter != "All" and p.property_name != self.property_filter:
                continue
            if self.status_filter != "All" and p.status != self.status_filter:
                continue
            results.append(p)
        return results

    def on_load(self):
        self._load_property_options()
        self._load_prospects()
        self.f_move_in_date = datetime.date.today().strftime("%Y-%m-%d")
        self.f_last_contact = datetime.date.today().strftime("%Y-%m-%d")
        self.f_property = self.prop_names[0] if self.prop_names else ""
        self.is_new = True

    def reload_on_db_change(self):
        self._load_property_options()
        self._load_prospects()
        self.selected_id = 0
        self.is_new = True
        self._reset_form()

    def _load_property_options(self):
        rows = run_query("SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName", db=self.db)
        self.prop_names = [str(r["PropertyName"]) for r in rows]
        self.prop_ids   = [int(r["PropertyID"]) for r in rows]
        self.property_options = ["All"] + self.prop_names

    def _load_prospects(self):
        rows = run_query(
            "SELECT p.ProspectID, p.ProspectName, p.PropertyID, p.Phone, p.Email, "
            "p.DesiredSize, p.DesiredMoveInDate, p.Source, p.ProspectStatus, "
            "p.LastContactDate, pr.PropertyName "
            "FROM Prospects p "
            "LEFT JOIN Properties pr ON p.PropertyID = pr.PropertyID "
            "ORDER BY p.DateCreated DESC, p.ProspectID DESC",
            db=self.db,
        )
        def fmt_dt(v) -> str:
            if v is None: return ""
            d = v.date() if hasattr(v, "date") else v
            return d.strftime("%m/%d/%Y")

        self.prospects = [
            ProspectRow(
                prospect_id=int(r["ProspectID"]),
                name=str(r.get("ProspectName") or ""),
                property_name=str(r.get("PropertyName") or ""),
                phone=str(r.get("Phone") or ""),
                email=str(r.get("Email") or ""),
                desired_size=str(r.get("DesiredSize") or ""),
                desired_move_in=fmt_dt(r.get("DesiredMoveInDate")),
                source=str(r.get("Source") or ""),
                status=str(r.get("ProspectStatus") or ""),
                last_contact=fmt_dt(r.get("LastContactDate")),
            )
            for r in rows
        ]

    def set_search(self, v: str): self.search = v
    def set_property_filter(self, v: str): self.property_filter = v
    def set_status_filter(self, v: str): self.status_filter = v

    def select_prospect(self, pid: int):
        self.selected_id = pid
        self.is_new = False
        self.form_error = ""
        self.form_success = ""
        self._load_form_for_selected()

    def new_prospect(self):
        self.selected_id = 0
        self.is_new = True
        self.form_error = ""
        self.form_success = ""
        self._reset_form()

    def _reset_form(self):
        self.f_name = ""
        self.f_property = self.prop_names[0] if self.prop_names else ""
        self.f_phone = ""
        self.f_email = ""
        self.f_unit_type = ""
        self.f_desired_size = ""
        self.f_move_in_date = datetime.date.today().strftime("%Y-%m-%d")
        self.f_budget = ""
        self.f_source = PROSPECT_SOURCES[0]
        self.f_status = "Waiting"
        self.f_last_contact = datetime.date.today().strftime("%Y-%m-%d")
        self.f_notes = ""
        self.f_converted_tenant_id = 0

    def _load_form_for_selected(self):
        if self.selected_id == 0:
            return
        rows = run_query(
            "SELECT p.*, pr.PropertyName FROM Prospects p "
            "LEFT JOIN Properties pr ON p.PropertyID = pr.PropertyID "
            "WHERE p.ProspectID = ?",
            (self.selected_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]

        def fmt_input_date(v) -> str:
            if v is None: return ""
            d = v.date() if hasattr(v, "date") else v
            return d.strftime("%Y-%m-%d")

        prop_name = str(r.get("PropertyName") or "")
        self.f_name         = str(r.get("ProspectName") or "")
        self.f_property     = prop_name if prop_name in self.prop_names else (self.prop_names[0] if self.prop_names else "")
        self.f_phone        = str(r.get("Phone") or "")
        self.f_email        = str(r.get("Email") or "")
        self.f_unit_type    = str(r.get("DesiredUnitType") or "")
        self.f_desired_size = str(r.get("DesiredSize") or "")
        self.f_move_in_date = fmt_input_date(r.get("DesiredMoveInDate"))
        self.f_budget       = str(r.get("BudgetRange") or "")
        self.f_source       = str(r.get("Source") or PROSPECT_SOURCES[0])
        self.f_status       = str(r.get("ProspectStatus") or "Waiting")
        self.f_last_contact = fmt_input_date(r.get("LastContactDate"))
        self.f_notes        = str(r.get("Notes") or "")
        try:
            self.f_converted_tenant_id = int(r.get("ConvertedTenantID") or 0)
        except (TypeError, ValueError):
            self.f_converted_tenant_id = 0

    # Form setters
    def set_f_name(self, v: str):         self.f_name = v
    def set_f_property(self, v: str):     self.f_property = v
    def set_f_phone(self, v: str):        self.f_phone = v
    def set_f_email(self, v: str):        self.f_email = v
    def set_f_unit_type(self, v: str):    self.f_unit_type = v
    def set_f_desired_size(self, v: str): self.f_desired_size = v
    def set_f_move_in_date(self, v: str): self.f_move_in_date = v
    def set_f_budget(self, v: str):       self.f_budget = v
    def set_f_source(self, v: str):       self.f_source = v
    def set_f_status(self, v: str):       self.f_status = v
    def set_f_last_contact(self, v: str): self.f_last_contact = v
    def set_f_notes(self, v: str):        self.f_notes = v

    def save_prospect(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_name.strip():
            self.form_error = "Name is required."
            return

        # Resolve property ID
        prop_id = None
        if self.f_property in self.prop_names:
            prop_id = self.prop_ids[self.prop_names.index(self.f_property)]

        def parse_date(s: str):
            try:
                return datetime.datetime.strptime(s, "%Y-%m-%d").date() if s else None
            except ValueError:
                return None

        now = datetime.datetime.now()
        move_in  = parse_date(self.f_move_in_date)
        last_con = parse_date(self.f_last_contact)

        if self.selected_id > 0 and not self.is_new:
            run_exec(
                "UPDATE Prospects SET ProspectName=?, PropertyID=?, Phone=?, Email=?, "
                "DesiredUnitType=?, DesiredSize=?, DesiredMoveInDate=?, BudgetRange=?, "
                "Source=?, ProspectStatus=?, LastContactDate=?, Notes=?, DateModified=? "
                "WHERE ProspectID=?",
                (
                    self.f_name.strip(), prop_id,
                    self.f_phone.strip(), self.f_email.strip().lower(),
                    self.f_unit_type.strip(), self.f_desired_size.strip(),
                    move_in, self.f_budget.strip(),
                    self.f_source, self.f_status,
                    last_con, self.f_notes, now,
                    self.selected_id,
                ),
                db=self.db,
            )
            self.form_success = f"{self.f_name.strip()} saved."
        else:
            run_exec(
                "INSERT INTO Prospects (ProspectName, PropertyID, Phone, Email, "
                "DesiredUnitType, DesiredSize, DesiredMoveInDate, BudgetRange, "
                "Source, ProspectStatus, LastContactDate, Notes, DateCreated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.f_name.strip(), prop_id,
                    self.f_phone.strip(), self.f_email.strip().lower(),
                    self.f_unit_type.strip(), self.f_desired_size.strip(),
                    move_in, self.f_budget.strip(),
                    self.f_source, self.f_status,
                    last_con, self.f_notes, now,
                ),
                db=self.db,
            )
            self.form_success = f"{self.f_name.strip()} added to waiting list."
            self.is_new = False

        self._load_prospects()


# ── UI helpers ────────────────────────────────────────────────────────────────

def status_badge(status: str) -> rx.Component:
    color = rx.match(
        status,
        ("Waiting", "blue"),
        ("Contacted", "orange"),
        ("Application Submitted", "purple"),
        ("Converted to Tenant", "green"),
        ("Closed", "gray"),
        "gray",
    )
    return rx.badge(status, color_scheme=color, variant="soft", size="1")


def prospect_list_item(p: ProspectRow) -> rx.Component:
    is_selected = WaitingListState.selected_id == p.prospect_id
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(p.name, size="2", weight="bold", color=BRAND_DARK),
                rx.spacer(),
                status_badge(p.status),
                align="center", width="100%",
            ),
            rx.hstack(
                rx.text(p.property_name, size="1", color="#888"),
                rx.text("·", size="1", color="#ccc"),
                rx.text(p.phone, size="1", color="#888"),
                spacing="1",
            ),
            rx.hstack(
                rx.text("Move-in: " + p.desired_move_in, size="1", color="#aaa"),
                rx.spacer(),
                rx.text(p.source, size="1", color="#aaa"),
                width="100%",
            ),
            spacing="1", align_items="start", width="100%",
        ),
        on_click=WaitingListState.select_prospect(p.prospect_id),
        style={
            "padding": "12px 14px",
            "border_radius": "8px",
            "cursor": "pointer",
            "background": rx.cond(is_selected, "#e8edf8", "white"),
            "border": rx.cond(is_selected, f"1px solid {BRAND_PRIMARY}", "1px solid #eee"),
            "margin_bottom": "4px",
            "_hover": {"background": "#f0f4ff"},
        },
        width="100%",
    )


def form_field(label: str, component: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color="#666"),
        component,
        spacing="1", width="100%",
    )


def waiting_list_content() -> rx.Component:
    return rx.hstack(
        # ── Left panel: list ────────────────────────────────────────────────
        rx.box(
            rx.vstack(
                # Header
                rx.hstack(
                    rx.heading("Waiting list", size="4", color=BRAND_DARK),
                    rx.spacer(),
                    rx.button(
                        "+ New",
                        on_click=WaitingListState.new_prospect,
                        size="2", color_scheme="blue", variant="soft",
                    ),
                    align="center", width="100%",
                ),

                # Filters
                rx.input(
                    placeholder="Search name, phone, email...",
                    value=WaitingListState.search,
                    on_change=WaitingListState.set_search,
                    size="2", width="100%",
                ),
                rx.hstack(
                    rx.select(
                        WaitingListState.property_options,
                        value=WaitingListState.property_filter,
                        on_change=WaitingListState.set_property_filter,
                        size="2",
                    ),
                    rx.select(
                        ["All"] + PROSPECT_STATUSES,
                        value=WaitingListState.status_filter,
                        on_change=WaitingListState.set_status_filter,
                        size="2",
                    ),
                    spacing="2", width="100%",
                ),

                # Count
                rx.text(
                    WaitingListState.filtered_prospects.length().to_string() + " prospects",
                    size="1", color="#888",
                ),

                # List
                rx.box(
                    rx.foreach(WaitingListState.filtered_prospects, prospect_list_item),
                    width="100%",
                    overflow_y="auto",
                    style={"max_height": "calc(100vh - 280px)"},
                ),

                spacing="3", width="100%", align_items="start",
            ),
            style={
                "width": "360px",
                "min_width": "360px",
                "background": "white",
                "border_right": "1px solid #dde3f0",
                "padding": "20px 16px",
                "height": "100vh",
                "overflow_y": "auto",
                "position": "sticky",
                "top": "0",
            },
        ),

        # ── Right panel: form ────────────────────────────────────────────────
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.heading(WaitingListState.form_title, size="4", color=BRAND_DARK),
                    rx.cond(
                        WaitingListState.f_converted_tenant_id > 0,
                        rx.badge(
                            "Converted → Tenant #" + WaitingListState.f_converted_tenant_id.to_string(),
                            color_scheme="green", variant="soft",
                        ),
                        rx.fragment(),
                    ),
                    align="center", spacing="3",
                ),

                # Row 1: name, property, status
                rx.grid(
                    form_field("Name *",
                        rx.input(value=WaitingListState.f_name,
                                 on_change=WaitingListState.set_f_name,
                                 placeholder="Full name", size="2", width="100%"),
                    ),
                    form_field("Property",
                        rx.cond(
                            WaitingListState.prop_names.length() > 0,
                            rx.select(WaitingListState.prop_names,
                                      value=WaitingListState.f_property,
                                      on_change=WaitingListState.set_f_property,
                                      size="2"),
                            rx.text("No properties", size="2", color="#888"),
                        ),
                    ),
                    form_field("Status",
                        rx.select(PROSPECT_STATUSES,
                                  value=WaitingListState.f_status,
                                  on_change=WaitingListState.set_f_status,
                                  size="2"),
                    ),
                    columns="3", spacing="4", width="100%",
                ),

                # Row 2: phone, email, source
                rx.grid(
                    form_field("Phone",
                        rx.input(value=WaitingListState.f_phone,
                                 on_change=WaitingListState.set_f_phone,
                                 placeholder="Phone number", size="2", width="100%"),
                    ),
                    form_field("Email",
                        rx.input(value=WaitingListState.f_email,
                                 on_change=WaitingListState.set_f_email,
                                 placeholder="Email address", size="2",
                                 type="email", width="100%"),
                    ),
                    form_field("Source",
                        rx.select(PROSPECT_SOURCES,
                                  value=WaitingListState.f_source,
                                  on_change=WaitingListState.set_f_source,
                                  size="2"),
                    ),
                    columns="3", spacing="4", width="100%",
                ),

                # Row 3: unit type, desired size, budget
                rx.grid(
                    form_field("Desired unit type",
                        rx.input(value=WaitingListState.f_unit_type,
                                 on_change=WaitingListState.set_f_unit_type,
                                 placeholder="e.g. Office, Retail", size="2", width="100%"),
                    ),
                    form_field("Desired size",
                        rx.input(value=WaitingListState.f_desired_size,
                                 on_change=WaitingListState.set_f_desired_size,
                                 placeholder="e.g. 800-1000 sf", size="2", width="100%"),
                    ),
                    form_field("Budget range",
                        rx.input(value=WaitingListState.f_budget,
                                 on_change=WaitingListState.set_f_budget,
                                 placeholder="e.g. $800-1200/mo", size="2", width="100%"),
                    ),
                    columns="3", spacing="4", width="100%",
                ),

                # Row 4: move-in date, last contact date
                rx.grid(
                    form_field("Desired move-in date",
                        rx.input(value=WaitingListState.f_move_in_date,
                                 on_change=WaitingListState.set_f_move_in_date,
                                 type="date", size="2", width="100%"),
                    ),
                    form_field("Last contact date",
                        rx.input(value=WaitingListState.f_last_contact,
                                 on_change=WaitingListState.set_f_last_contact,
                                 type="date", size="2", width="100%"),
                    ),
                    columns="2", spacing="4", width="100%",
                ),

                # Notes
                form_field("Notes",
                    rx.text_area(
                        value=WaitingListState.f_notes,
                        on_change=WaitingListState.set_f_notes,
                        placeholder="Any additional context...",
                        width="100%", rows="4",
                    ),
                ),

                # Feedback
                rx.cond(
                    WaitingListState.form_error != "",
                    rx.callout(WaitingListState.form_error, color="red", variant="soft"),
                    rx.fragment(),
                ),
                rx.cond(
                    WaitingListState.form_success != "",
                    rx.callout(WaitingListState.form_success, color="green", variant="soft"),
                    rx.fragment(),
                ),

                rx.button(
                    rx.cond(
                        WaitingListState.selected_id > 0,
                        "Save prospect",
                        "Add to waiting list",
                    ),
                    on_click=WaitingListState.save_prospect,
                    color_scheme="blue", size="2",
                ),

                spacing="4", width="100%", align_items="start",
            ),
            style={
                "flex": "1",
                "padding": "24px 32px",
                "overflow_y": "auto",
            },
        ),

        spacing="0",
        width="100%",
        align_items="start",
        style={"min_height": "100vh"},
    )


def waiting_list_page() -> rx.Component:
    return page_shell(waiting_list_content(), current_path="/waiting-list")
