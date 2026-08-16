"""
Waiting List page — prospect pipeline for available suites.

Layout:
  - Filter bar (search, property, status)
  - Prospect list (left panel)
  - Edit/Create form (right panel)

Full CRUD with same fields as Streamlit page_waiting_list().

v7 — Full-page dynamic width tracks the resizable sidebar.
"""

import reflex as rx
import datetime

from LucidPM.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM.components.sidebar import page_shell


# Dynamic full-page width. Sidebar script maintains --lucid-sidebar-width.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"

PROSPECT_STATUSES = ["Waiting", "Contacted", "Application Submitted", "Converted to Applicant", "Closed"]
PROSPECT_SOURCES  = ["Messenger", "Phone", "Text", "Website", "Referral", "Walk in", "Other"]

STATUS_COLORS = {
    "Waiting":                "blue",
    "Contacted":              "orange",
    "Application Submitted":  "purple",
    "Converted to Tenant":    "green",
    "Closed":                 "gray",
}


# ── Data models ───────────────────────────────────────────────────────────────

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


class TallyPreviewRow(rx.Base):
    row_idx: int = 0
    name: str = ""
    business: str = ""
    email: str = ""
    phone: str = ""
    property_name: str = ""
    move_in: str = ""


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
        return "Edit Prospect" if self.selected_id > 0 and not self.is_new else "New Prospect"

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
            self.form_success = f"{self.f_name.strip()} added to Waiting List."
            self.is_new = False

        self._load_prospects()

    # ── Convert to Applicant ──────────────────────────────────────────────────

    convert_error: str = ""
    convert_success: str = ""

    def convert_to_applicant(self, prospect_id: int):
        """Convert a Waiting List Prospect to an Applicant in the Tenants table."""
        self.convert_error = ""
        self.convert_success = ""

        # Load prospect record
        rows = run_query(
            "SELECT p.*, pr.PropertyName FROM Prospects p "
            "LEFT JOIN Properties pr ON p.PropertyID = pr.PropertyID "
            "WHERE p.ProspectID = ?",
            (prospect_id,), db=self.db,
        )
        if not rows:
            self.convert_error = "Prospect not found."
            return
        p = rows[0]

        # Check not already converted
        if p.get("ConvertedTenantID"):
            self.convert_error = "This prospect has already been converted to an Applicant."
            return

        # Get Applicant status ID
        status_rows = run_query(
            "SELECT TenantStatusID FROM TenantStatuses WHERE TenantStatusName = 'Applicant'",
            db=self.db,
        )
        if not status_rows:
            self.convert_error = "Applicant status not found in TenantStatuses. Run the terminology migration SQL first."
            return
        applicant_status_id = int(status_rows[0]["TenantStatusID"])

        # Get default type ID
        type_rows = run_query(
            "SELECT TOP 1 TenantTypeID FROM TenantTypes ORDER BY TenantTypeID",
            db=self.db,
        )
        type_id = int(type_rows[0]["TenantTypeID"]) if type_rows else None

        tenant_name = str(p.get("ProspectName") or "").strip()
        prop_id = p.get("PropertyID")
        notes = (
            f"Converted from Waiting List.\n"
            f"Source: {p.get('Source') or ''}\n"
            f"Desired size: {p.get('DesiredSize') or ''}\n"
            f"Budget: {p.get('BudgetRange') or ''}\n"
            f"Notes: {p.get('Notes') or ''}"
        ).strip()

        now = datetime.datetime.now()

        # Create tenant record
        run_exec(
            "INSERT INTO Tenants (TenantName, Suite, PropertyID, TenantStatusID, "
            "TenantTypeID, Notes, ProspectID) VALUES (?,?,?,?,?,?,?)",
            (tenant_name, "", prop_id, applicant_status_id, type_id, notes, prospect_id),
            db=self.db,
        )

        # Get new TenantID
        new_tenant = run_query(
            "SELECT TOP 1 TenantID FROM Tenants WHERE ProspectID=? ORDER BY TenantID DESC",
            (prospect_id,), db=self.db,
        )
        if not new_tenant:
            self.convert_error = "Tenant record created but could not retrieve TenantID."
            return
        tenant_id = int(new_tenant[0]["TenantID"])

        # Update prospect record
        run_exec(
            "UPDATE Prospects SET ProspectStatus='Converted to Applicant', "
            "ConvertedTenantID=?, DateModified=? WHERE ProspectID=?",
            (tenant_id, now, prospect_id),
            db=self.db,
        )

        self.convert_success = f"{tenant_name} converted to Applicant (Tenant #{tenant_id})."
        self._load_prospects()

    # ── Tally import ──────────────────────────────────────────────────────────

    tally_show: bool = False
    tally_preview: list[TallyPreviewRow] = []   # typed rows for display
    tally_parsed: list[dict] = []               # full normalized rows for import
    tally_filename: str = ""
    tally_error: str = ""
    tally_result: str = ""
    tally_importing: bool = False
    tally_selected: list[bool] = []

    @rx.var
    def tally_selected_count(self) -> int:
        return sum(1 for v in self.tally_selected if v)

    def toggle_tally(self):
        self.tally_show = not self.tally_show
        self.tally_error = ""
        self.tally_result = ""

    async def handle_tally_upload(self, files: list[rx.UploadFile]):
        self.tally_error = ""
        self.tally_result = ""
        self.tally_preview = []
        self.tally_parsed = []
        self.tally_selected = []

        if not files:
            return

        file = files[0]
        self.tally_filename = file.filename or "upload.csv"

        try:
            file_bytes = await file.read()
            from LucidPM.pages.tally_import import parse_tally_csv, preview_rows
            parsed = parse_tally_csv(file_bytes)
            if not parsed:
                self.tally_error = "No rows found in CSV."
                return
            self.tally_parsed = parsed
            self.tally_selected = [True] * len(parsed)
            preview = preview_rows(parsed)
            self.tally_preview = [
                TallyPreviewRow(
                    row_idx=i,
                    name=r.get("Name", ""),
                    business=r.get("Business", ""),
                    email=r.get("Email", ""),
                    phone=r.get("Phone", ""),
                    property_name=r.get("Property", ""),
                    move_in=r.get("Move-in", ""),
                )
                for i, r in enumerate(preview)
            ]
        except Exception as ex:
            self.tally_error = f"Could not read CSV: {ex}"

    def run_tally_import(self):
        self.tally_error = ""
        self.tally_result = ""
        self.tally_importing = True

        if not self.tally_parsed:
            self.tally_error = "No data to import. Upload a CSV first."
            self.tally_importing = False
            return

        try:
            from LucidPM.pages.tally_import import import_tally_row
            imported = 0
            skipped = 0
            failures = []

            selected_rows = [
                row for i, row in enumerate(self.tally_parsed)
                if i < len(self.tally_selected) and self.tally_selected[i]
            ]
            if not selected_rows:
                self.tally_error = "No rows selected. Check at least one applicant to import."
                self.tally_importing = False
                return

            for i, row_norm in enumerate(selected_rows):
                try:
                    result, _ = import_tally_row(row_norm, self.db)
                    if result == "imported":
                        imported += 1
                    else:
                        skipped += 1
                except Exception as ex:
                    failures.append(f"Selected row {i + 1}: {ex}")

            parts = []
            if imported:
                parts.append(f"Imported {imported} application(s) as Prospects.")
            if skipped:
                parts.append(f"Skipped {skipped} (tenant already exists).")
            if failures:
                parts.append(f"{len(failures)} row(s) failed: " + "; ".join(failures[:5]))

            self.tally_result = " ".join(parts) if parts else "Nothing to import."
            if imported:
                self._load_prospects()
                self.tally_parsed = []
                self.tally_preview = []
                self.tally_selected = []
        except Exception as ex:
            self.tally_error = f"Import failed: {ex}"
        finally:
            self.tally_importing = False

    def toggle_tally_row(self, idx: int):
        updated = list(self.tally_selected)
        if 0 <= idx < len(updated):
            updated[idx] = not updated[idx]
        self.tally_selected = updated

    def select_all_tally_rows(self):
        self.tally_selected = [True] * len(self.tally_parsed)

    def clear_all_tally_rows(self):
        self.tally_selected = [False] * len(self.tally_parsed)

