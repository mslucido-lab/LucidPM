"""
Lucido Property Manager — Reflex Prototype
Tenant Detail + Contacts tab proof of concept
Drop this file into the LucidoPM_Reflex subfolder and run: reflex run
"""

import reflex as rx
import pyodbc
import pandas as pd
from typing import Optional

# ── DB config ────────────────────────────────────────────────────────────────
SQL_SERVER = "localhost\\SQLEXPRESS"
PROD_DB_NAME = "TenantCRM"
TEST_DB_NAME = "TenantCRM_Test"

BRAND_PRIMARY = "#4A63A8"
BRAND_DARK = "#2F4C97"
BRAND_LIGHT_BG = "#F4F6FA"

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_conn(db: str = TEST_DB_NAME) -> pyodbc.Connection:
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={db};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def query(sql: str, params: tuple = (), db: str = TEST_DB_NAME) -> list[dict]:
    with get_conn(db) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def execute(sql: str, params: tuple = (), db: str = TEST_DB_NAME) -> None:
    with get_conn(db) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()


# ── State ─────────────────────────────────────────────────────────────────────
class State(rx.State):

    # DB toggle
    use_test_db: bool = True

    # Tenant list
    tenants: list[dict] = []
    selected_tenant_id: int = 0
    tenant_name: str = ""
    tenant_status: str = ""
    tenant_type: str = ""
    tenant_suite: str = ""
    tenant_property: str = ""
    tenant_notes: str = ""

    # Contacts
    contacts: list[dict] = []
    selected_contact_id: int = 0
    contact_mode: str = "new"  # "new" | "edit"

    # Contact form fields
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

    # UI state
    form_error: str = ""
    form_success: str = ""
    active_tab: str = "contacts"

    @property
    def db(self) -> str:
        return TEST_DB_NAME if self.use_test_db else PROD_DB_NAME

    def load_tenants(self):
        rows = query(
            "SELECT t.TenantID, t.TenantName, t.TenantStatusID, s.StatusName, "
            "tt.TenantTypeName, ps.SuiteName, p.PropertyName, t.Notes "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN TenantTypes tt ON t.TenantTypeID = tt.TenantTypeID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            "WHERE s.StatusName = 'Active' "
            "ORDER BY t.TenantName",
            db=self.db,
        )
        self.tenants = rows
        if rows and self.selected_tenant_id == 0:
            self.select_tenant(rows[0]["TenantID"])

    def select_tenant(self, tenant_id: int):
        self.selected_tenant_id = tenant_id
        matches = [t for t in self.tenants if t["TenantID"] == tenant_id]
        if matches:
            t = matches[0]
            self.tenant_name = str(t.get("TenantName") or "")
            self.tenant_status = str(t.get("StatusName") or "")
            self.tenant_type = str(t.get("TenantTypeName") or "")
            self.tenant_suite = str(t.get("SuiteName") or "")
            self.tenant_property = str(t.get("PropertyName") or "")
            self.tenant_notes = str(t.get("Notes") or "")
        self.load_contacts()
        self.new_contact()

    def load_contacts(self):
        self.contacts = query(
            "SELECT ContactID, FirstName, LastName, ContactRole, Title, "
            "WorkPhone, HomePhone, Email1, Email2, IsPrimary, Salutation "
            "FROM Contacts WHERE TenantID = ? "
            "ORDER BY IsPrimary DESC, LastName, FirstName",
            (self.selected_tenant_id,),
            db=self.db,
        )

    def select_contact(self, contact_id: int):
        self.selected_contact_id = contact_id
        self.contact_mode = "edit"
        self.form_error = ""
        self.form_success = ""
        matches = [c for c in self.contacts if c["ContactID"] == contact_id]
        if matches:
            c = matches[0]
            self.f_salutation = str(c.get("Salutation") or "")
            self.f_first = str(c.get("FirstName") or "")
            self.f_last = str(c.get("LastName") or "")
            self.f_title = str(c.get("Title") or "")
            self.f_role = str(c.get("ContactRole") or "")
            self.f_work_phone = str(c.get("WorkPhone") or "")
            self.f_home_phone = str(c.get("HomePhone") or "")
            self.f_email1 = str(c.get("Email1") or "")
            self.f_email2 = str(c.get("Email2") or "")
            self.f_is_primary = bool(c.get("IsPrimary") or False)

    def new_contact(self):
        self.selected_contact_id = 0
        self.contact_mode = "new"
        self.form_error = ""
        self.form_success = ""
        self.f_salutation = ""
        self.f_first = ""
        self.f_last = ""
        self.f_title = ""
        self.f_role = ""
        self.f_work_phone = ""
        self.f_home_phone = ""
        self.f_email1 = ""
        self.f_email2 = ""
        self.f_is_primary = False

    def save_contact(self):
        self.form_error = ""
        self.form_success = ""
        if not (self.f_first.strip() or self.f_last.strip()):
            self.form_error = "First name or last name is required."
            return
        if self.f_is_primary:
            execute(
                "UPDATE Contacts SET IsPrimary = 0 WHERE TenantID = ?",
                (self.selected_tenant_id,),
                db=self.db,
            )
        if self.contact_mode == "edit":
            execute(
                "UPDATE Contacts SET Salutation=?, FirstName=?, LastName=?, Title=?, "
                "ContactRole=?, WorkPhone=?, HomePhone=?, Email1=?, Email2=?, IsPrimary=? "
                "WHERE ContactID=?",
                (
                    self.f_salutation.strip(),
                    self.f_first.strip(),
                    self.f_last.strip(),
                    self.f_title.strip(),
                    self.f_role.strip(),
                    self.f_work_phone.strip(),
                    self.f_home_phone.strip(),
                    self.f_email1.strip(),
                    self.f_email2.strip(),
                    self.f_is_primary,
                    self.selected_contact_id,
                ),
                db=self.db,
            )
            self.form_success = "Contact saved."
        else:
            execute(
                "INSERT INTO Contacts (TenantID, Salutation, FirstName, LastName, Title, "
                "ContactRole, WorkPhone, HomePhone, Email1, Email2, IsPrimary) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.selected_tenant_id,
                    self.f_salutation.strip(),
                    self.f_first.strip(),
                    self.f_last.strip(),
                    self.f_title.strip(),
                    self.f_role.strip(),
                    self.f_work_phone.strip(),
                    self.f_home_phone.strip(),
                    self.f_email1.strip(),
                    self.f_email2.strip(),
                    self.f_is_primary,
                ),
                db=self.db,
            )
            self.form_success = "Contact created."
        self.load_contacts()

    def delete_contact(self):
        if self.selected_contact_id == 0:
            return
        execute(
            "DELETE FROM Contacts WHERE ContactID = ?",
            (self.selected_contact_id,),
            db=self.db,
        )
        self.load_contacts()
        self.new_contact()

    def toggle_db(self):
        self.use_test_db = not self.use_test_db
        self.selected_tenant_id = 0
        self.load_tenants()

    # Form field setters
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


