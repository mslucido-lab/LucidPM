"""
Manage Vendors page — split panel: list left, form right.

v7 — Adds outbound vendor email compose modal using shared send_email().
"""

# v9 - Removes inline Edit column; row click opens edit-ready form directly.
# v8 - Responsive page width and stable split-panel resizer.

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# Page width constant — dynamic sidebar width + page_shell padding (32px each side = 64px)
# Sidebar script updates --lucid-sidebar-width when resized
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"


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

    # Category lookup (public so UI can bind to them)
    category_names: list[str] = []
    category_ids: list[int] = []

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

    # Compose email modal
    compose_email_open: bool = False
    compose_to: str = ""
    compose_subject: str = ""
    compose_body: str = ""
    compose_sending: bool = False
    compose_error: str = ""
    compose_success: str = ""

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
        self.category_names = [str(r["CategoryName"]) for r in rows]
        self.category_ids   = [int(r["WorkItemCategoryID"]) for r in rows]
        self.category_options = ["All"] + self.category_names

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
        self.f_category = str(r.get("CategoryName") or (self.category_names[0] if self.category_names else ""))
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
        self.f_category = self.category_names[0] if self.category_names else ""
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
        if self.f_category in self.category_names:
            cat_id = self.category_ids[self.category_names.index(self.f_category)]
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

    def delete_vendor(self):
        self.form_error = ""
        if self.selected_vendor_id == 0:
            return
        in_use = run_query(
            "SELECT TOP 1 WorkItemID FROM WorkItems WHERE VendorID = ?",
            (self.selected_vendor_id,), db=self.db,
        )
        if in_use:
            self.form_error = "Cannot delete — this vendor is referenced by work items. Mark it inactive instead."
            return
        run_exec("DELETE FROM Vendors WHERE VendorID = ?",
                 (self.selected_vendor_id,), db=self.db)
        self.load_vendor_list()
        self.new_vendor()

    def open_compose_email(self):
        """Pre-populate To address from Vendors.Email and open modal."""
        self.compose_error = ""
        self.compose_success = ""
        self.compose_subject = ""
        self.compose_body = ""
        self.compose_sending = False

        if not self.selected_vendor_id or int(self.selected_vendor_id) <= 0:
            self.compose_to = ""
            self.compose_email_open = True
            return

        rows = run_query(
            "SELECT TOP 1 Email FROM dbo.Vendors WHERE VendorID = ?",
            (int(self.selected_vendor_id),),
            db=self.db,
        )
        self.compose_to = str(rows[0].get("Email") or "") if rows else ""
        self.compose_email_open = True

    def close_compose_email(self):
        self.compose_email_open = False
        self.compose_error = ""
        self.compose_success = ""
        self.compose_sending = False

    def set_compose_to(self, v: str):
        self.compose_to = v

    def set_compose_subject(self, v: str):
        self.compose_subject = v

    def set_compose_body(self, v: str):
        self.compose_body = v

    def send_compose_email(self):
        """Validate and send. No comm log entry for vendor emails."""
        from LucidPM_Reflex.state import send_email

        self.compose_error = ""
        self.compose_success = ""

        if not self.compose_to.strip():
            self.compose_error = "To address is required."
            return
        if not self.compose_subject.strip():
            self.compose_error = "Subject is required."
            return
        if not self.compose_body.strip():
            self.compose_error = "Message body is required."
            return
        if not self.selected_vendor_id or int(self.selected_vendor_id) <= 0:
            self.compose_error = "No vendor selected."
            return

        self.compose_sending = True

        try:
            send_email(
                to_address=self.compose_to.strip(),
                subject=self.compose_subject.strip(),
                body=self.compose_body.strip(),
                db=self.db,
            )
        except Exception as ex:
            self.compose_error = f"Failed to send: {ex}"
            self.compose_sending = False
            return

        self.compose_success = "Email sent."
        self.compose_sending = False
        self.compose_email_open = False

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
        on_click=VendorState.select_vendor(v.vendor_id),
        style=rx.cond(
            VendorState.selected_vendor_id == v.vendor_id,
            {"background": "#f0f4ff", "cursor": "pointer"},
            {"background": "white", "cursor": "pointer", "_hover": {"background": "#f8fafc"}},
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
            rx.cond(
                VendorState.category_names.length() > 0,
                rx.select(VendorState.category_names,
                          value=VendorState.f_category,
                          on_change=VendorState.set_f_category, size="2", width="100%"),
                rx.text("Loading types...", size="2", color="#888"),
            ),
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
            rx.cond(
                VendorState.selected_vendor_id > 0,
                rx.button(
                    "Send Email",
                    on_click=VendorState.open_compose_email,
                    variant="outline",
                    color_scheme="blue",
                    size="2",
                ),
                rx.fragment(),
            ),
            rx.cond(
                VendorState.vendor_mode == "edit",
                rx.button("Delete vendor", on_click=VendorState.delete_vendor,
                          color_scheme="red", variant="outline", size="2"),
                rx.fragment(),
            ),
            rx.button("Cancel", on_click=VendorState.new_vendor, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="4", width="100%", align_items="start",
    )


VENDORS_RESIZER_SCRIPT = """
(function() {
    var cleanupName = '__lucid_vendors_resizer_cleanup';

    function installResizer() {
        if (window[cleanupName]) {
            try { window[cleanupName](); } catch (e) {}
        }

        var isResizing = false;
        var startX = 0;
        var startWidth = 0;
        var leftPanel = null;

        function getResizerFromEvent(e) {
            var path = e.composedPath ? e.composedPath() : [];
            for (var i = 0; i < path.length; i++) {
                if (path[i] && path[i].id === 'vendors-panel-resizer') {
                    return path[i];
                }
            }
            var target = e.target;
            return target && target.closest ? target.closest('#vendors-panel-resizer') : null;
        }

        function startResize(e) {
            var resizer = getResizerFromEvent(e);
            if (!resizer) return;
            leftPanel = document.getElementById('vendors-list-panel');
            if (!leftPanel) return;
            isResizing = true;
            startX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            startWidth = leftPanel.offsetWidth || 580;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            if (resizer.setPointerCapture && e.pointerId) {
                try { resizer.setPointerCapture(e.pointerId); } catch (err) {}
            }
            e.preventDefault();
            e.stopPropagation();
        }

        function moveResize(e) {
            if (!isResizing || !leftPanel) return;
            var clientX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            var newWidth = Math.min(Math.max(startWidth + (clientX - startX), 260), 860);
            leftPanel.style.width = newWidth + 'px';
            leftPanel.style.minWidth = newWidth + 'px';
            leftPanel.style.maxWidth = newWidth + 'px';
            e.preventDefault();
        }

        function stopResize() {
            if (!isResizing) return;
            isResizing = false;
            leftPanel = null;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }

        document.addEventListener('pointerdown', startResize, true);
        document.addEventListener('pointermove', moveResize, true);
        document.addEventListener('pointerup', stopResize, true);
        document.addEventListener('pointercancel', stopResize, true);
        document.addEventListener('mousedown', startResize, true);
        document.addEventListener('mousemove', moveResize, true);
        document.addEventListener('mouseup', stopResize, true);

        window[cleanupName] = function() {
            document.removeEventListener('pointerdown', startResize, true);
            document.removeEventListener('pointermove', moveResize, true);
            document.removeEventListener('pointerup', stopResize, true);
            document.removeEventListener('pointercancel', stopResize, true);
            document.removeEventListener('mousedown', startResize, true);
            document.removeEventListener('mousemove', moveResize, true);
            document.removeEventListener('mouseup', stopResize, true);
        };
    }

    installResizer();

    var observer = new MutationObserver(function() {
        if (document.getElementById('vendors-panel-resizer') && document.getElementById('vendors-list-panel')) {
            installResizer();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    setTimeout(installResizer, 300);
    setTimeout(installResizer, 1000);
    setTimeout(installResizer, 2500);
})();
"""


def vendor_compose_email_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("Send Email to Vendor"),
                rx.cond(
                    VendorState.compose_error != "",
                    rx.callout.root(
                        rx.callout.text(VendorState.compose_error),
                        color_scheme="red",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.vstack(
                    rx.text("To", size="2", color="#555"),
                    rx.input(
                        value=VendorState.compose_to,
                        on_change=VendorState.set_compose_to,
                        placeholder="vendor@example.com",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Subject", size="2", color="#555"),
                    rx.input(
                        value=VendorState.compose_subject,
                        on_change=VendorState.set_compose_subject,
                        placeholder="Subject",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Message", size="2", color="#555"),
                    rx.text_area(
                        value=VendorState.compose_body,
                        on_change=VendorState.set_compose_body,
                        placeholder="Write your message here...",
                        rows="10",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.hstack(
                    rx.button(
                        "Send",
                        on_click=VendorState.send_compose_email,
                        loading=VendorState.compose_sending,
                        color_scheme="blue",
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            on_click=VendorState.close_compose_email,
                            variant="outline",
                        ),
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            max_width="600px",
        ),
        open=VendorState.compose_email_open,
    )


# ── Page content ──────────────────────────────────────────────────────────────

def vendors_content() -> rx.Component:
    return rx.box(
        rx.script(VENDORS_RESIZER_SCRIPT),
        # Page heading + new button
        rx.hstack(
            rx.heading("Manage vendors", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.button("+ New vendor", on_click=VendorState.new_vendor,
                      variant="outline", color_scheme="blue", size="2"),
            align="center", width="100%",
            padding_bottom="12px",
        ),
        # Split panel
        rx.hstack(
            # Left: filters + list
            rx.box(
                rx.hstack(
                    rx.vstack(
                        rx.text("Type", size="1", color="#888"),
                        rx.select(
                            VendorState.category_options,
                            value=VendorState.category_filter,
                            on_change=VendorState.set_category_filter,
                            size="1",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("Active", size="1", color="#888"),
                        rx.select(
                            ["All", "Yes", "No"],
                            value=VendorState.active_filter,
                            on_change=VendorState.set_active_filter,
                            size="1",
                        ),
                        spacing="1",
                    ),
                    spacing="3",
                    padding_bottom="12px",
                ),
                rx.cond(
                    VendorState.vendor_list.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Vendor name"),
                                rx.table.column_header_cell("Type"),
                                rx.table.column_header_cell("Phone"),
                                rx.table.column_header_cell("Status"),
                            )
                        ),
                        rx.table.body(rx.foreach(VendorState.vendor_list, vendor_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No vendors found.", color="#888", size="2"),
                ),
                id="vendors-list-panel",
                style={
                    "width": "580px",
                    "min_width": "580px",
                    "max_width": "580px",
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
                id="vendors-panel-resizer",
                style={
                    "width": "12px", "min_width": "12px", "cursor": "col-resize",
                    "display": "flex", "align_items": "center", "justify_content": "center",
                    "align_self": "stretch", "flex_shrink": "0",
                    "_hover": {"background": "#f0f4ff"},
                    "border_radius": "4px", "transition": "background 0.15s",
                    "touch_action": "none",
                    "z_index": "10",
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
            spacing="0",
            width="100%",
            align_items="start",
        ),
        vendor_compose_email_modal(),
        padding="24px",
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
        flex_shrink="0",
        style={"box_sizing": "border-box", "overflow_x": "hidden"},
    )


def vendors_page() -> rx.Component:
    return page_shell(vendors_content(), current_path="/admin/vendors")