def status_badge(status: str) -> rx.Component:
    color = rx.match(
        status,
        ("Waiting", "blue"),
        ("Contacted", "orange"),
        ("Application Submitted", "purple"),
        ("Converted to Applicant", "green"),
        ("Closed", "gray"),
        "gray",
    )
    return rx.badge(status, color_scheme=color, variant="soft", size="1")


def prospect_list_item(p: ProspectRow) -> rx.Component:
    is_selected = WaitingListState.selected_id == p.prospect_id
    is_converted = p.status == "Converted to Applicant"
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
            # Convert to Applicant button — only show if not already converted
            rx.cond(
                ~is_converted,
                rx.button(
                    "→ Convert to Applicant",
                    on_click=WaitingListState.convert_to_applicant(p.prospect_id),
                    size="1",
                    variant="ghost",
                    color_scheme="green",
                    style={"font_size": "11px", "padding": "2px 6px"},
                ),
                rx.text("✓ Applicant created", size="1", color="#4caf50"),
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


def tally_preview_row_ui(r: TallyPreviewRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.checkbox(
                checked=WaitingListState.tally_selected[r.row_idx],
                on_change=WaitingListState.toggle_tally_row(r.row_idx),
                size="1",
            )
        ),
        rx.table.cell(rx.text(r.name, size="2")),
        rx.table.cell(rx.text(r.business, size="2", color="#666")),
        rx.table.cell(rx.text(r.email, size="2", color="#666")),
        rx.table.cell(rx.text(r.phone, size="2", color="#666")),
        rx.table.cell(rx.text(r.property_name, size="2", color="#666")),
        rx.table.cell(rx.text(r.move_in, size="2", color="#666")),
    )


