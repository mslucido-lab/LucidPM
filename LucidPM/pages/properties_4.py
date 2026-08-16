"""
Manage Properties page — list + inline form, no detail panel needed.
Properties are low-volume (2-10 per user), so a simple list + form
below the table is the right pattern (no split panel required).
"""

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# ── Data model ────────────────────────────────────────────────────────────────

class PropertySummary(rx.Base):
    property_id: int = 0
    property_name: str = ""
    address: str = ""
    tax_account: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class PropertyState(AppState):

    # List
    property_list: list[PropertySummary] = []

    # Selected / form mode
    selected_property_id: int = 0
    property_mode: str = "new"   # "new" | "edit"

    # Form fields
    f_name: str = ""
    f_address1: str = ""
    f_address2: str = ""
    f_city: str = ""
    f_state: str = ""
    f_zip: str = ""
    f_tax: str = ""

    form_error: str = ""
    form_success: str = ""

    @rx.var
    def form_title(self) -> str:
        return "Save property" if self.property_mode == "edit" else "New property"

    @rx.var
    def editing_banner_text(self) -> str:
        return f"Editing: {self.f_name}"

    def on_load(self):
        self.load_property_list()
        self.new_property()

    def load_property_list(self):
        rows = run_query(
            "SELECT PropertyID, PropertyName, "
            "ISNULL(PropertyAddress1,'') + CASE WHEN PropertyCity IS NOT NULL "
            "THEN ', ' + PropertyCity ELSE '' END + "
            "CASE WHEN PropertyState IS NOT NULL THEN ', ' + PropertyState ELSE '' END AS Address, "
            "ISNULL(TaxAccountNumber,'') AS TaxAccountNumber "
            "FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_list = [
            PropertySummary(
                property_id=r["PropertyID"],
                property_name=str(r.get("PropertyName") or ""),
                address=str(r.get("Address") or ""),
                tax_account=str(r.get("TaxAccountNumber") or ""),
            )
            for r in rows
        ]

    def select_property(self, property_id: int):
        self.selected_property_id = property_id
        self.property_mode = "edit"
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT PropertyName, PropertyAddress1, PropertyAddress2, "
            "PropertyCity, PropertyState, PropertyZip, TaxAccountNumber "
            "FROM Properties WHERE PropertyID = ?",
            (property_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.f_name     = str(r.get("PropertyName") or "")
        self.f_address1 = str(r.get("PropertyAddress1") or "")
        self.f_address2 = str(r.get("PropertyAddress2") or "")
        self.f_city     = str(r.get("PropertyCity") or "")
        self.f_state    = str(r.get("PropertyState") or "")
        self.f_zip      = str(r.get("PropertyZip") or "")
        self.f_tax      = str(r.get("TaxAccountNumber") or "")

    def new_property(self):
        self.selected_property_id = 0
        self.property_mode = "new"
        self.form_error = ""
        self.form_success = ""
        self.f_name = self.f_address1 = self.f_address2 = ""
        self.f_city = self.f_state = self.f_zip = self.f_tax = ""

    def save_property(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_name.strip():
            self.form_error = "Property name is required."
            return
        if self.property_mode == "edit":
            run_exec(
                "UPDATE Properties SET PropertyName=?, PropertyAddress1=?, PropertyAddress2=?, "
                "PropertyCity=?, PropertyState=?, PropertyZip=?, TaxAccountNumber=? "
                "WHERE PropertyID=?",
                (self.f_name.strip(), self.f_address1.strip(), self.f_address2.strip(),
                 self.f_city.strip(), self.f_state.strip(), self.f_zip.strip(),
                 self.f_tax.strip(), self.selected_property_id),
                db=self.db,
            )
            self.form_success = "Property saved."
        else:
            run_exec(
                "INSERT INTO Properties (PropertyName, PropertyAddress1, PropertyAddress2, "
                "PropertyCity, PropertyState, PropertyZip, TaxAccountNumber) "
                "VALUES (?,?,?,?,?,?,?)",
                (self.f_name.strip(), self.f_address1.strip(), self.f_address2.strip(),
                 self.f_city.strip(), self.f_state.strip(), self.f_zip.strip(),
                 self.f_tax.strip()),
                db=self.db,
            )
            self.form_success = "Property created."
            self.new_property()
        self.load_property_list()

    # Setters
    def set_f_name(self, v): self.f_name = v
    def set_f_address1(self, v): self.f_address1 = v
    def set_f_address2(self, v): self.f_address2 = v
    def set_f_city(self, v): self.f_city = v
    def set_f_state(self, v): self.f_state = v
    def set_f_zip(self, v): self.f_zip = v
    def set_f_tax(self, v): self.f_tax = v


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

def property_row(p: PropertySummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(p.property_name, size="2", weight="bold")),
        rx.table.cell(rx.text(p.address, size="2", color="#555")),
        rx.table.cell(rx.text(p.tax_account, size="2", color="#555")),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=PropertyState.select_property(p.property_id))
        ),
        style=rx.cond(
            PropertyState.selected_property_id == p.property_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


# ── Form ─────────────────────────────────────────────────────────────────────

def property_form() -> rx.Component:
    return rx.vstack(
        rx.divider(),
        rx.cond(
            PropertyState.property_mode == "edit",
            edit_banner(PropertyState.editing_banner_text),
            rx.text("New property", size="3", weight="bold", color=BRAND_DARK),
        ),
        # Property name — full width
        rx.vstack(
            rx.text("Property name *", size="1", color="#666"),
            rx.input(value=PropertyState.f_name, on_change=PropertyState.set_f_name,
                     placeholder="e.g. Broadway Building", size="2", width="100%"),
            spacing="1", width="100%",
        ),
        # Address row 1: address1, address2
        rx.grid(
            rx.vstack(
                rx.text("Address line 1", size="1", color="#666"),
                rx.input(value=PropertyState.f_address1, on_change=PropertyState.set_f_address1,
                         placeholder="Street address", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Address line 2", size="1", color="#666"),
                rx.input(value=PropertyState.f_address2, on_change=PropertyState.set_f_address2,
                         placeholder="Suite, unit, etc.", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="2", spacing="4", width="100%",
        ),
        # Address row 2: city, state, zip
        rx.grid(
            rx.vstack(
                rx.text("City", size="1", color="#666"),
                rx.input(value=PropertyState.f_city, on_change=PropertyState.set_f_city,
                         placeholder="City", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("State", size="1", color="#666"),
                rx.input(value=PropertyState.f_state,
                         on_change=PropertyState.set_f_state,
                         placeholder="TX", max_length=2,
                         size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("ZIP code", size="1", color="#666"),
                rx.input(value=PropertyState.f_zip, on_change=PropertyState.set_f_zip,
                         placeholder="ZIP", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="3", spacing="4", width="100%",
        ),
        # Tax account — half width
        rx.vstack(
            rx.text("Tax account number", size="1", color="#666"),
            rx.input(value=PropertyState.f_tax, on_change=PropertyState.set_f_tax,
                     placeholder="County tax account #", size="2", width="50%"),
            spacing="1", width="100%",
        ),
        # Feedback
        rx.cond(PropertyState.form_error != "",
                rx.callout(PropertyState.form_error, color="red", variant="soft"),
                rx.fragment()),
        rx.cond(PropertyState.form_success != "",
                rx.callout(PropertyState.form_success, color="green", variant="soft"),
                rx.fragment()),
        # Buttons
        rx.hstack(
            rx.button(
                rx.cond(PropertyState.property_mode == "edit", "Save property", "Create property"),
                on_click=PropertyState.save_property, color_scheme="blue", size="2",
            ),
            rx.button("Cancel", on_click=PropertyState.new_property, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Page content ──────────────────────────────────────────────────────────────

def properties_content() -> rx.Component:
    return rx.box(
        # Page heading
        rx.hstack(
            rx.heading("Manage properties", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.button("+ New property", on_click=PropertyState.new_property,
                      variant="outline", color_scheme="blue", size="2"),
            align="center", width="100%",
            padding_bottom="16px",
        ),
        # Split panel — list left, form right
        rx.hstack(
            # Left: list
            rx.box(
                rx.cond(
                    PropertyState.property_list.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Property name"),
                                rx.table.column_header_cell("Address"),
                                rx.table.column_header_cell("Tax account"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(PropertyState.property_list, property_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No properties found.", color="#888", size="2"),
                ),
                style={
                    "width": "480px",
                    "min_width": "480px",
                    "max_height": "calc(100vh - 120px)",
                    "overflow_y": "auto",
                    "background": "white",
                    "border": "1px solid #dde3f0",
                    "border_radius": "12px",
                    "padding": "20px",
                    "flex_shrink": "0",
                },
            ),
            # Right: form
            rx.box(
                property_form(),
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
            spacing="4",
            width="100%",
            align_items="start",
        ),
        padding="24px",
        width="100%",
    )


def properties_page() -> rx.Component:
    return page_shell(properties_content(), current_path="/admin/properties")
