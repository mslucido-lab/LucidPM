"""
Tenants page — unified tenant list + detail view.
Replaces the separate Tenants and Tenant Detail pages from Streamlit.
"""

import reflex as rx
import pyodbc
import datetime

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec, fmt_date,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES, TEST_DB_NAME,
)
from LucidPM_Reflex.components.sidebar import page_shell


# ── Data models ───────────────────────────────────────────────────────────────

class Contact(rx.Base):
    contact_id: int = 0
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    role: str = ""
    email: str = ""
    phone: str = ""
    is_primary: bool = False
    salutation: str = ""
    title: str = ""
    home_phone: str = ""
    email2: str = ""


class Comm(rx.Base):
    comm_id: int = 0
    comm_date: str = ""
    method: str = ""
    subject: str = ""
    outcome: str = ""
    next_action_date: str = ""
    notes: str = ""
    contact_name: str = ""
    is_overdue: bool = False


class TenantSummary(rx.Base):
    tenant_id: int = 0
    tenant_name: str = ""
    status: str = ""
    suite: str = ""
    property_name: str = ""


# ── Tenant state ──────────────────────────────────────────────────────────────

class TenantState(AppState):

    # Tenant list
    tenant_list: list[TenantSummary] = []
    status_filter: str = "Active"
    property_filter: str = "All"
    property_filter_options: list[str] = ["All"]

    # Selected tenant
    tenant_names: list[str] = []
    tenant_ids: list[int] = []
    selected_tenant_name: str = ""
    tenant_id: int = 0
    tenant_status: str = ""
    tenant_type: str = ""
    tenant_suite: str = ""
    tenant_property: str = ""
    tenant_notes: str = ""
    tenant_initials: str = ""

    # Contacts
    contacts: list[Contact] = []
    selected_contact_id: int = 0
    contact_mode: str = "new"
    f_salutation: str = ""
    f_first: str = ""
    f_last: str = ""
    f_title: str = ""
    f_role: str = ""
    f_work_phone: str = ""
    f_home_phone: str = ""
    f_email1: str = ""
    f_email2: str = ""
    f_is_primary: bool = False
    form_error: str = ""
    form_success: str = ""

    # Communications
    comms: list[Comm] = []
    selected_comm_id: int = 0
    comm_mode: str = "new"
    c_date: str = ""
    c_method: str = "Call"
    c_subject: str = ""
    c_outcome: str = ""
    c_next_action_date: str = ""
    c_notes: str = ""
    c_template_name: str = ""
    comm_form_error: str = ""
    comm_form_success: str = ""
    comm_contact_names: list[str] = []
    comm_contact_ids: list[int] = []
    comm_selected_contact_name: str = ""
    method_choices: list[str] = METHOD_CHOICES

    @rx.var
    def editing_banner(self) -> str:
        return f"Editing: {self.f_first} {self.f_last}".strip()

    @rx.var
    def comm_editing_banner(self) -> str:
        return f"Editing: {self.c_date} — {self.c_subject}".strip(" —")

    @rx.var
    def tenant_location(self) -> str:
        parts = [x for x in [self.tenant_suite, self.tenant_property] if x]
        return " · ".join(parts)

    @rx.var
    def tenant_subtitle(self) -> str:
        parts = [x for x in [self.tenant_type, f"Tenant #{self.tenant_id}"] if x]
        return " · ".join(parts)

    def on_load(self):
        self._load_property_options()
        self.load_tenant_list()

    def _load_property_options(self):
        rows = run_query("SELECT PropertyName FROM Properties ORDER BY PropertyName", db=self.db)
        self.property_filter_options = ["All"] + [r["PropertyName"] for r in rows]

    def load_tenant_list(self):
        conditions = []
        params = []
        if self.status_filter != "All":
            conditions.append("s.TenantStatusName = ?")
            params.append(self.status_filter)
        if self.property_filter != "All":
            conditions.append("p.PropertyName = ?")
            params.append(self.property_filter)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, s.TenantStatusName, "
            "ps.SuiteLabel, p.PropertyName "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            f"{where} ORDER BY t.TenantName",
            tuple(params),
            db=self.db,
        )
        self.tenant_list = [
            TenantSummary(
                tenant_id=r["TenantID"],
                tenant_name=str(r.get("TenantName") or ""),
                status=str(r.get("TenantStatusName") or ""),
                suite=str(r.get("SuiteLabel") or ""),
                property_name=str(r.get("PropertyName") or ""),
            )
            for r in rows
        ]
        self.tenant_names = [r["TenantName"] for r in rows]
        self.tenant_ids = [r["TenantID"] for r in rows]
        if rows and self.tenant_id == 0:
            self._load_tenant_detail(rows[0]["TenantID"])

    def set_status_filter(self, v: str):
        self.status_filter = v
        self.load_tenant_list()

    def set_property_filter(self, v: str):
        self.property_filter = v
        self.load_tenant_list()

    def select_tenant_from_list(self, tenant_id: int):
        self._load_tenant_detail(tenant_id)

    def on_tenant_dropdown_change(self, name: str):
        self.selected_tenant_name = name
        if name in self.tenant_names:
            idx = self.tenant_names.index(name)
            self._load_tenant_detail(self.tenant_ids[idx])

    def _load_tenant_detail(self, tenant_id: int):
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, s.TenantStatusName, tt.TenantTypeName, "
            "ps.SuiteLabel, p.PropertyName, t.Notes "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN TenantTypes tt ON t.TenantTypeID = tt.TenantTypeID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            "WHERE t.TenantID = ?",
            (tenant_id,),
            db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.tenant_id = r["TenantID"]
        self.selected_tenant_name = str(r.get("TenantName") or "")
        self.tenant_status = str(r.get("TenantStatusName") or "")
        self.tenant_type = str(r.get("TenantTypeName") or "")
        self.tenant_suite = str(r.get("SuiteLabel") or "")
        self.tenant_property = str(r.get("PropertyName") or "")
        self.tenant_notes = str(r.get("Notes") or "")
        name = str(r.get("TenantName") or "")
        self.tenant_initials = "".join([w[0].upper() for w in name.split() if w][:2]) or "?"
        self.load_contacts()
        self.load_comms()
        self.new_contact()
        self.new_comm()

    # ── Contacts ──────────────────────────────────────────────────────────────

    def load_contacts(self):
        rows = run_query(
            "SELECT ContactID, FirstName, LastName, ContactRole, Title, "
            "WorkPhone, HomePhone, Email1, Email2, IsPrimary, Salutation "
            "FROM Contacts WHERE TenantID = ? "
            "ORDER BY IsPrimary DESC, LastName, FirstName",
            (self.tenant_id,),
            db=self.db,
        )
        self.contacts = [
            Contact(
                contact_id=r["ContactID"],
                first_name=str(r.get("FirstName") or ""),
                last_name=str(r.get("LastName") or ""),
                full_name=(f"{r.get('FirstName') or ''} {r.get('LastName') or ''}".strip()
                           or f"Contact #{r['ContactID']}"),
                role=str(r.get("ContactRole") or r.get("Title") or ""),
                email=str(r.get("Email1") or ""),
                phone=str(r.get("WorkPhone") or ""),
                is_primary=bool(r.get("IsPrimary")),
                salutation=str(r.get("Salutation") or ""),
                title=str(r.get("Title") or ""),
                home_phone=str(r.get("HomePhone") or ""),
                email2=str(r.get("Email2") or ""),
            )
            for r in rows
        ]
        self._load_comm_contact_options()

    def select_contact(self, contact_id: int):
        self.selected_contact_id = contact_id
        self.contact_mode = "edit"
        self.form_error = ""
        self.form_success = ""
        matches = [c for c in self.contacts if c.contact_id == contact_id]
        if matches:
            c = matches[0]
            self.f_salutation = c.salutation
            self.f_first = c.first_name
            self.f_last = c.last_name
            self.f_title = c.title
            self.f_role = c.role
            self.f_work_phone = c.phone
            self.f_home_phone = c.home_phone
            self.f_email1 = c.email
            self.f_email2 = c.email2
            self.f_is_primary = c.is_primary

    def new_contact(self):
        self.selected_contact_id = 0
        self.contact_mode = "new"
        self.form_error = ""
        self.form_success = ""
        self.f_salutation = self.f_first = self.f_last = ""
        self.f_title = self.f_role = self.f_work_phone = ""
        self.f_home_phone = self.f_email1 = self.f_email2 = ""
        self.f_is_primary = False

    def save_contact(self):
        self.form_error = ""
        self.form_success = ""
        if not (self.f_first.strip() or self.f_last.strip()):
            self.form_error = "First name or last name is required."
            return
        if self.f_is_primary:
            run_exec("UPDATE Contacts SET IsPrimary = 0 WHERE TenantID = ?",
                     (self.tenant_id,), db=self.db)
        if self.contact_mode == "edit":
            run_exec(
                "UPDATE Contacts SET Salutation=?, FirstName=?, LastName=?, Title=?, "
                "ContactRole=?, WorkPhone=?, HomePhone=?, Email1=?, Email2=?, IsPrimary=? "
                "WHERE ContactID=?",
                (self.f_salutation.strip(), self.f_first.strip(), self.f_last.strip(),
                 self.f_title.strip(), self.f_role.strip(), self.f_work_phone.strip(),
                 self.f_home_phone.strip(), self.f_email1.strip(), self.f_email2.strip(),
                 self.f_is_primary, self.selected_contact_id),
                db=self.db,
            )
            self.form_success = "Contact saved."
        else:
            run_exec(
                "INSERT INTO Contacts (TenantID, Salutation, FirstName, LastName, Title, "
                "ContactRole, WorkPhone, HomePhone, Email1, Email2, IsPrimary) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (self.tenant_id, self.f_salutation.strip(), self.f_first.strip(),
                 self.f_last.strip(), self.f_title.strip(), self.f_role.strip(),
                 self.f_work_phone.strip(), self.f_home_phone.strip(),
                 self.f_email1.strip(), self.f_email2.strip(), self.f_is_primary),
                db=self.db,
            )
            self.form_success = "Contact created."
        self.load_contacts()

    def delete_contact(self):
        if self.selected_contact_id == 0:
            return
        run_exec("DELETE FROM Contacts WHERE ContactID = ?",
                 (self.selected_contact_id,), db=self.db)
        self.load_contacts()
        self.new_contact()

    def set_f_salutation(self, v): self.f_salutation = v
    def set_f_first(self, v): self.f_first = v
    def set_f_last(self, v): self.f_last = v
    def set_f_title(self, v): self.f_title = v
    def set_f_role(self, v): self.f_role = v
    def set_f_work_phone(self, v): self.f_work_phone = v
    def set_f_home_phone(self, v): self.f_home_phone = v
    def set_f_email1(self, v): self.f_email1 = v
    def set_f_email2(self, v): self.f_email2 = v
    def set_f_is_primary(self, v): self.f_is_primary = v

    # ── Communications ────────────────────────────────────────────────────────

    def load_comms(self):
        today = datetime.date.today()
        rows = run_query(
            "SELECT c.CommunicationID, c.CommDate, c.Method, c.Subject, c.Outcome, "
            "c.NextActionDate, c.Notes, c.ContactID, c.TemplateName, "
            "ct.FirstName, ct.LastName "
            "FROM Communications c "
            "LEFT JOIN Contacts ct ON c.ContactID = ct.ContactID "
            "WHERE c.TenantID = ? ORDER BY c.CommDate DESC",
            (self.tenant_id,),
            db=self.db,
        )
        comms = []
        for r in rows:
            raw_date = r.get("CommDate")
            raw_next = r.get("NextActionDate")
            fn = str(r.get("FirstName") or "")
            ln = str(r.get("LastName") or "")
            is_overdue = bool(raw_next and hasattr(raw_next, 'date') and raw_next.date() < today)
            comms.append(Comm(
                comm_id=r["CommunicationID"],
                comm_date=raw_date.strftime("%m/%d/%Y") if raw_date else "",
                method=str(r.get("Method") or ""),
                subject=str(r.get("Subject") or ""),
                outcome=str(r.get("Outcome") or ""),
                next_action_date=raw_next.strftime("%m/%d/%Y") if raw_next else "",
                notes=str(r.get("Notes") or ""),
                contact_name=f"{fn} {ln}".strip(),
                is_overdue=is_overdue,
            ))
        self.comms = comms

    def _load_comm_contact_options(self):
        rows = run_query(
            "SELECT ContactID, FirstName, LastName FROM Contacts "
            "WHERE TenantID = ? ORDER BY IsPrimary DESC, LastName, FirstName",
            (self.tenant_id,),
            db=self.db,
        )
        names = ["(No contact)"]
        ids = [0]
        for r in rows:
            fn = str(r.get("FirstName") or "")
            ln = str(r.get("LastName") or "")
            names.append(f"{fn} {ln}".strip() or f"Contact #{r['ContactID']}")
            ids.append(r["ContactID"])
        self.comm_contact_names = names
        self.comm_contact_ids = ids

    def select_comm(self, comm_id: int):
        self.selected_comm_id = comm_id
        self.comm_mode = "edit"
        self.comm_form_error = ""
        self.comm_form_success = ""
        rows = run_query(
            "SELECT CommunicationID, CommDate, Method, Subject, Outcome, "
            "NextActionDate, Notes, ContactID, TemplateName "
            "FROM Communications WHERE CommunicationID = ?",
            (comm_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        raw_date = r.get("CommDate")
        raw_next = r.get("NextActionDate")
        self.c_date = raw_date.strftime("%Y-%m-%d") if raw_date else ""
        self.c_method = str(r.get("Method") or "Call")
        self.c_subject = str(r.get("Subject") or "")
        self.c_outcome = str(r.get("Outcome") or "")
        self.c_next_action_date = raw_next.strftime("%Y-%m-%d") if raw_next else ""
        self.c_notes = str(r.get("Notes") or "")
        self.c_template_name = str(r.get("TemplateName") or "")
        cid = r.get("ContactID")
        if cid and int(cid) in self.comm_contact_ids:
            idx = self.comm_contact_ids.index(int(cid))
            self.comm_selected_contact_name = self.comm_contact_names[idx]
        else:
            self.comm_selected_contact_name = "(No contact)"

    def new_comm(self):
        self.selected_comm_id = 0
        self.comm_mode = "new"
        self.comm_form_error = ""
        self.comm_form_success = ""
        self.c_date = datetime.date.today().strftime("%Y-%m-%d")
        self.c_method = "Call"
        self.c_subject = self.c_outcome = self.c_next_action_date = ""
        self.c_notes = self.c_template_name = ""
        self.comm_selected_contact_name = "(No contact)"

    def save_comm(self):
        self.comm_form_error = ""
        self.comm_form_success = ""
        if not self.c_subject.strip():
            self.comm_form_error = "Subject is required."
            return
        try:
            comm_date = datetime.datetime.strptime(self.c_date, "%Y-%m-%d").date() if self.c_date else datetime.date.today()
        except ValueError:
            comm_date = datetime.date.today()
        try:
            next_date = datetime.datetime.strptime(self.c_next_action_date, "%Y-%m-%d").date() if self.c_next_action_date else None
        except ValueError:
            next_date = None
        cid = None
        if self.comm_selected_contact_name != "(No contact)" and self.comm_selected_contact_name in self.comm_contact_names:
            idx = self.comm_contact_names.index(self.comm_selected_contact_name)
            cid = self.comm_contact_ids[idx] or None
        if self.comm_mode == "edit":
            run_exec(
                "UPDATE Communications SET CommDate=?, Method=?, Subject=?, TemplateName=?, "
                "Outcome=?, NextActionDate=?, Notes=?, ContactID=? WHERE CommunicationID=?",
                (comm_date, self.c_method, self.c_subject.strip(), self.c_template_name.strip(),
                 self.c_outcome.strip(), next_date, self.c_notes, cid, self.selected_comm_id),
                db=self.db,
            )
            self.comm_form_success = "Communication saved."
        else:
            run_exec(
                "INSERT INTO Communications (TenantID, CommDate, Method, Subject, TemplateName, "
                "Outcome, NextActionDate, Notes, ContactID) VALUES (?,?,?,?,?,?,?,?,?)",
                (self.tenant_id, comm_date, self.c_method, self.c_subject.strip(),
                 self.c_template_name.strip(), self.c_outcome.strip(), next_date,
                 self.c_notes, cid),
                db=self.db,
            )
            self.comm_form_success = "Communication logged."
        self.load_comms()

    def delete_comm(self):
        if self.selected_comm_id == 0:
            return
        run_exec("DELETE FROM Communications WHERE CommunicationID = ?",
                 (self.selected_comm_id,), db=self.db)
        self.load_comms()
        self.new_comm()

    def set_c_date(self, v): self.c_date = v
    def set_c_method(self, v): self.c_method = v
    def set_c_subject(self, v): self.c_subject = v
    def set_c_outcome(self, v): self.c_outcome = v
    def set_c_next_action_date(self, v): self.c_next_action_date = v
    def set_c_notes(self, v): self.c_notes = v
    def set_c_template_name(self, v): self.c_template_name = v
    def set_comm_selected_contact_name(self, v): self.comm_selected_contact_name = v


# ── UI helpers ────────────────────────────────────────────────────────────────

def pill(label: str, bg: str, color: str) -> rx.Component:
    return rx.box(
        rx.text(label, size="1", weight="bold", color=color),
        style={"background": bg, "border_radius": "999px", "padding": "2px 10px"},
    )


def edit_banner(text: rx.Var) -> rx.Component:
    return rx.box(
        rx.text("✏️ " + text, size="2", weight="bold", color=BRAND_DARK),
        style={
            "background": "#f0f4ff", "border": "1px solid #c5d0f0",
            "border_left": f"4px solid {BRAND_PRIMARY}",
            "border_radius": "6px", "padding": "8px 14px", "width": "100%",
        },
    )


# ── Tenant list panel ─────────────────────────────────────────────────────────

def tenant_list_row(t: TenantSummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(t.tenant_name, size="2", weight="bold")),
        rx.table.cell(rx.text(t.suite, size="2", color="#555")),
        rx.table.cell(
            rx.button("View", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_tenant_from_list(t.tenant_id))
        ),
        style=rx.cond(
            TenantState.tenant_id == t.tenant_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )


def tenant_list_panel() -> rx.Component:
    return rx.vstack(
        # Header row with title and status filter
        rx.hstack(
            rx.heading("Tenants", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.select(
                ["Active", "Prospect", "Inactive", "All"],
                value=TenantState.status_filter,
                on_change=TenantState.set_status_filter,
                size="1",
            ),
            align="center", width="100%",
        ),
        # Property filter — full width below header
        rx.hstack(
            rx.text("Property:", size="1", color="#666", white_space="nowrap"),
            rx.select(
                TenantState.property_filter_options,
                value=TenantState.property_filter,
                on_change=TenantState.set_property_filter,
                size="1",
                width="100%",
            ),
            align="center", spacing="2", width="100%",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Suite"),
                    rx.table.column_header_cell(""),
                )
            ),
            rx.table.body(rx.foreach(TenantState.tenant_list, tenant_list_row)),
            width="100%", variant="surface",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Tenant header card ────────────────────────────────────────────────────────

def tenant_header_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.text(TenantState.tenant_initials, color="white", weight="bold", size="5"),
                style={
                    "width": "52px", "height": "52px", "border_radius": "50%",
                    "background": BRAND_PRIMARY, "display": "flex",
                    "align_items": "center", "justify_content": "center", "flex_shrink": "0",
                },
            ),
            rx.vstack(
                rx.hstack(
                    rx.text(TenantState.selected_tenant_name, weight="bold", size="5", color=BRAND_DARK),
                    rx.cond(
                        TenantState.tenant_status == "Active",
                        pill(TenantState.tenant_status, "#e8f5e9", "#1b5e20"),
                        pill(TenantState.tenant_status, "#eeeeee", "#555555"),
                    ),
                    rx.cond(
                        TenantState.tenant_location != "",
                        pill(TenantState.tenant_location, "#f0f4ff", BRAND_PRIMARY),
                        rx.fragment(),
                    ),
                    align="center", spacing="2", wrap="wrap",
                ),
                rx.text(TenantState.tenant_subtitle, size="2", color="#666"),
                spacing="1", align_items="start",
            ),
            align="center", spacing="4",
        ),
        style={
            "background": "white", "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}", "border_radius": "12px",
            "padding": "16px 20px", "margin_bottom": "8px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
        },
    )