def tally_import_section() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Toggle header
            rx.hstack(
                rx.text("📥 Import Tally applications", size="2", weight="bold", color=BRAND_DARK),
                rx.spacer(),
                rx.button(
                    rx.cond(WaitingListState.tally_show, "▲ Collapse", "▼ Expand"),
                    on_click=WaitingListState.toggle_tally,
                    variant="ghost", size="1", color_scheme="blue",
                ),
                align="center", width="100%",
            ),

            rx.cond(
                WaitingListState.tally_show,
                rx.vstack(
                    rx.text(
                        "Upload a Tally CSV export. Each row creates a Prospect tenant record. "
                        "The importer matches existing waiting list entries by phone or email, "
                        "creates a primary contact, and stores SSN/DL encrypted.",
                        size="1", color="#666",
                    ),

                    # Upload zone
                    rx.upload(
                        rx.vstack(
                            rx.text("📎 Drop CSV here or click to browse", size="2", color="#666"),
                            rx.text(
                                rx.cond(
                                    WaitingListState.tally_filename != "",
                                    "Selected: " + WaitingListState.tally_filename,
                                    "Accepts .csv files",
                                ),
                                size="1", color="#999",
                            ),
                            spacing="1", align_items="center",
                        ),
                        id="tally_upload",
                        accept={".csv": ["text/csv", "application/csv"]},
                        on_drop=WaitingListState.handle_tally_upload(
                            rx.upload_files(upload_id="tally_upload")
                        ),
                        style={
                            "border": "2px dashed #c5d0f0",
                            "border_radius": "8px",
                            "padding": "20px",
                            "text_align": "center",
                            "cursor": "pointer",
                            "width": "100%",
                            "_hover": {"border_color": BRAND_PRIMARY, "background": "#f4f6fa"},
                        },
                    ),

                    # Error
                    rx.cond(
                        WaitingListState.tally_error != "",
                        rx.callout(WaitingListState.tally_error, color="red", variant="soft"),
                        rx.fragment(),
                    ),

                    # Preview table
                    rx.cond(
                        WaitingListState.tally_preview.length() > 0,
                        rx.vstack(
                            rx.text(
                                WaitingListState.tally_preview.length().to_string() + " rows detected — preview (first rows shown):",
                                size="2", weight="bold", color=BRAND_DARK,
                            ),
                            rx.hstack(
                                rx.button(
                                    "Select all", size="1", variant="ghost", color_scheme="blue",
                                    on_click=WaitingListState.select_all_tally_rows,
                                ),
                                rx.button(
                                    "Clear all", size="1", variant="ghost", color_scheme="gray",
                                    on_click=WaitingListState.clear_all_tally_rows,
                                ),
                                spacing="2",
                            ),
                            rx.box(
                                rx.table.root(
                                    rx.table.header(
                                        rx.table.row(
                                            rx.table.column_header_cell(""),
                                            rx.table.column_header_cell("Name"),
                                            rx.table.column_header_cell("Business"),
                                            rx.table.column_header_cell("Email"),
                                            rx.table.column_header_cell("Phone"),
                                            rx.table.column_header_cell("Property"),
                                            rx.table.column_header_cell("Move-in"),
                                        )
                                    ),
                                    rx.table.body(
                                        rx.foreach(WaitingListState.tally_preview, tally_preview_row_ui)
                                    ),
                                    variant="surface", width="100%",
                                ),
                                overflow_x="auto", width="100%",
                            ),

                            # Import button
                            rx.hstack(
                                rx.button(
                                    rx.cond(
                                        WaitingListState.tally_importing,
                                        "Importing...",
                                        "Import selected (" + WaitingListState.tally_selected_count.to_string() + ")",
                                    ),
                                    on_click=WaitingListState.run_tally_import,
                                    color_scheme="blue", size="2",
                                    loading=WaitingListState.tally_importing,
                                    disabled=WaitingListState.tally_selected_count == 0,
                                ),
                                rx.cond(
                                    WaitingListState.tally_result != "",
                                    rx.callout(WaitingListState.tally_result,
                                               color=rx.cond(
                                                   WaitingListState.tally_result.contains("failed"),
                                                   "red", "green"
                                               ),
                                               variant="soft"),
                                    rx.fragment(),
                                ),
                                spacing="3", align="center",
                            ),
                            spacing="3", width="100%", align_items="start",
                        ),
                        rx.fragment(),
                    ),

                    spacing="3", width="100%", align_items="start",
                ),
                rx.fragment(),
            ),

            spacing="2", width="100%", align_items="start",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_radius": "10px",
            "padding": "16px 20px",
            "margin_top": "16px",
        },
    )