# ── UI helpers ────────────────────────────────────────────────────────────────
def badge(label: str, bg: str, color: str) -> rx.Component:
    return rx.box(
        rx.text(label, size="1", weight="bold", color=color),
        style={
            "background": bg,
            "border_radius": "999px",
            "padding": "2px 10px",
            "display": "inline-block",
        },
    )


def status_badge(status: str) -> rx.Component:
    return rx.cond(
        State.tenant_status == "Active",
        badge(State.tenant_status, "#e8f5e9", "#1b5e20"),
        rx.cond(
            State.tenant_status == "Prospect",
            badge(State.tenant_status, "#e8eaf6", "#1a237e"),
            badge(State.tenant_status, "#eeeeee", "#555555"),
        ),
    )


def tenant_header() -> rx.Component:
    return rx.box(
        rx.hstack(
            # Avatar
            rx.box(
                rx.text(
                    State.tenant_name[:2].upper(),
                    color="white",
                    weight="bold",
                    size="4",
                ),
                style={
                    "width": "52px",
                    "height": "52px",
                    "border_radius": "50%",
                    "background": BRAND_PRIMARY,
                    "display": "flex",
                    "align_items": "center",
                    "justify_content": "center",
                    "flex_shrink": "0",
                },
            ),
            # Name + badges + meta
            rx.vstack(
                rx.hstack(
                    rx.text(State.tenant_name, weight="bold", size="5", color=BRAND_DARK),
                    status_badge(State.tenant_status),
                    rx.box(
                        rx.text(
                            rx.cond(
                                State.tenant_suite != "",
                                State.tenant_suite + " · " + State.tenant_property,
                                State.tenant_property,
                            ),
                            size="1",
                            color=BRAND_PRIMARY,
                        ),
                        style={
                            "background": "#f0f4ff",
                            "border_radius": "999px",
                            "padding": "2px 10px",
                        },
                    ),
                    align="center",
                    spacing="2",
                    wrap="wrap",
                ),
                rx.text(
                    State.tenant_type + " · Tenant #" + State.selected_tenant_id.to_string(),
                    size="2",
                    color="#666",
                ),
                spacing="1",
                align_items="start",
            ),
            align="center",
            spacing="4",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}",
            "border_radius": "12px",
            "padding": "16px 20px",
            "margin_bottom": "16px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
        },
    )