# ── Contacts tab ──────────────────────────────────────────────────────────────

def contact_row(c: Contact) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(c.full_name, weight="bold", size="2"),
                rx.cond(c.is_primary, pill("Primary", "#e8f5e9", "#1b5e20"), rx.fragment()),
                align="center", spacing="2",
            )
        ),
        rx.table.cell(rx.text(c.role, size="2", color="#555")),
        rx.table.cell(rx.text(c.email, size="2", color="#555")),
        rx.table.cell(rx.text(c.phone, size="2", color="#555")),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_contact(c.contact_id))
        ),
        style=rx.cond(
            TenantState.selected_contact_id == c.contact_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


def contacts_tab() -> rx.Component:
    return rx.vstack(
        rx.cond(
            TenantState.contacts.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Role"),
                        rx.table.column_header_cell("Email"),
                        rx.table.column_header_cell("Phone"),
                        rx.table.column_header_cell(""),
                    )
                ),
                rx.table.body(rx.foreach(TenantState.contacts, contact_row)),
                width="100%", variant="surface",
            ),
            rx.text("No contacts yet.", color="#888", size="2"),
        ),
        rx.button("+ New contact", on_click=TenantState.new_contact,
                  variant="outline", color_scheme="blue", size="2"),
        rx.divider(),
        rx.cond(
            TenantState.contact_mode == "edit",
            edit_banner(TenantState.editing_banner),
            rx.text("New contact", size="3", weight="bold", color=BRAND_DARK),
        ),
        rx.grid(
            rx.vstack(rx.text("Salutation", size="1", color="#666"),
                      rx.input(value=TenantState.f_salutation, on_change=TenantState.set_f_salutation,
                               placeholder="Ms.", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("First name *", size="1", color="#666"),
                      rx.input(value=TenantState.f_first, on_change=TenantState.set_f_first,
                               placeholder="First name", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Last name *", size="1", color="#666"),
                      rx.input(value=TenantState.f_last, on_change=TenantState.set_f_last,
                               placeholder="Last name", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Job title", size="1", color="#666"),
                      rx.input(value=TenantState.f_title, on_change=TenantState.set_f_title,
                               placeholder="Job title", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Role", size="1", color="#666"),
                      rx.input(value=TenantState.f_role, on_change=TenantState.set_f_role,
                               placeholder="e.g. Property Manager", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Work phone", size="1", color="#666"),
                      rx.input(value=TenantState.f_work_phone, on_change=TenantState.set_f_work_phone,
                               placeholder="Work phone", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Mobile / home", size="1", color="#666"),
                      rx.input(value=TenantState.f_home_phone, on_change=TenantState.set_f_home_phone,
                               placeholder="Mobile / home", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Primary email", size="1", color="#666"),
                      rx.input(value=TenantState.f_email1, on_change=TenantState.set_f_email1,
                               placeholder="email@example.com", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Secondary email", size="1", color="#666"),
                      rx.input(value=TenantState.f_email2, on_change=TenantState.set_f_email2,
                               placeholder="Secondary email", size="2", width="100%"),
                      spacing="1", width="100%"),
            columns="3", spacing="4", width="100%",
        ),
        rx.hstack(
            rx.switch(checked=TenantState.f_is_primary, on_change=TenantState.set_f_is_primary),
            rx.vstack(
                rx.text("Primary contact", size="2", weight="bold"),
                rx.text("Receives all primary correspondence", size="1", color="#666"),
                spacing="0",
            ),
            align="center", spacing="3",
        ),
        rx.cond(TenantState.form_error != "",
                rx.callout(TenantState.form_error, color="red", variant="soft"), rx.fragment()),
        rx.cond(TenantState.form_success != "",
                rx.callout(TenantState.form_success, color="green", variant="soft"), rx.fragment()),
        rx.hstack(
            rx.button(
                rx.cond(TenantState.contact_mode == "edit", "Save contact", "Create contact"),
                on_click=TenantState.save_contact, color_scheme="blue", size="2",
            ),
            rx.cond(
                TenantState.contact_mode == "edit",
                rx.button("Delete contact", on_click=TenantState.delete_contact,
                          color_scheme="red", variant="outline", size="2"),
                rx.fragment(),
            ),
            rx.button("Cancel", on_click=TenantState.new_contact, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Communications tab ────────────────────────────────────────────────────────

def comm_row(c: Comm) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(c.comm_date, size="2")),
        rx.table.cell(rx.text(c.method, size="2")),
        rx.table.cell(rx.text(c.subject, size="2", weight="bold")),
        rx.table.cell(rx.text(c.outcome, size="2", color="#555")),
        rx.table.cell(
            rx.cond(
                c.is_overdue,
                rx.text(c.next_action_date, size="2", color="#c62828", weight="bold"),
                rx.text(c.next_action_date, size="2", color="#555"),
            )
        ),
        rx.table.cell(rx.text(c.contact_name, size="2", color="#555")),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_comm(c.comm_id))
        ),
        style=rx.cond(
            TenantState.selected_comm_id == c.comm_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


def comms_tab() -> rx.Component:
    return rx.vstack(
        rx.cond(
            TenantState.comms.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Date"),
                        rx.table.column_header_cell("Method"),
                        rx.table.column_header_cell("Subject"),
                        rx.table.column_header_cell("Outcome"),
                        rx.table.column_header_cell("Follow-up"),
                        rx.table.column_header_cell("Contact"),
                        rx.table.column_header_cell(""),
                    )
                ),
                rx.table.body(rx.foreach(TenantState.comms, comm_row)),
                width="100%", variant="surface",
            ),
            rx.text("No communications yet.", color="#888", size="2"),
        ),
        rx.button("+ Log communication", on_click=TenantState.new_comm,
                  variant="outline", color_scheme="blue", size="2"),
        rx.divider(),
        rx.cond(
            TenantState.comm_mode == "edit",
            edit_banner(TenantState.comm_editing_banner),
            rx.text("Log communication", size="3", weight="bold", color=BRAND_DARK),
        ),
        rx.grid(
            rx.vstack(rx.text("Date", size="1", color="#666"),
                      rx.input(value=TenantState.c_date, on_change=TenantState.set_c_date,
                               type="date", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Method", size="1", color="#666"),
                      rx.select(TenantState.method_choices, value=TenantState.c_method,
                                on_change=TenantState.set_c_method, size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Contact", size="1", color="#666"),
                      rx.select(TenantState.comm_contact_names,
                                value=TenantState.comm_selected_contact_name,
                                on_change=TenantState.set_comm_selected_contact_name,
                                size="2", width="100%"),
                      spacing="1", width="100%"),
            columns="3", spacing="4", width="100%",
        ),
        rx.grid(
            rx.vstack(rx.text("Subject *", size="1", color="#666"),
                      rx.input(value=TenantState.c_subject, on_change=TenantState.set_c_subject,
                               placeholder="What was this about?", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Outcome", size="1", color="#666"),
                      rx.input(value=TenantState.c_outcome, on_change=TenantState.set_c_outcome,
                               placeholder="e.g. Left voicemail, Resolved", size="2", width="100%"),
                      spacing="1", width="100%"),
            rx.vstack(rx.text("Follow-up date", size="1", color="#666"),
                      rx.input(value=TenantState.c_next_action_date,
                               on_change=TenantState.set_c_next_action_date,
                               type="date", size="2", width="100%"),
                      spacing="1", width="100%"),
            columns="3", spacing="4", width="100%",
        ),
        rx.vstack(
            rx.text("Notes", size="1", color="#666"),
            rx.text_area(value=TenantState.c_notes, on_change=TenantState.set_c_notes,
                         placeholder="Additional notes...", width="100%", rows="4"),
            spacing="1", width="100%",
        ),
        rx.cond(TenantState.comm_form_error != "",
                rx.callout(TenantState.comm_form_error, color="red", variant="soft"), rx.fragment()),
        rx.cond(TenantState.comm_form_success != "",
                rx.callout(TenantState.comm_form_success, color="green", variant="soft"), rx.fragment()),
        rx.hstack(
            rx.button(
                rx.cond(TenantState.comm_mode == "edit", "Save communication", "Log communication"),
                on_click=TenantState.save_comm, color_scheme="blue", size="2",
            ),
            rx.cond(
                TenantState.comm_mode == "edit",
                rx.button("Delete", on_click=TenantState.delete_comm,
                          color_scheme="red", variant="outline", size="2"),
                rx.fragment(),
            ),
            rx.button("Cancel", on_click=TenantState.new_comm, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Tenant detail panel ───────────────────────────────────────────────────────

def tenant_detail_panel() -> rx.Component:
    return rx.vstack(
        tenant_header_card(),
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Contacts", value="contacts"),
                rx.tabs.trigger("Communications", value="communications"),
                rx.tabs.trigger("Leases", value="leases"),
                rx.tabs.trigger("Documents", value="documents"),
            ),
            rx.tabs.content(contacts_tab(), value="contacts", padding_top="16px"),
            rx.tabs.content(comms_tab(), value="communications", padding_top="16px"),
            rx.tabs.content(
                rx.text("Leases — coming soon", color="#888"),
                value="leases", padding_top="16px",
            ),
            rx.tabs.content(
                rx.text("Documents — coming soon", color="#888"),
                value="documents", padding_top="16px",
            ),
            default_value="contacts", width="100%",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Page ──────────────────────────────────────────────────────────────────────

def tenants_content() -> rx.Component:
    return rx.hstack(
        # Left panel — tenant list
        rx.box(
            tenant_list_panel(),
            style={
                "width": "420px",
                "min_width": "420px",
                "max_height": "calc(100vh - 80px)",
                "overflow_y": "auto",
                "background": "white",
                "border": "1px solid #dde3f0",
                "border_radius": "12px",
                "padding": "20px",
                "height": "fit-content",
            },
        ),

        # Right panel — tenant detail
        rx.box(
            rx.cond(
                TenantState.tenant_id > 0,
                tenant_detail_panel(),
                rx.vstack(
                    rx.text("👈 Select a tenant to view details", color="#888", size="3"),
                    align_items="center",
                    padding_top="48px",
                ),
            ),
            flex="1",
            min_width="0",
            style={
                "max_height": "calc(100vh - 80px)",
                "overflow_y": "auto",
                "position": "sticky",
                "top": "0",
            },
        ),

        spacing="5",
        width="100%",
        align_items="start",
    )


def tenants_page() -> rx.Component:
    return page_shell(tenants_content(), current_path="/tenants")