RESIZER_SCRIPT = """
(function() {
    function initResizer() {
        var resizer = document.getElementById('wl-panel-resizer');
        var leftPanel = document.getElementById('wl-list-panel');
        if (!resizer || !leftPanel) {
            setTimeout(initResizer, 300);
            return;
        }
        var isResizing = false;
        var startX = 0;
        var startWidth = 0;

        resizer.addEventListener('mousedown', function(e) {
            isResizing = true;
            startX = e.clientX;
            startWidth = leftPanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            var delta = e.clientX - startX;
            var newWidth = Math.min(Math.max(startWidth + delta, 260), 700);
            leftPanel.style.width = newWidth + 'px';
            leftPanel.style.minWidth = newWidth + 'px';
        });

        document.addEventListener('mouseup', function() {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }
    initResizer();
})();
"""


def waiting_list_content() -> rx.Component:
    return rx.box(
        rx.script(RESIZER_SCRIPT),
        rx.hstack(
            # ── Left panel: list ────────────────────────────────────────────────
            rx.box(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.heading("Waiting List", size="4", color=BRAND_DARK),
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

                    # Convert feedback
                    rx.cond(
                        WaitingListState.convert_success != "",
                        rx.callout(WaitingListState.convert_success, color="green", variant="soft", size="1"),
                        rx.fragment(),
                    ),
                    rx.cond(
                        WaitingListState.convert_error != "",
                        rx.callout(WaitingListState.convert_error, color="red", variant="soft", size="1"),
                        rx.fragment(),
                    ),

                    # List
                    rx.foreach(WaitingListState.filtered_prospects, prospect_list_item),

                    spacing="3", width="100%", align_items="start",
                ),
                id="wl-list-panel",
                style={
                    "width": "380px",
                    "min_width": "380px",
                    "max_height": "calc(100vh - 80px)",
                    "overflow_y": "auto",
                    "background": "white",
                    "border": "1px solid #dde3f0",
                    "border_radius": "12px",
                    "padding": "20px",
                    "flex_shrink": "0",
                },
            ),

            # ── Drag handle ──────────────────────────────────────────────────
            rx.box(
                rx.box(style={"width": "4px", "height": "40px",
                              "background": "#c5d0f0", "border_radius": "2px"}),
                id="wl-panel-resizer",
                style={
                    "width": "12px", "min_width": "12px", "cursor": "col-resize",
                    "display": "flex", "align_items": "center", "justify_content": "center",
                    "align_self": "stretch", "flex_shrink": "0",
                    "_hover": {"background": "#f0f4ff"},
                    "border_radius": "4px", "transition": "background 0.15s",
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

                    # Row 4: dates
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

                    # Feedback + Save
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
                            "Save Prospect",
                            "Add to Waiting List",
                        ),
                        on_click=WaitingListState.save_prospect,
                        color_scheme="blue", size="2",
                    ),

                    spacing="4", width="100%", align_items="start",
                ),
                style={
                    "flex": "1",
                    "min_width": "0",
                    "max_height": "calc(100vh - 80px)",
                    "overflow_y": "auto",
                    "padding": "24px 32px",
                },
            ),

            spacing="0",
            width="100%",
            align_items="start",
        ),

        # Tally import — below the split panel, full width
        tally_import_section(),

        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
        flex_shrink="0",
        style={
            "box_sizing": "border-box",
            "overflow_x": "hidden",
        },
    )


def waiting_list_page() -> rx.Component:
    return page_shell(waiting_list_content(), current_path="/waiting-list")