def contact_row(contact: dict) -> rx.Component:
    cid = contact["ContactID"]
    first = contact.get("FirstName") or ""
    last = contact.get("LastName") or ""
    full_name = f"{first} {last}".strip() or f"Contact #{cid}"
    role = contact.get("ContactRole") or contact.get("Title") or ""
    email = contact.get("Email1") or ""
    phone = contact.get("WorkPhone") or ""
    is_primary = bool(contact.get("IsPrimary"))

    meta_parts = [x for x in [role, email, phone] if x]
    meta = " · ".join(meta_parts)

    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(full_name, weight="bold", size="2"),
                rx.cond(
                    is_primary,
                    badge("Primary", "#e8f5e9", "#1b5e20"),
                    rx.fragment(),
                ),
                align="center",
                spacing="2",
            )
        ),
        rx.table.cell(rx.text(role, size="2", color="#555")),
        rx.table.cell(rx.text(email, size="2", color="#555")),
        rx.table.cell(rx.text(phone, size="2", color="#555")),
        rx.table.cell(
            rx.button(
                "Edit",
                size="1",
                variant="soft",
                on_click=State.select_contact(cid),
                color_scheme="blue",
            )
        ),
        style=rx.cond(
            State.selected_contact_id == cid,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
        _hover={"background": "#f8f9ff"},
    )


