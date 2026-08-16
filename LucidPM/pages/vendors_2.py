"""
Manage Vendors page — split panel: list left, form right.
"""

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# ── Data model ────────────────────────────────────────────────────────────────

class VendorSummary(rx.Base):
    vendor_id: int = 0
    vendor_name: str = ""
    category: str = ""
    phone: str = ""
    email: str = ""
    active: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class VendorState(AppState):

    # List + filters
    vendor_list: list[VendorSummary] = []
    category_filter: str = "All"
    active_filter: str = "All"
    category_options: list[str] = ["All"]

    # Category lookup
    _category_names: list[str] = []
    _category_ids: list[int] = []

    # Selected / form mode
    selected_vendor_id: int = 0
    vendor_mode: str = "new"   # "new" | "edit"

    # Form fields
    f_name: str = ""
    f_category: str = ""
    f_phone: str = ""
    f_email: str = ""
    f_active: bool = True
    f_notes: str = ""

    form_error: str = ""
    form_success: str = ""

    @rx.var
    def editing_banner_text(self) -> str:
        return f"Editing: {self.f_name}"

    def on_load(self):
        self._load_category_options()
        self.load_vendor_list()
        self.new_vendor()

    def _load_category_options(self):
        rows = run_query(
            "SELECT WorkItemCategoryID, CategoryName FROM WorkItemCategories "
            "WHERE IsActive = 1 ORDER BY SortOrder, CategoryName",
            db=self.db,
        )
        self._category_names = [str(r["CategoryName"]) for r in rows]
        self._category_ids   = [int(r["WorkItemCategoryID"]) for r in rows]
        self.category_options = ["All"] + self._category_names

    def load_vendor_list(self):
        conditions = []
        params = []
        if self.category_filter != "All":
            conditions.append("wc.CategoryName = ?")
            params.append(self.category_filter)
        if self.active_filter == "Yes":
            conditions.append("v.IsActive = 1")
        elif self.active_filter == "No":
            conditions.append("v.IsActive = 0")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = run_query(
            "SELECT v.VendorID, v.VendorName, wc.CategoryName, "
            "ISNULL(v.Phone,'') AS Phone, ISNULL(v.Email,'') AS Email, v.IsActive "
            "FROM Vendors v "
            "LEFT JOIN WorkItemCategories wc ON v.VendorCategoryID = wc.WorkItemCategoryID "
            f"{where} ORDER BY v.VendorName",
            tuple(params), db=self.db,
        )
        self.vendor_list = [
            VendorSummary(
                vendor_id=int(r["VendorID"]),
                vendor_name=str(r.get("VendorName") or ""),
                category=str(r.get("CategoryName") or ""),
                phone=str(r.get("Phone") or ""),
                email=str(r.get("Email") or ""),
                active="Yes" if r.get("IsActive") else "No",
            )
            for r in rows
        ]

    def set_category_filter(self, v: str):
        self.category_filter = v
        self.load_vendor_list()

    def set_active_filter(self, v: str):
        self.active_filter = v
        self.load_vendor_list()

    def select_vendor(self, vendor_id: int):
        self.selected_vendor_id = vendor_id
        self.vendor_mode = "edit"
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT v.VendorName, wc.CategoryName, v.Phone, v.Email, v.IsActive, v.Notes "
            "FROM Vendors v "
            "LEFT JOIN WorkItemCategories wc ON v.VendorCategoryID = wc.WorkItemCategoryID "
            "WHERE v.VendorID = ?",
            (vendor_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.f_name     = str(r.get("VendorName") or "")
        self.f_category = str(r.get("CategoryName") or (self._category_names[0] if self._category_names else ""))
        self.f_phone    = str(r.get("Phone") or "")
        self.f_email    = str(r.get("Email") or "")
        self.f_active   = bool(r.get("IsActive"))
        self.f_notes    = str(r.get("Notes") or "")

    def new_vendor(self):
        self.selected_vendor_id = 0
        self.vendor_mode = "new"
        self.form_error = ""
        self.form_success = ""
        self.f_name = self.f_phone = self.f_email = self.f_notes = ""
        self.f_category = self._category_names[0] if self._category_names else ""
        self.f_active = True

    def save_vendor(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_name.strip():
            self.form_error = "Vendor name is required."
            return
        if not self.f_category:
            self.form_error = "Type is required."
            return
        if self.f_category in self._category_names:
            cat_id = self._category_ids[self._category_names.index(self.f_category)]
        else:
            self.form_error = "Invalid type selection."
            return
        import datetime
        now = datetime.datetime.now()
        if self.vendor_mode == "edit":
            run_exec(
                "UPDATE Vendors SET VendorName=?, VendorCategoryID=?, Phone=?, Email=?, "
                "IsActive=?, Notes=?, UpdatedDate=? WHERE VendorID=?",
                (self.f_name.strip(), cat_id, self.f_phone.strip(), self.f_email.strip(),
                 self.f_active, self.f_notes, now, self.selected_vendor_id),
                db=self.db,
            )
            run_exec("UPDATE WorkItems SET VendorName=? WHERE VendorID=?",
                     (self.f_name.strip(), self.selected_vendor_id), db=self.db)
            self.form_success = "Vendor saved."
        else:
            run_exec(
                "INSERT INTO Vendors (VendorName, VendorCategoryID, Phone, Email, "
                "IsActive, Notes, CreatedDate, UpdatedDate) VALUES (?,?,?,?,?,?,?,?)",
                (self.f_name.strip(), cat_id, self.f_phone.strip(), self.f_email.strip(),
                 self.f_active, self.f_notes, now, now),
                db=self.db,
            )
            self.form_success = "Vendor created."
            self.new_vendor()
        self.load_vendor_list()

    # Setters
    def set_f_name(self, v): self.f_name = v
    def set_f_category(self, v): self.f_category = v
    def set_f_phone(self, v): self.f_phone = v
    def set_f_email(self, v): self.f_email = v
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

def vendor_row(v: VendorSummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(v.vendor_name, size="2", weight="bold")),
        rx.table.cell(rx.text(v.category, size="2", color="#555")),
        rx.table.cell(rx.text(v.phone, size="2", color="#555")),
        rx.table.cell(
            rx.cond(
                v.active == "Yes",
                rx.badge("Active", color_scheme="green", variant="soft"),
                rx.badge("Inactive", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=VendorState.select_vendor(v.vendor_id))
        ),
        style=rx.cond(
            VendorState.selected_vendor_id == v.vendor_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


# ── Form ─────────────────────────────────────────────────────────────────────

def vendor_form() -> rx.Component:
    return rx.vstack(
        rx.cond(
            VendorState.vendor_mode == "edit",
            edit_banner(VendorState.editing_banner_text),
            rx.text("New vendor", size="3", weight="bold", color=BRAND_DARK),
        ),
        rx.vstack(
            rx.text("Vendor name *", size="1", color="#666"),
            rx.input(value=VendorState.f_name, on_change=VendorState.set_f_name,
                     placeholder="Company or person name", size="2", width="100%"),
            spacing="1", width="100%",
        ),
        rx.vstack(
            rx.text("Type *", size="1", color="#666"),
            rx.select(VendorState._category_names,
                      value=VendorState.f_category,
                      on_change=VendorState.set_f_category, size="2", width="100%"),
            spacing="1", width="100%",
        ),
        rx.grid(
            rx.vstack(
                rx.text("Phone", size="1", color="#666"),
                rx.input(value=VendorState.f_phone, on_change=VendorState.set_f_phone,
                         placeholder="Phone number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Email", size="1", color="#666"),
                rx.input(value=VendorState.f_email, on_change=VendorState.set_f_email,
                         placeholder="email@example.com", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="2", spacing="4", width="100%",
        ),
        rx.vstack(
            rx.text("Notes", size="1", color="#666"),
            rx.text_area(value=VendorState.f_notes, on_change=VendorState.set_f_notes,
                         placeholder="Additional notes...", width="100%", rows="3"),
            spacing="1", width="100%",
        ),
        rx.hstack(
            rx.switch(checked=VendorState.f_active, on_change=VendorState.set_f_active),
            rx.vstack(
                rx.text("Active", size="2", weight="bold"),
                rx.text("Inactive vendors won't appear in work item dropdowns", size="1", color="#666"),
                spacing="0",
            ),
            align="center", spacing="3",
        ),
        rx.cond(VendorState.form_error != "",
                rx.callout(VendorState.form_error, color="red", variant="soft"),
                rx.fragment()),
        rx.cond(VendorState.form_success != "",
                rx.callout(VendorState.form_success, color="green", variant="soft"),
                rx.fragment()),
        rx.hstack(
            rx.button(
                rx.cond(VendorState.vendor_mode == "edit", "Save vendor", "Create vendor"),
                on_click=VendorState.save_vendor, color_scheme="blue", size="2",
            ),
            rx.button("Cancel", on_click=VendorState.new_vendor, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Page content ──────────────────────────────────────────────────────────────

def vendors_content() -> rx.Component:
    return rx.box(
        # Page heading + filters + new button
        rx.hstack(
            rx.heading("Manage vendors", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.select(
                VendorState.category_options,
                value=VendorState.category_filter,
                on_change=VendorState.set_category_filter,
                size="1", placeholder="Type",
            ),
            rx.select(
                ["All", "Yes", "No"],
                value=VendorState.active_filter,
                on_change=VendorState.set_active_filter,
                size="1", placeholder="Active",
            ),
            rx.button("+ New vendor", on_click=VendorState.new_vendor,
                      variant="outline", color_scheme="blue", size="2"),
            align="center", spacing="2", width="100%",
            padding_bottom="16px",
        ),
        # Split panel
        rx.hstack(
            # Left: list
            rx.box(
                rx.cond(
                    VendorState.vendor_list.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Vendor name"),
                                rx.table.column_header_cell("Type"),
                                rx.table.column_header_cell("Phone"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(VendorState.vendor_list, vendor_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No vendors found.", color="#888", size="2"),
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
                vendor_form(),
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


def vendors_page() -> rx.Component:
    return page_shell(vendors_content(), current_path="/admin/vendors")