def contacts_tab() -> rx.Component:
    return rx.vstack(
        # Table
        rx.box(
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
                rx.table.body(
                    rx.foreach(State.contacts, contact_row),
                ),
                width="100%",
                variant="surface",
            ),
            rx.cond(
                State.contacts.length() == 0,
                rx.text("No contacts yet.", color="#888", size="2"),
                rx.fragment(),
            ),
            width="100%",
        ),

        # Add new button
        rx.button(
            "+ New contact",
            on_click=State.new_contact,
            variant="outline",
            color_scheme="blue",
            size="2",
        ),

        rx.divider(),

        # Edit confirmation banner
        rx.cond(
            State.contact_mode == "edit",
            rx.box(
                rx.text(
                    "✏️ Editing: " + State.f_first + " " + State.f_last,
                    size="2",
                    weight="bold",
                    color=BRAND_DARK,
                ),
                style={
                    "background": "#f0f4ff",
                    "border": "1px solid #c5d0f0",
                    "border_left": f"4px solid {BRAND_PRIMARY}",
                    "border_radius": "6px",
                    "padding": "8px 14px",
                    "width": "100%",
                },
            ),
            rx.text(
                "New contact",
                size="3",
                weight="bold",
                color=BRAND_DARK,
            ),
        ),

        # Form
        rx.grid(
            rx.vstack(
                rx.text("Salutation", size="1", color="#666"),
                rx.input(
                    value=State.f_salutation,
                    on_change=State.set_f_salutation,
                    placeholder="Ms.",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("First name *", size="1", color="#666"),
                rx.input(
                    value=State.f_first,
                    on_change=State.set_f_first,
                    placeholder="First name",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Last name *", size="1", color="#666"),
                rx.input(
                    value=State.f_last,
                    on_change=State.set_f_last,
                    placeholder="Last name",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Job title", size="1", color="#666"),
                rx.input(
                    value=State.f_title,
                    on_change=State.set_f_title,
                    placeholder="Job title",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Role", size="1", color="#666"),
                rx.input(
                    value=State.f_role,
                    on_change=State.set_f_role,
                    placeholder="e.g. Property Manager",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Work phone", size="1", color="#666"),
                rx.input(
                    value=State.f_work_phone,
                    on_change=State.set_f_work_phone,
                    placeholder="Work phone",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Mobile / home", size="1", color="#666"),
                rx.input(
                    value=State.f_home_phone,
                    on_change=State.set_f_home_phone,
                    placeholder="Mobile / home",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Primary email", size="1", color="#666"),
                rx.input(
                    value=State.f_email1,
                    on_change=State.set_f_email1,
                    placeholder="email@example.com",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Secondary email", size="1", color="#666"),
                rx.input(
                    value=State.f_email2,
                    on_change=State.set_f_email2,
                    placeholder="Secondary email",
                    size="2",
                    width="100%",
                ),
                spacing="1", width="100%",
            ),
            columns="3",
            spacing="4",
            width="100%",
        ),

        # Primary checkbox
        rx.hstack(
            rx.switch(
                checked=State.f_is_primary,
                on_change=State.set_f_is_primary,
            ),
            rx.vstack(
                rx.text("Primary contact", size="2", weight="bold"),
                rx.text("Receives all primary correspondence for this tenant", size="1", color="#666"),
                spacing="0",
            ),
            align="center",
            spacing="3",
        ),

        # Error / success messages
        rx.cond(
            State.form_error != "",
            rx.callout(State.form_error, color="red", variant="soft"),
            rx.fragment(),
        ),
        rx.cond(
            State.form_success != "",
            rx.callout(State.form_success, color="green", variant="soft"),
            rx.fragment(),
        ),

        # Action buttons
        rx.hstack(
            rx.button(
                rx.cond(State.contact_mode == "edit", "Save contact", "Create contact"),
                on_click=State.save_contact,
                color_scheme="blue",
                size="2",
            ),
            rx.cond(
                State.contact_mode == "edit",
                rx.button(
                    "Delete contact",
                    on_click=State.delete_contact,
                    color_scheme="red",
                    variant="outline",
                    size="2",
                ),
                rx.fragment(),
            ),
            rx.button(
                "Cancel",
                on_click=State.new_contact,
                variant="ghost",
                size="2",
            ),
            spacing="3",
        ),

        spacing="4",
        width="100%",
        align_items="start",
    )


def tenant_selector() -> rx.Component:
    return rx.select(
        rx.foreach(
            State.tenants,
            lambda t: rx.option(
                t["TenantName"],
                value=t["TenantID"].to_string(),
            ),
        ),
        value=State.selected_tenant_id.to_string(),
        on_change=lambda v: State.select_tenant(int(v)),
        width="320px",
        size="2",
    )


def env_banner() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text(
                rx.cond(State.use_test_db, "🟢 TEST DATABASE", "🔴 PRODUCTION DATABASE"),
                size="2",
                weight="bold",
                color="white",
            ),
            rx.button(
                rx.cond(State.use_test_db, "Switch to Production", "Switch to Test"),
                on_click=State.toggle_db,
                size="1",
                variant="outline",
                color_scheme="gray",
            ),
            justify="between",
            align="center",
            width="100%",
        ),
        style={
            "background": rx.cond(State.use_test_db, "#2e7d32", "#c62828"),
            "padding": "8px 16px",
            "border_radius": "8px",
            "margin_bottom": "12px",
        },
    )


def index() -> rx.Component:
    return rx.box(
        # Top bar
        rx.box(
            style={
                "height": "6px",
                "background": f"linear-gradient(90deg, {BRAND_DARK} 0%, {BRAND_PRIMARY} 100%)",
                "margin_bottom": "24px",
            }
        ),

        rx.vstack(
            # App title
            rx.hstack(
                rx.heading("Lucid Property Manager", size="6", color=BRAND_DARK),
                rx.text("Tenant Detail", size="3", color="#888"),
                align="center",
                spacing="4",
            ),

            # Env banner
            env_banner(),

            # Tenant picker
            rx.hstack(
                rx.text("Tenant:", size="2", weight="bold", color="#444"),
                tenant_selector(),
                align="center",
                spacing="3",
            ),

            # Tenant header card
            tenant_header(),

            # Tabs
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Contacts", value="contacts"),
                    rx.tabs.trigger("Communications", value="communications"),
                    rx.tabs.trigger("Leases", value="leases"),
                    rx.tabs.trigger("Documents", value="documents"),
                ),
                rx.tabs.content(
                    contacts_tab(),
                    value="contacts",
                    padding_top="16px",
                ),
                rx.tabs.content(
                    rx.text("Communications — coming soon", color="#888"),
                    value="communications",
                    padding_top="16px",
                ),
                rx.tabs.content(
                    rx.text("Leases — coming soon", color="#888"),
                    value="leases",
                    padding_top="16px",
                ),
                rx.tabs.content(
                    rx.text("Documents — coming soon", color="#888"),
                    value="documents",
                    padding_top="16px",
                ),
                default_value="contacts",
                width="100%",
            ),

            spacing="4",
            width="100%",
            max_width="1100px",
            margin="0 auto",
            padding="0 24px 48px 24px",
        ),

        background=BRAND_LIGHT_BG,
        min_height="100vh",
        on_mount=State.load_tenants,
    )


app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        radius="medium",
    )
)
app.add_page(index, route="/")
