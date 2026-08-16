"""
Work Items page — global work item list + detail/edit form.
Route: /work-items

v5.2 — Responsive full-width split panel and stable first-load resizer binding.

v5.1 — Full-page dynamic width tracks resizable sidebar and adds Work Items split-panel resizer.

Layout: split panel (same pattern as Tenants)
  Left:  filterable/sortable work item list
  Right: detail form — create, edit, mark done
         Tabs: Actions (placeholder), Bids (placeholder)
"""

import datetime
import reflex as rx
from typing import Optional

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec, fmt_date,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# Dynamic full-page width. Updated by sidebar.py via --lucid-sidebar-width.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"

RESPONSIVE_GRID_4 = {"grid_template_columns": "repeat(auto-fit, minmax(180px, 1fr))"}
RESPONSIVE_GRID_2 = {"grid_template_columns": "repeat(auto-fit, minmax(240px, 1fr))"}


# ── Constants ─────────────────────────────────────────────────────────────────

WORK_TYPE_OPTIONS = ["Maintenance Request", "Repair", "Project", "Follow-Up"]
PRIORITY_OPTIONS  = ["Low", "Normal", "High", "Urgent"]
SOURCE_OPTIONS    = [
    "Tenant reported", "Staff observed", "Inspection",
    "Preventive", "Capital plan", "Vendor recommendation", "Other",
]
PRIORITY_COLOR = {
    "Urgent":  ("#fff3e0", "#e65100"),
    "High":    ("#fce4ec", "#b71c1c"),
    "Normal":  ("#e8f5e9", "#1b5e20"),
    "Low":     ("#f5f5f5", "#616161"),
}
OPEN_STATUSES = {"New", "Open", "In Progress", "Waiting on Vendor",
                 "Waiting on Tenant", "Scheduled"}

STATUS_SORT_ORDER = {
    "New": 0, "Open": 1, "In Progress": 2,
    "Waiting on Vendor": 3, "Waiting on Tenant": 4,
    "Scheduled": 5, "Deferred": 6,
    "Completed": 7, "Canceled": 8,
}


# ── Data models ───────────────────────────────────────────────────────────────

class WorkItemRow(rx.Base):
    work_item_id:   int = 0
    work_type:      str = ""
    title:          str = ""
    status:         str = ""
    priority:       str = ""
    property_name:  str = ""
    tenant_name:    str = ""
    category:       str = ""
    target_date:    str = ""
    assigned_to:    str = ""
    vendor_name:    str = ""
    is_overdue:     bool = False


class ActionRow(rx.Base):
    action_id:      int = 0
    action_title:   str = ""
    action_status:  str = ""
    due_date:       str = ""
    assigned_to:    str = ""
    vendor_name:    str = ""
    notes:          str = ""


class BidRow(rx.Base):
    bid_id:         int = 0
    vendor_name:    str = ""
    bid_date:       str = ""
    bid_amount:     str = ""
    bid_status:     str = ""
    scope_summary:  str = ""
    notes:          str = ""
    is_selected:    bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _s(val) -> str:
    return str(val or "").strip()

def _fmt_date(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%m/%d/%Y")
    return str(val)

def _fmt_currency(val) -> str:
    try:
        return f"${float(val):,.2f}"
    except (TypeError, ValueError):
        return ""

def _is_overdue(target_date_val) -> bool:
    if target_date_val is None:
        return False
    try:
        if isinstance(target_date_val, datetime.datetime):
            return target_date_val.date() < datetime.date.today()
        if isinstance(target_date_val, datetime.date):
            return target_date_val < datetime.date.today()
    except Exception:
        pass
    return False


# ── State ─────────────────────────────────────────────────────────────────────

class WorkItemState(AppState):

    # ── List / filter ──────────────────────────────────────────────────────
    work_items:         list[WorkItemRow] = []
    scope_filter:       str = "Open"          # Open | Closed | All
    property_filter:    str = "All"
    property_options:   list[str] = ["All"]
    search_query:       str = ""
    sort_field:         str = "status"        # status | target_date | priority
    sort_asc:           bool = True

    # ── Selected item ──────────────────────────────────────────────────────
    selected_id:        int = 0
    edit_mode:          bool = False
    is_new:             bool = False

    # Form fields
    f_work_type:        str = "Maintenance Request"
    f_title:            str = ""
    f_description:      str = ""
    f_property:         str = ""
    f_tenant:           str = ""
    f_suite:            str = ""
    f_category:         str = ""
    f_status:           str = "New"
    f_priority:         str = "Normal"
    f_source:           str = "Tenant reported"
    f_date_reported:    str = ""
    f_target_date:      str = ""
    f_scheduled_date:   str = ""
    f_assigned_to:      str = ""
    f_vendor:           str = ""
    f_estimated_cost:   str = ""
    f_actual_cost:      str = ""
    f_is_capital:       bool = False
    f_is_billable:      bool = False
    f_notes:            str = ""
    f_resolution:       str = ""

    # Lookups
    property_names:     list[str] = []
    property_ids:       list[int] = []
    tenant_names:       list[str] = []
    tenant_ids:         list[int] = []
    category_names:     list[str] = []
    category_ids:       list[int] = []
    status_names:       list[str] = []
    status_ids:         list[int] = []
    vendor_names:       list[str] = []
    vendor_ids:         list[int] = []

    # Detail display (read-only header)
    d_work_type:        str = ""
    d_title:            str = ""
    d_status:           str = ""
    d_priority:         str = ""
    d_property:         str = ""
    d_tenant:           str = ""
    d_category:         str = ""
    d_target_date:      str = ""
    d_assigned_to:      str = ""
    d_vendor:           str = ""
    d_estimated_cost:   str = ""
    d_actual_cost:      str = ""
    d_description:      str = ""
    d_notes:            str = ""
    d_resolution:       str = ""
    d_is_overdue:       bool = False

    # Actions + Bids (populated when item selected)
    actions:            list[ActionRow] = []
    bids:               list[BidRow] = []

    # Action form
    action_mode:        str = "new"
    selected_action_id: int = 0
    a_title:            str = ""
    a_status:           str = "Open"
    a_due_date:         str = ""
    a_assigned_to:      str = ""
    a_vendor:           str = ""
    a_notes:            str = ""
    action_form_error:  str = ""
    action_form_success: str = ""

    # Bid form
    bid_mode:           str = "new"
    selected_bid_id:    int = 0
    b_vendor:           str = ""
    b_date:             str = ""
    b_amount:           str = ""
    b_status:           str = "Requested"
    b_scope:            str = ""
    b_notes:            str = ""
    bid_form_error:     str = ""
    bid_form_success:   str = ""

    # UI
    form_error:         str = ""
    form_success:       str = ""
    confirm_done:       bool = False
    loading:            bool = False

    # ── Computed vars ──────────────────────────────────────────────────────

    @rx.var
    def is_closeable(self) -> bool:
        """Hide Mark Done when status is already terminal."""
        return self.d_status not in ("Completed", "Canceled")

    @rx.var
    def show_detail(self) -> bool:
        return self.selected_id > 0 or self.edit_mode

    @rx.var
    def filtered_items(self) -> list[WorkItemRow]:
        q = self.search_query.lower().strip()
        result = []
        for item in self.work_items:
            # scope filter
            if self.scope_filter == "Open" and item.status not in OPEN_STATUSES:
                continue
            if self.scope_filter == "Closed" and item.status in OPEN_STATUSES:
                continue
            # property filter
            if self.property_filter != "All" and item.property_name != self.property_filter:
                continue
            # search
            if q and q not in (
                item.title.lower() + item.status.lower() + item.category.lower() +
                item.tenant_name.lower() + item.property_name.lower() +
                item.assigned_to.lower() + item.vendor_name.lower()
            ):
                continue
            result.append(item)

        # Sort
        PRIORITY_ORDER = {"Urgent": 0, "High": 1, "Normal": 2, "Low": 3}
        if self.sort_field == "status":
            result.sort(
                key=lambda i: STATUS_SORT_ORDER.get(i.status, 99),
                reverse=not self.sort_asc,
            )
        elif self.sort_field == "priority":
            result.sort(
                key=lambda i: PRIORITY_ORDER.get(i.priority, 99),
                reverse=not self.sort_asc,
            )
        elif self.sort_field == "target_date":
            result.sort(
                key=lambda i: i.target_date or "99/99/9999",
                reverse=not self.sort_asc,
            )
        return result

    @rx.var
    def open_count(self) -> int:
        return sum(1 for i in self.work_items if i.status in OPEN_STATUSES)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def on_load(self):
        self._load_lookups()
        self.load_work_items()

    def reload_on_db_change(self):
        self.work_items = []
        self.selected_id = 0
        self.edit_mode = False
        self.actions = []
        self.bids = []
        self._load_lookups()
        self.load_work_items()

    # ── Internal ───────────────────────────────────────────────────────────

    def _load_lookups(self):
        db = self.db
        try:
            rows = run_query("SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName", db=db)
            self.property_names = ["(No property)"] + [_s(r["PropertyName"]) for r in rows]
            self.property_ids   = [0] + [int(r["PropertyID"]) for r in rows]
            self.property_options = ["All"] + [_s(r["PropertyName"]) for r in rows]
        except Exception:
            pass

        try:
            rows = run_query(
                "SELECT t.TenantID, t.TenantName FROM Tenants t "
                "JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
                "WHERE s.TenantStatusName IN ('Active','Default') ORDER BY t.TenantName",
                db=db,
            )
            self.tenant_names = ["(No tenant)"] + [_s(r["TenantName"]) for r in rows]
            self.tenant_ids   = [0] + [int(r["TenantID"]) for r in rows]
        except Exception:
            pass

        try:
            rows = run_query(
                "SELECT WorkItemCategoryID, CategoryName FROM WorkItemCategories "
                "WHERE IsActive = 1 ORDER BY SortOrder, CategoryName",
                db=db,
            )
            self.category_names = [_s(r["CategoryName"]) for r in rows]
            self.category_ids   = [int(r["WorkItemCategoryID"]) for r in rows]
        except Exception:
            self.category_names = ["General","Plumbing","Electrical","HVAC","Doors/Locks",
                                   "Roof","Landscaping","Exterior","Interior","Other"]
            self.category_ids   = list(range(1, len(self.category_names) + 1))

        try:
            rows = run_query(
                "SELECT WorkItemStatusID, StatusName FROM WorkItemStatuses "
                "WHERE IsActive = 1 ORDER BY SortOrder, StatusName",
                db=db,
            )
            self.status_names = [_s(r["StatusName"]) for r in rows]
            self.status_ids   = [int(r["WorkItemStatusID"]) for r in rows]
        except Exception:
            self.status_names = ["New","Open","In Progress","Waiting on Vendor",
                                 "Waiting on Tenant","Scheduled","Completed","Canceled","Deferred"]
            self.status_ids   = list(range(1, len(self.status_names) + 1))

        try:
            rows = run_query(
                "SELECT VendorID, VendorName FROM Vendors WHERE IsActive = 1 ORDER BY VendorName",
                db=db,
            )
            self.vendor_names = ["(No vendor)"] + [_s(r["VendorName"]) for r in rows]
            self.vendor_ids   = [0] + [int(r["VendorID"]) for r in rows]
        except Exception:
            pass

    def load_work_items(self):
        db = self.db
        try:
            rows = run_query(
                "SELECT w.WorkItemID, w.WorkType, w.Title, "
                "ISNULL(s.StatusName, w.Status) AS Status, "
                "w.Priority, w.PropertyID, w.TenantID, "
                "ISNULL(c.CategoryName, w.Category) AS Category, "
                "w.TargetDate, w.AssignedTo, "
                "ISNULL(v.VendorName, w.VendorName) AS VendorName "
                "FROM WorkItems w "
                "LEFT JOIN WorkItemStatuses s ON w.StatusID = s.WorkItemStatusID "
                "LEFT JOIN WorkItemCategories c ON w.CategoryID = c.WorkItemCategoryID "
                "LEFT JOIN Vendors v ON w.VendorID = v.VendorID "
                "ORDER BY "
                "CASE WHEN ISNULL(s.StatusName, w.Status) IN "
                "('New','Open','In Progress','Waiting on Vendor','Waiting on Tenant','Scheduled','Deferred') "
                "THEN 0 ELSE 1 END, "
                "w.TargetDate ASC, w.CreatedDate DESC",
                db=db,
            )
            prop_map   = dict(zip(self.property_ids, self.property_names))
            tenant_map = dict(zip(self.tenant_ids, self.tenant_names))

            self.work_items = [
                WorkItemRow(
                    work_item_id  = int(r["WorkItemID"]),
                    work_type     = _s(r.get("WorkType")),
                    title         = _s(r.get("Title")),
                    status        = _s(r.get("Status")),
                    priority      = _s(r.get("Priority")),
                    property_name = prop_map.get(r.get("PropertyID") and int(r["PropertyID"]), ""),
                    tenant_name   = tenant_map.get(r.get("TenantID") and int(r["TenantID"]), ""),
                    category      = _s(r.get("Category")),
                    target_date   = _fmt_date(r.get("TargetDate")),
                    assigned_to   = _s(r.get("AssignedTo")),
                    vendor_name   = _s(r.get("VendorName")),
                    is_overdue    = _is_overdue(r.get("TargetDate")),
                )
                for r in rows
            ]
        except Exception as ex:
            self.form_error = f"Could not load work items: {ex}"

    def _load_item_detail(self, work_item_id: int):
        db = self.db
        rows = run_query(
            "SELECT w.*, "
            "ISNULL(s.StatusName, w.Status) AS StatusLabel, "
            "ISNULL(c.CategoryName, w.Category) AS CategoryLabel, "
            "ISNULL(v.VendorName, w.VendorName) AS VendorLabel, "
            "p.PropertyName, t.TenantName "
            "FROM WorkItems w "
            "LEFT JOIN WorkItemStatuses s ON w.StatusID = s.WorkItemStatusID "
            "LEFT JOIN WorkItemCategories c ON w.CategoryID = c.WorkItemCategoryID "
            "LEFT JOIN Vendors v ON w.VendorID = v.VendorID "
            "LEFT JOIN Properties p ON w.PropertyID = p.PropertyID "
            "LEFT JOIN Tenants t ON w.TenantID = t.TenantID "
            "WHERE w.WorkItemID = ?",
            (work_item_id,), db=db,
        )
        if not rows:
            return
        r = rows[0]
        self.d_work_type     = _s(r.get("WorkType"))
        self.d_title         = _s(r.get("Title"))
        self.d_status        = _s(r.get("StatusLabel") or r.get("Status"))
        self.d_priority      = _s(r.get("Priority"))
        self.d_property      = _s(r.get("PropertyName"))
        self.d_tenant        = _s(r.get("TenantName"))
        self.d_category      = _s(r.get("CategoryLabel") or r.get("Category"))
        self.d_target_date   = _fmt_date(r.get("TargetDate"))
        self.d_assigned_to   = _s(r.get("AssignedTo"))
        self.d_vendor        = _s(r.get("VendorLabel") or r.get("VendorName"))
        self.d_estimated_cost = _fmt_currency(r.get("EstimatedCost"))
        self.d_actual_cost   = _fmt_currency(r.get("ActualCost"))
        self.d_description   = _s(r.get("Description"))
        self.d_notes         = _s(r.get("Notes"))
        self.d_resolution    = _s(r.get("ResolutionSummary"))
        self.d_is_overdue    = _is_overdue(r.get("TargetDate"))
        self._load_actions(work_item_id)
        self._load_bids(work_item_id)

    def _load_actions(self, work_item_id: int):
        try:
            rows = run_query(
                "SELECT a.WorkItemActionID, a.ActionTitle, a.ActionStatus, a.DueDate, "
                "a.AssignedTo, a.Notes, ISNULL(av.VendorName, '') AS VendorName "
                "FROM WorkItemActions a "
                "LEFT JOIN Vendors av ON a.VendorID = av.VendorID "
                "WHERE a.WorkItemID = ? "
                "ORDER BY CASE WHEN a.ActionStatus IN ('Open','Waiting') THEN 0 ELSE 1 END, "
                "a.DueDate ASC, a.CreatedDate DESC",
                (work_item_id,), db=self.db,
            )
            self.actions = [
                ActionRow(
                    action_id    = int(r["WorkItemActionID"]),
                    action_title = _s(r.get("ActionTitle")),
                    action_status = _s(r.get("ActionStatus")),
                    due_date     = _fmt_date(r.get("DueDate")),
                    assigned_to  = _s(r.get("AssignedTo")),
                    vendor_name  = _s(r.get("VendorName")),
                    notes        = _s(r.get("Notes")),
                )
                for r in rows
            ]
        except Exception:
            self.actions = []

    def _load_bids(self, work_item_id: int):
        try:
            rows = run_query(
                "SELECT b.WorkItemBidID, v.VendorName, b.BidDate, b.BidAmount, "
                "b.BidStatus, b.ScopeSummary, b.IsSelected "
                "FROM WorkItemBids b "
                "LEFT JOIN Vendors v ON b.VendorID = v.VendorID "
                "WHERE b.WorkItemID = ? "
                "ORDER BY CASE WHEN b.IsSelected = 1 THEN 0 ELSE 1 END, "
                "b.BidDate DESC",
                (work_item_id,), db=self.db,
            )
            self.bids = [
                BidRow(
                    bid_id       = int(r["WorkItemBidID"]),
                    vendor_name  = _s(r.get("VendorName")),
                    bid_date     = _fmt_date(r.get("BidDate")),
                    bid_amount   = _fmt_currency(r.get("BidAmount")),
                    bid_status   = _s(r.get("BidStatus")),
                    scope_summary = _s(r.get("ScopeSummary")),
                    notes        = _s(r.get("Notes")),
                    is_selected  = bool(r.get("IsSelected")),
                )
                for r in rows
            ]
        except Exception:
            self.bids = []

    # ── Event handlers ─────────────────────────────────────────────────────

    def set_scope_filter(self, v: str):
        self.scope_filter = v

    def toggle_sort(self, field: str):
        if self.sort_field == field:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_field = field
            self.sort_asc = True

    def set_property_filter(self, v: str):
        self.property_filter = v

    def set_search_query(self, v: str):
        self.search_query = v

    def select_item(self, work_item_id: int):
        self.selected_id = work_item_id
        self.edit_mode = False
        self.is_new = False
        self.form_error = ""
        self.form_success = ""
        self.confirm_done = False
        self._load_item_detail(work_item_id)
        self._reset_action_form()
        self._reset_bid_form()

    def start_new(self):
        self.selected_id = 0
        self.edit_mode = True
        self.is_new = True
        self.form_error = ""
        self.form_success = ""
        self.confirm_done = False
        today = datetime.date.today().isoformat()
        self.f_work_type      = "Maintenance Request"
        self.f_title          = ""
        self.f_description    = ""
        self.f_property       = self.property_names[1] if len(self.property_names) > 1 else ""
        self.f_tenant         = "(No tenant)"
        self.f_suite          = ""
        self.f_category       = self.category_names[0] if self.category_names else ""
        self.f_status         = "New"
        self.f_priority       = "Normal"
        self.f_source         = "Tenant reported"
        self.f_date_reported  = today
        self.f_target_date    = ""
        self.f_scheduled_date = ""
        self.f_assigned_to    = ""
        self.f_vendor         = "(No vendor)"
        self.f_estimated_cost = ""
        self.f_actual_cost    = ""
        self.f_is_capital     = False
        self.f_is_billable    = False
        self.f_notes          = ""
        self.f_resolution     = ""

    def start_edit(self):
        self.edit_mode = True
        self.is_new = False
        self.form_error = ""
        self.form_success = ""
        # Populate form from display values
        self.f_work_type      = self.d_work_type or "Maintenance Request"
        self.f_title          = self.d_title
        self.f_description    = self.d_description
        self.f_property       = self.d_property or "(No property)"
        self.f_tenant         = self.d_tenant or "(No tenant)"
        self.f_suite          = ""
        self.f_category       = self.d_category or (self.category_names[0] if self.category_names else "")
        self.f_status         = self.d_status or "New"
        self.f_priority       = self.d_priority or "Normal"
        self.f_source         = "Tenant reported"
        self.f_date_reported  = ""
        self.f_target_date    = self.d_target_date
        self.f_scheduled_date = ""
        self.f_assigned_to    = self.d_assigned_to
        self.f_vendor         = self.d_vendor or "(No vendor)"
        self.f_estimated_cost = self.d_estimated_cost.replace("$", "").replace(",", "") if self.d_estimated_cost else ""
        self.f_actual_cost    = self.d_actual_cost.replace("$", "").replace(",", "") if self.d_actual_cost else ""
        self.f_is_capital     = False
        self.f_is_billable    = False
        self.f_notes          = self.d_notes
        self.f_resolution     = self.d_resolution

    def cancel_edit(self):
        self.edit_mode = False
        self.form_error = ""
        self.form_success = ""

    def save_work_item(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_title.strip():
            self.form_error = "Title is required."
            return

        db = self.db
        now = datetime.datetime.now()

        # Resolve IDs
        prop_id = None
        if self.f_property and self.f_property in self.property_names:
            idx = self.property_names.index(self.f_property)
            prop_id = self.property_ids[idx] or None

        tenant_id = None
        if self.f_tenant and self.f_tenant in self.tenant_names:
            idx = self.tenant_names.index(self.f_tenant)
            tenant_id = self.tenant_ids[idx] or None

        cat_id = None
        cat_name = self.f_category
        if self.f_category and self.f_category in self.category_names:
            idx = self.category_names.index(self.f_category)
            cat_id = self.category_ids[idx]

        status_id = None
        if self.f_status and self.f_status in self.status_names:
            idx = self.status_names.index(self.f_status)
            status_id = self.status_ids[idx]

        vendor_id = None
        vendor_name = ""
        if self.f_vendor and self.f_vendor in self.vendor_names and self.f_vendor != "(No vendor)":
            idx = self.vendor_names.index(self.f_vendor)
            vendor_id = self.vendor_ids[idx] or None
            vendor_name = self.f_vendor

        def _parse_date(s: str):
            if not s:
                return None
            try:
                return datetime.date.fromisoformat(s)
            except Exception:
                return None

        def _parse_float(s: str) -> float:
            try:
                return float(s.replace(",", "").replace("$", ""))
            except Exception:
                return 0.0

        completed_date = now if self.f_status == "Completed" else None

        params = (
            self.f_work_type.strip(),
            prop_id,
            tenant_id,
            self.f_suite.strip(),
            cat_name.strip(),
            cat_id,
            self.f_title.strip(),
            self.f_description.strip(),
            self.f_status.strip(),
            status_id,
            self.f_priority.strip(),
            self.f_source.strip(),
            _parse_date(self.f_date_reported),
            _parse_date(self.f_target_date),
            _parse_date(self.f_scheduled_date),
            completed_date,
            self.f_assigned_to.strip(),
            vendor_name,
            vendor_id,
            _parse_float(self.f_estimated_cost),
            _parse_float(self.f_actual_cost),
            int(self.f_is_capital),
            int(self.f_is_billable),
            self.f_notes.strip(),
            self.f_resolution.strip(),
            now,
        )

        try:
            if not self.is_new and self.selected_id > 0:
                run_exec(
                    "UPDATE [WorkItems] SET [WorkType]=?, [PropertyID]=?, [TenantID]=?, [Suite]=?, "
                    "[Category]=?, [CategoryID]=?, [Title]=?, [Description]=?, [Status]=?, [StatusID]=?, "
                    "[Priority]=?, [Source]=?, [DateReported]=?, [TargetDate]=?, [ScheduledDate]=?, "
                    "[CompletedDate]=?, [AssignedTo]=?, [VendorName]=?, [VendorID]=?, [EstimatedCost]=?, "
                    "[ActualCost]=?, [IsCapitalProject]=?, [IsBillableToTenant]=?, [Notes]=?, "
                    "[ResolutionSummary]=?, [UpdatedDate]=? "
                    "WHERE [WorkItemID]=?",
                    params + (int(self.selected_id),),
                    db=db,
                )
                self.form_success = "Work item saved."
            else:
                run_exec(
                    "INSERT INTO [WorkItems] ([WorkType],[PropertyID],[TenantID],[Suite],[Category],[CategoryID],"
                    "[Title],[Description],[Status],[StatusID],[Priority],[Source],[DateReported],[TargetDate],"
                    "[ScheduledDate],[CompletedDate],[AssignedTo],[VendorName],[VendorID],[EstimatedCost],"
                    "[ActualCost],[IsCapitalProject],[IsBillableToTenant],[Notes],[ResolutionSummary],[CreatedDate],[UpdatedDate]) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    params + (now,),
                    db=db,
                )
                self.form_success = "Work item created."

            self.edit_mode = False
            self.is_new = False
            self.load_work_items()

            # Re-select if editing
            if not self.is_new and self.selected_id > 0:
                self._load_item_detail(self.selected_id)

        except Exception as ex:
            self.form_error = f"Save failed: {ex}"

    def mark_done(self):
        if not self.confirm_done:
            self.confirm_done = True
            return
        self.confirm_done = False
        db = self.db
        try:
            # Check for open actions
            rows = run_query(
                "SELECT COUNT(*) AS Cnt FROM WorkItemActions "
                "WHERE WorkItemID = ? AND ActionStatus NOT IN ('Done','Canceled')",
                (int(self.selected_id),), db=db,
            )
            open_count = int(rows[0]["Cnt"]) if rows else 0
            if open_count > 0:
                self.form_error = f"Cannot close — {open_count} open action(s) remain. Close those first."
                return

            status_rows = run_query(
                "SELECT TOP 1 WorkItemStatusID, StatusName FROM WorkItemStatuses "
                "WHERE StatusName = 'Completed'",
                db=db,
            )
            if status_rows:
                sid  = int(status_rows[0]["WorkItemStatusID"])
                sname = _s(status_rows[0]["StatusName"])
            else:
                sid, sname = None, "Completed"

            now = datetime.datetime.now()
            run_exec(
                "UPDATE WorkItems SET Status=?, StatusID=?, CompletedDate=?, UpdatedDate=? WHERE WorkItemID=?",
                (sname, sid, now, now, int(self.selected_id)),
                db=db,
            )
            self.form_success = "Work item marked done."
            self.load_work_items()
            self._load_item_detail(self.selected_id)
        except Exception as ex:
            self.form_error = f"Error: {ex}"

    def cancel_confirm_done(self):
        self.confirm_done = False

    # ── Action event handlers ──────────────────────────────────────────────

    def _reset_action_form(self):
        self.action_mode = "new"
        self.selected_action_id = 0
        self.a_title = ""
        self.a_status = "Open"
        self.a_due_date = ""
        self.a_assigned_to = ""
        self.a_vendor = "(No vendor)"
        self.a_notes = ""
        self.action_form_error = ""
        self.action_form_success = ""

    def new_action(self):
        self._reset_action_form()

    def select_action(self, action_id: int):
        self.selected_action_id = action_id
        self.action_mode = "edit"
        self.action_form_error = ""
        self.action_form_success = ""
        for a in self.actions:
            if a.action_id == action_id:
                self.a_title      = a.action_title
                self.a_status     = a.action_status
                self.a_due_date   = a.due_date
                self.a_assigned_to = a.assigned_to
                self.a_vendor     = a.vendor_name or "(No vendor)"
                self.a_notes      = a.notes
                break

    def save_action(self):
        self.action_form_error = ""
        self.action_form_success = ""
        if not self.a_title.strip():
            self.action_form_error = "Action title is required."
            return
        db = self.db
        now = datetime.datetime.now()
        vendor_id = None
        if self.a_vendor and self.a_vendor in self.vendor_names and self.a_vendor != "(No vendor)":
            idx = self.vendor_names.index(self.a_vendor)
            vendor_id = self.vendor_ids[idx] or None

        def _parse_date(s):
            try: return datetime.date.fromisoformat(s) if s else None
            except: return None

        completed = now if self.a_status == "Done" else None
        try:
            if self.action_mode == "edit" and self.selected_action_id > 0:
                run_exec(
                    "UPDATE WorkItemActions SET ActionTitle=?, ActionStatus=?, DueDate=?, "
                    "CompletedDate=?, AssignedTo=?, VendorID=?, Notes=?, UpdatedDate=? "
                    "WHERE WorkItemActionID=?",
                    (self.a_title.strip(), self.a_status.strip(), _parse_date(self.a_due_date),
                     completed, self.a_assigned_to.strip(), vendor_id, self.a_notes.strip(),
                     now, int(self.selected_action_id)),
                    db=db,
                )
            else:
                run_exec(
                    "INSERT INTO WorkItemActions (WorkItemID, ActionTitle, ActionStatus, DueDate, "
                    "CompletedDate, AssignedTo, VendorID, Notes, CreatedDate, UpdatedDate) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (int(self.selected_id), self.a_title.strip(), self.a_status.strip(),
                     _parse_date(self.a_due_date), completed, self.a_assigned_to.strip(),
                     vendor_id, self.a_notes.strip(), now, now),
                    db=db,
                )
            self.action_form_success = "Action saved."
            self._reset_action_form()
            self._load_actions(self.selected_id)
        except Exception as ex:
            self.action_form_error = f"Save failed: {ex}"

    def delete_action(self):
        if self.selected_action_id == 0:
            return
        try:
            run_exec(
                "DELETE FROM WorkItemActions WHERE WorkItemActionID=?",
                (int(self.selected_action_id),), db=self.db,
            )
            self._reset_action_form()
            self._load_actions(self.selected_id)
        except Exception as ex:
            self.action_form_error = f"Delete failed: {ex}"

    # ── Bid event handlers ─────────────────────────────────────────────────

    def _reset_bid_form(self):
        self.bid_mode = "new"
        self.selected_bid_id = 0
        self.b_vendor = "(No vendor)"
        self.b_date = ""
        self.b_amount = ""
        self.b_status = "Requested"
        self.b_scope = ""
        self.b_notes = ""
        self.bid_form_error = ""
        self.bid_form_success = ""

    def new_bid(self):
        self._reset_bid_form()

    def select_bid(self, bid_id: int):
        self.selected_bid_id = bid_id
        self.bid_mode = "edit"
        self.bid_form_error = ""
        self.bid_form_success = ""
        for b in self.bids:
            if b.bid_id == bid_id:
                self.b_vendor = b.vendor_name or "(No vendor)"
                self.b_date   = b.bid_date
                self.b_amount = b.bid_amount.replace("$","").replace(",","") if b.bid_amount else ""
                self.b_status = b.bid_status
                self.b_scope  = b.scope_summary
                self.b_notes  = b.notes
                break

    def save_bid(self):
        self.bid_form_error = ""
        self.bid_form_success = ""
        if not self.b_vendor or self.b_vendor == "(No vendor)":
            self.bid_form_error = "Vendor is required."
            return
        db = self.db
        now = datetime.datetime.now()
        vendor_id = None
        if self.b_vendor in self.vendor_names:
            idx = self.vendor_names.index(self.b_vendor)
            vendor_id = self.vendor_ids[idx] or None

        def _parse_date(s):
            try: return datetime.date.fromisoformat(s) if s else None
            except: return None
        def _parse_float(s):
            try: return float(str(s).replace(",","").replace("$",""))
            except: return None

        try:
            if self.bid_mode == "edit" and self.selected_bid_id > 0:
                run_exec(
                    "UPDATE WorkItemBids SET VendorID=?, BidDate=?, BidAmount=?, BidStatus=?, "
                    "ScopeSummary=?, Notes=?, UpdatedDate=? WHERE WorkItemBidID=?",
                    (vendor_id, _parse_date(self.b_date), _parse_float(self.b_amount),
                     self.b_status.strip(), self.b_scope.strip(), self.b_notes.strip(),
                     now, int(self.selected_bid_id)),
                    db=db,
                )
            else:
                run_exec(
                    "INSERT INTO WorkItemBids (WorkItemID, VendorID, BidDate, BidAmount, BidStatus, "
                    "ScopeSummary, Notes, IsSelected, CreatedDate, UpdatedDate) "
                    "VALUES (?,?,?,?,?,?,?,0,?,?)",
                    (int(self.selected_id), vendor_id, _parse_date(self.b_date),
                     _parse_float(self.b_amount), self.b_status.strip(),
                     self.b_scope.strip(), self.b_notes.strip(), now, now),
                    db=db,
                )
            self.bid_form_success = "Bid saved."
            self._reset_bid_form()
            self._load_bids(self.selected_id)
        except Exception as ex:
            self.bid_form_error = f"Save failed: {ex}"

    def select_winning_bid(self):
        if self.selected_bid_id == 0:
            self.bid_form_error = "Select a bid first."
            return
        db = self.db
        now = datetime.datetime.now()
        try:
            # Deselect all other bids, revert their status from Accepted if needed
            run_exec(
                "UPDATE WorkItemBids SET IsSelected=0, "
                "BidStatus=CASE WHEN BidStatus='Accepted' THEN 'Received' ELSE BidStatus END, "
                "UpdatedDate=? WHERE WorkItemID=? AND WorkItemBidID!=?",
                (now, int(self.selected_id), int(self.selected_bid_id)), db=db,
            )
            # Mark winner as selected + Accepted
            run_exec(
                "UPDATE WorkItemBids SET IsSelected=1, BidStatus='Accepted', "
                "SelectedDate=?, UpdatedDate=? WHERE WorkItemBidID=?",
                (now, now, int(self.selected_bid_id)), db=db,
            )
            # Pull the winning bid's vendor and update the parent work item
            bid_rows = run_query(
                "SELECT b.VendorID, v.VendorName FROM WorkItemBids b "
                "LEFT JOIN Vendors v ON b.VendorID = v.VendorID "
                "WHERE b.WorkItemBidID=?",
                (int(self.selected_bid_id),), db=db,
            )
            if bid_rows and bid_rows[0].get("VendorID"):
                vid   = int(bid_rows[0]["VendorID"])
                vname = str(bid_rows[0].get("VendorName") or "").strip()
                run_exec(
                    "UPDATE WorkItems SET VendorID=?, VendorName=?, UpdatedDate=? WHERE WorkItemID=?",
                    (vid, vname, now, int(self.selected_id)), db=db,
                )

            self.bid_form_success = "Bid accepted — work item vendor updated."
            self._load_bids(self.selected_id)
            self._load_item_detail(self.selected_id)
        except Exception as ex:
            self.bid_form_error = f"Error: {ex}"

    # setters
    def set_f_work_type(self, v: str):      self.f_work_type = v
    def set_f_title(self, v: str):          self.f_title = v
    def set_f_description(self, v: str):    self.f_description = v
    def set_f_property(self, v: str):       self.f_property = v
    def set_f_tenant(self, v: str):         self.f_tenant = v
    def set_f_suite(self, v: str):          self.f_suite = v
    def set_f_category(self, v: str):       self.f_category = v
    def set_f_status(self, v: str):         self.f_status = v
    def set_f_priority(self, v: str):       self.f_priority = v
    def set_f_source(self, v: str):         self.f_source = v
    def set_f_date_reported(self, v: str):  self.f_date_reported = v
    def set_f_target_date(self, v: str):    self.f_target_date = v
    def set_f_scheduled_date(self, v: str): self.f_scheduled_date = v
    def set_f_assigned_to(self, v: str):    self.f_assigned_to = v
    def set_f_vendor(self, v: str):         self.f_vendor = v
    def set_f_estimated_cost(self, v: str): self.f_estimated_cost = v
    def set_f_actual_cost(self, v: str):    self.f_actual_cost = v
    def set_f_is_capital(self, v: bool):    self.f_is_capital = v
    def set_f_is_billable(self, v: bool):   self.f_is_billable = v
    def set_f_notes(self, v: str):          self.f_notes = v
    def set_f_resolution(self, v: str):     self.f_resolution = v
    def set_a_title(self, v: str):          self.a_title = v
    def set_a_status(self, v: str):         self.a_status = v
    def set_a_due_date(self, v: str):       self.a_due_date = v
    def set_a_assigned_to(self, v: str):    self.a_assigned_to = v
    def set_a_vendor(self, v: str):         self.a_vendor = v
    def set_a_notes(self, v: str):          self.a_notes = v
    def set_b_vendor(self, v: str):         self.b_vendor = v
    def set_b_date(self, v: str):           self.b_date = v
    def set_b_amount(self, v: str):         self.b_amount = v
    def set_b_status(self, v: str):         self.b_status = v
    def set_b_scope(self, v: str):          self.b_scope = v
    def set_b_notes(self, v: str):          self.b_notes = v


# ── UI helpers ────────────────────────────────────────────────────────────────

def _pill(text: str, bg: str, color: str) -> rx.Component:
    return rx.box(
        rx.text(text, size="1", weight="bold", style={"color": color}),
        style={"background": bg, "border_radius": "999px",
               "padding": "2px 10px", "display": "inline-block"},
    )

def _priority_pill(priority: str) -> rx.Component:
    bg, color = PRIORITY_COLOR.get(priority, ("#f5f5f5", "#616161"))
    return _pill(priority, bg, color)

def _field(label: str, component: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color="#666"),
        component,
        spacing="1", width="100%",
    )


# ── List panel ────────────────────────────────────────────────────────────────

def _work_item_list_row(item: WorkItemRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.vstack(
                rx.text(item.title, size="2", weight="bold",
                        style={"color": rx.cond(item.is_overdue, "#c62828", BRAND_DARK)}),
                rx.text(item.category, size="1", color="#888"),
                spacing="0",
            ),
            padding="8px 10px",
        ),
        rx.table.cell(
            rx.vstack(
                rx.text(item.property_name, size="1", color="#555"),
                rx.text(item.tenant_name, size="1", color="#888"),
                spacing="0",
            ),
            padding="8px 10px",
        ),
        rx.table.cell(
            rx.vstack(
                rx.text(item.status, size="1", color="#555"),
                rx.text(item.target_date, size="1",
                        style={"color": rx.cond(item.is_overdue, "#c62828", "#888")}),
                spacing="0",
            ),
            padding="8px 10px",
        ),
        on_click=WorkItemState.select_item(item.work_item_id),
        style=rx.cond(
            WorkItemState.selected_id == item.work_item_id,
            {"background": "#f0f4ff", "cursor": "pointer"},
            {"background": "white", "cursor": "pointer",
             "_hover": {"background": "#f8fafc"}},
        ),
        vertical_align="top",
    )


def _list_panel() -> rx.Component:
    return rx.vstack(
        # Header
        rx.hstack(
            rx.heading("Work Items", size="5", color=BRAND_DARK),
            rx.badge(
                WorkItemState.open_count.to_string() + " open",
                color_scheme="blue", variant="soft",
            ),
            rx.spacer(),
            rx.button(
                "+ New",
                on_click=WorkItemState.start_new,
                size="2", color_scheme="blue", variant="soft",
            ),
            align="center", width="100%",
        ),

        # Filters
        rx.hstack(
            rx.select(
                ["Open", "Closed", "All"],
                value=WorkItemState.scope_filter,
                on_change=WorkItemState.set_scope_filter,
                size="1",
            ),
            rx.select(
                WorkItemState.property_options,
                value=WorkItemState.property_filter,
                on_change=WorkItemState.set_property_filter,
                size="1",
            ),
            spacing="2", width="100%",
        ),

        rx.input(
            placeholder="Search…",
            value=WorkItemState.search_query,
            on_change=WorkItemState.set_search_query,
            size="2",
            width="100%",
        ),

        # List table
        rx.cond(
            WorkItemState.filtered_items.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Title / Category",
                            style={"font_size": "11px", "color": BRAND_PRIMARY,
                                   "padding": "6px 10px", "width": "42%"}),
                        rx.table.column_header_cell("Property / Tenant",
                            style={"font_size": "11px", "color": BRAND_PRIMARY,
                                   "padding": "6px 10px", "width": "34%"}),
                        rx.table.column_header_cell(
                            rx.hstack(
                                rx.text("Status / Due", size="1", weight="bold", color=BRAND_PRIMARY),
                                rx.text(
                                    rx.cond(
                                        WorkItemState.sort_field == "status",
                                        rx.cond(WorkItemState.sort_asc, " ↑", " ↓"),
                                        "",
                                    ),
                                    size="1", color=BRAND_PRIMARY,
                                ),
                                spacing="0",
                            ),
                            on_click=WorkItemState.toggle_sort("status"),
                            style={"cursor": "pointer", "padding": "6px 10px",
                                   "width": "24%",
                                   "_hover": {"background": "#eef1fa"}},
                        ),
                    )
                ),
                rx.table.body(
                    rx.foreach(WorkItemState.filtered_items, _work_item_list_row)
                ),
                width="100%", variant="surface",
                style={"table_layout": "fixed"},
            ),
            rx.text("No work items match the current filters.", color="#888", size="2"),
        ),

        spacing="3", width="100%", align_items="start",
    )


# ── Detail panel ──────────────────────────────────────────────────────────────

def _detail_header() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(WorkItemState.d_title, size="4", weight="bold", color=BRAND_DARK),
                    _priority_pill(WorkItemState.d_priority),
                    rx.cond(
                        WorkItemState.d_is_overdue,
                        _pill("OVERDUE", "#fce4ec", "#b71c1c"),
                        rx.fragment(),
                    ),
                    align="center", spacing="2", wrap="wrap",
                ),
                rx.hstack(
                    rx.text(WorkItemState.d_work_type, size="2", color="#666"),
                    rx.text("·", size="2", color="#ccc"),
                    rx.text(WorkItemState.d_status, size="2", color="#666"),
                    rx.text("·", size="2", color="#ccc"),
                    rx.text(WorkItemState.d_category, size="2", color="#666"),
                    spacing="1", align="center",
                ),
                rx.hstack(
                    rx.text(WorkItemState.d_property, size="2", color=BRAND_PRIMARY),
                    rx.cond(
                        WorkItemState.d_tenant != "",
                        rx.hstack(
                            rx.text("·", size="2", color="#ccc"),
                            rx.text(WorkItemState.d_tenant, size="2", color="#555"),
                            spacing="1",
                        ),
                        rx.fragment(),
                    ),
                    spacing="1", align="center",
                ),
                spacing="1", align_items="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.hstack(
                    rx.button(
                        "✏ Edit",
                        on_click=WorkItemState.start_edit,
                        size="1", variant="outline", color_scheme="blue",
                    ),
                    # Mark done / confirm
                    rx.cond(
                        WorkItemState.is_closeable,
                        rx.cond(
                            WorkItemState.confirm_done,
                            rx.hstack(
                                rx.text("Mark this done?", size="1", color="#c62828"),
                                rx.button("Yes", on_click=WorkItemState.mark_done,
                                          size="1", color_scheme="red"),
                                rx.button("No", on_click=WorkItemState.cancel_confirm_done,
                                          size="1", variant="ghost"),
                                spacing="2", align="center",
                            ),
                            rx.button(
                                "✓ Mark done",
                                on_click=WorkItemState.mark_done,
                                size="1", variant="outline", color_scheme="green",
                            ),
                        ),
                        rx.badge(WorkItemState.d_status, color_scheme="gray", variant="soft"),
                    ),
                    spacing="2",
                ),
                rx.hstack(
                    rx.text("Due:", size="1", color="#888"),
                    rx.text(WorkItemState.d_target_date, size="1",
                            style={"color": rx.cond(WorkItemState.d_is_overdue, "#c62828", "#555")}),
                    rx.text("Est:", size="1", color="#888"),
                    rx.text(WorkItemState.d_estimated_cost, size="1", color="#555"),
                    spacing="2", align="center",
                ),
                align_items="end", spacing="2",
            ),
            align="start", width="100%",
        ),
        style={
            "background": "white",
            "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}",
            "border_radius": "12px",
            "padding": "16px 20px",
            "margin_bottom": "8px",
            "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
        },
    )


def _edit_form() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                rx.cond(WorkItemState.is_new, "New work item", "Edit work item"),
                size="3", weight="bold", color=BRAND_DARK,
            ),

            # Row 1: type, title, status, priority
            rx.grid(
                _field("Work type",
                    rx.select(WORK_TYPE_OPTIONS, value=WorkItemState.f_work_type,
                              on_change=WorkItemState.set_f_work_type, size="2", width="100%")),
                _field("Title *",
                    rx.input(value=WorkItemState.f_title, on_change=WorkItemState.set_f_title,
                             placeholder="Brief description", size="2", width="100%")),
                _field("Status",
                    rx.select(WorkItemState.status_names, value=WorkItemState.f_status,
                              on_change=WorkItemState.set_f_status, size="2", width="100%")),
                _field("Priority",
                    rx.select(PRIORITY_OPTIONS, value=WorkItemState.f_priority,
                              on_change=WorkItemState.set_f_priority, size="2", width="100%")),
                columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
            ),

            # Row 2: property, tenant, suite, category
            rx.grid(
                _field("Property",
                    rx.select(WorkItemState.property_names, value=WorkItemState.f_property,
                              on_change=WorkItemState.set_f_property, size="2", width="100%")),
                _field("Tenant",
                    rx.select(WorkItemState.tenant_names, value=WorkItemState.f_tenant,
                              on_change=WorkItemState.set_f_tenant, size="2", width="100%")),
                _field("Suite",
                    rx.input(value=WorkItemState.f_suite, on_change=WorkItemState.set_f_suite,
                             placeholder="e.g. 101", size="2", width="100%")),
                _field("Category",
                    rx.select(WorkItemState.category_names, value=WorkItemState.f_category,
                              on_change=WorkItemState.set_f_category, size="2", width="100%")),
                columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
            ),

            # Row 3: source, date reported, target date, scheduled date
            rx.grid(
                _field("Source",
                    rx.select(SOURCE_OPTIONS, value=WorkItemState.f_source,
                              on_change=WorkItemState.set_f_source, size="2", width="100%")),
                _field("Date reported",
                    rx.input(type="date", value=WorkItemState.f_date_reported,
                             on_change=WorkItemState.set_f_date_reported, size="2", width="100%")),
                _field("Target date",
                    rx.input(type="date", value=WorkItemState.f_target_date,
                             on_change=WorkItemState.set_f_target_date, size="2", width="100%")),
                _field("Scheduled date",
                    rx.input(type="date", value=WorkItemState.f_scheduled_date,
                             on_change=WorkItemState.set_f_scheduled_date, size="2", width="100%")),
                columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
            ),

            # Row 4: assigned to, vendor, estimated cost, actual cost
            rx.grid(
                _field("Assigned to",
                    rx.input(value=WorkItemState.f_assigned_to,
                             on_change=WorkItemState.set_f_assigned_to,
                             placeholder="Staff name", size="2", width="100%")),
                _field("Vendor",
                    rx.select(WorkItemState.vendor_names, value=WorkItemState.f_vendor,
                              on_change=WorkItemState.set_f_vendor, size="2", width="100%")),
                _field("Estimated cost",
                    rx.input(value=WorkItemState.f_estimated_cost,
                             on_change=WorkItemState.set_f_estimated_cost,
                             placeholder="0.00", size="2", width="100%")),
                _field("Actual cost",
                    rx.input(value=WorkItemState.f_actual_cost,
                             on_change=WorkItemState.set_f_actual_cost,
                             placeholder="0.00", size="2", width="100%")),
                columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
            ),

            # Row 5: flags
            rx.hstack(
                rx.hstack(
                    rx.checkbox(checked=WorkItemState.f_is_capital,
                                on_change=WorkItemState.set_f_is_capital),
                    rx.text("Capital project", size="2"),
                    align="center", spacing="2",
                ),
                rx.hstack(
                    rx.checkbox(checked=WorkItemState.f_is_billable,
                                on_change=WorkItemState.set_f_is_billable),
                    rx.text("Billable to tenant", size="2"),
                    align="center", spacing="2",
                ),
                spacing="6",
            ),

            # Description
            _field("Description",
                rx.text_area(value=WorkItemState.f_description,
                             on_change=WorkItemState.set_f_description,
                             placeholder="Detailed description of the issue…",
                             width="100%", rows="3")),

            # Notes
            _field("Notes",
                rx.text_area(value=WorkItemState.f_notes,
                             on_change=WorkItemState.set_f_notes,
                             placeholder="Internal notes…",
                             width="100%", rows="2")),

            # Resolution summary
            _field("Resolution summary",
                rx.text_area(value=WorkItemState.f_resolution,
                             on_change=WorkItemState.set_f_resolution,
                             placeholder="How was this resolved?",
                             width="100%", rows="2")),

            # Feedback
            rx.cond(WorkItemState.form_error != "",
                rx.callout(WorkItemState.form_error, icon="triangle_alert",
                           color_scheme="red"), rx.fragment()),
            rx.cond(WorkItemState.form_success != "",
                rx.callout(WorkItemState.form_success, icon="check",
                           color_scheme="green"), rx.fragment()),

            # Buttons
            rx.hstack(
                rx.button(
                    rx.cond(WorkItemState.is_new, "Create work item", "Save work item"),
                    on_click=WorkItemState.save_work_item,
                    color_scheme="blue", size="2",
                ),
                rx.button("Cancel", on_click=WorkItemState.cancel_edit,
                          variant="outline", color_scheme="gray", size="2"),
                spacing="3",
            ),

            spacing="4", width="100%", align_items="start",
        ),
        style={
            "background": "white", "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}", "border_radius": "12px",
            "padding": "16px 20px",
            "width": "100%",
            "max_width": "100%",
            "box_sizing": "border-box",
        },
    )


# ── Actions tab ───────────────────────────────────────────────────────────────

def _action_row(a: ActionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(a.action_title, size="2", weight="bold")),
        rx.table.cell(rx.text(a.action_status, size="2", color="#555")),
        rx.table.cell(rx.text(a.due_date, size="2", color="#555")),
        rx.table.cell(rx.text(a.assigned_to, size="2", color="#555")),
        rx.table.cell(rx.text(a.vendor_name, size="2", color="#555")),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=WorkItemState.select_action(a.action_id))
        ),
        style=rx.cond(
            WorkItemState.selected_action_id == a.action_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


def _actions_tab() -> rx.Component:
    action_statuses = ["Open", "Waiting", "Done", "Canceled"]
    return rx.vstack(
        rx.cond(
            WorkItemState.actions.length() > 0,
            rx.table.root(
                rx.table.header(rx.table.row(
                    rx.table.column_header_cell("Action"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Due"),
                    rx.table.column_header_cell("Assigned to"),
                    rx.table.column_header_cell("Vendor"),
                    rx.table.column_header_cell(""),
                )),
                rx.table.body(rx.foreach(WorkItemState.actions, _action_row)),
                width="100%", variant="surface",
            ),
            rx.text("No actions yet.", color="#888", size="2"),
        ),

        rx.divider(),
        rx.text(
            rx.cond(WorkItemState.action_mode == "edit", "Edit action", "New action"),
            size="2", weight="bold", color=BRAND_DARK,
        ),
        rx.grid(
            _field("Action title *",
                rx.input(value=WorkItemState.a_title, on_change=WorkItemState.set_a_title,
                         placeholder="e.g. Call vendor for estimate", size="2", width="100%")),
            _field("Status",
                rx.select(action_statuses, value=WorkItemState.a_status,
                          on_change=WorkItemState.set_a_status, size="2", width="100%")),
            _field("Due date",
                rx.input(type="date", value=WorkItemState.a_due_date,
                         on_change=WorkItemState.set_a_due_date, size="2", width="100%")),
            _field("Assigned to",
                rx.input(value=WorkItemState.a_assigned_to,
                         on_change=WorkItemState.set_a_assigned_to,
                         placeholder="Staff name", size="2", width="100%")),
            columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
        ),
        rx.grid(
            _field("Vendor",
                rx.select(WorkItemState.vendor_names, value=WorkItemState.a_vendor,
                          on_change=WorkItemState.set_a_vendor, size="2", width="100%")),
            _field("Notes",
                rx.input(value=WorkItemState.a_notes, on_change=WorkItemState.set_a_notes,
                         placeholder="Notes…", size="2", width="100%")),
            columns="2", spacing="3", width="100%", style=RESPONSIVE_GRID_2,
        ),
        rx.cond(WorkItemState.action_form_error != "",
            rx.callout(WorkItemState.action_form_error, color_scheme="red"), rx.fragment()),
        rx.cond(WorkItemState.action_form_success != "",
            rx.callout(WorkItemState.action_form_success, color_scheme="green"), rx.fragment()),
        rx.hstack(
            rx.button(
                rx.cond(WorkItemState.action_mode == "edit", "Save action", "Add action"),
                on_click=WorkItemState.save_action, color_scheme="blue", size="2",
            ),
            rx.cond(
                WorkItemState.action_mode == "edit",
                rx.button("Delete", on_click=WorkItemState.delete_action,
                          color_scheme="red", variant="outline", size="2"),
                rx.fragment(),
            ),
            rx.button("Clear", on_click=WorkItemState.new_action,
                      variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Bids tab ──────────────────────────────────────────────────────────────────

def _bid_row(b: BidRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(b.vendor_name, size="2", weight="bold")),
        rx.table.cell(rx.text(b.bid_date, size="2", color="#555")),
        rx.table.cell(rx.text(b.bid_amount, size="2", weight="bold", color=BRAND_DARK)),
        rx.table.cell(rx.text(b.bid_status, size="2", color="#555")),
        rx.table.cell(rx.text(b.scope_summary, size="1", color="#888")),
        rx.table.cell(
            rx.cond(b.is_selected,
                rx.badge("Selected", color_scheme="green", variant="soft"),
                rx.fragment(),
            )
        ),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=WorkItemState.select_bid(b.bid_id))
        ),
        style=rx.cond(
            WorkItemState.selected_bid_id == b.bid_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


def _bids_tab() -> rx.Component:
    bid_statuses = ["Requested", "Received", "Accepted", "Rejected", "Canceled"]
    return rx.vstack(
        rx.cond(
            WorkItemState.bids.length() > 0,
            rx.table.root(
                rx.table.header(rx.table.row(
                    rx.table.column_header_cell("Vendor"),
                    rx.table.column_header_cell("Date"),
                    rx.table.column_header_cell("Amount"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Scope"),
                    rx.table.column_header_cell(""),
                    rx.table.column_header_cell(""),
                )),
                rx.table.body(rx.foreach(WorkItemState.bids, _bid_row)),
                width="100%", variant="surface",
            ),
            rx.text("No bids yet.", color="#888", size="2"),
        ),

        rx.divider(),
        rx.text(
            rx.cond(WorkItemState.bid_mode == "edit", "Edit bid", "New bid"),
            size="2", weight="bold", color=BRAND_DARK,
        ),
        rx.grid(
            _field("Vendor *",
                rx.select(WorkItemState.vendor_names, value=WorkItemState.b_vendor,
                          on_change=WorkItemState.set_b_vendor, size="2", width="100%")),
            _field("Bid date",
                rx.input(type="date", value=WorkItemState.b_date,
                         on_change=WorkItemState.set_b_date, size="2", width="100%")),
            _field("Amount",
                rx.input(value=WorkItemState.b_amount, on_change=WorkItemState.set_b_amount,
                         placeholder="0.00", size="2", width="100%")),
            _field("Status",
                rx.select(bid_statuses, value=WorkItemState.b_status,
                          on_change=WorkItemState.set_b_status, size="2", width="100%")),
            columns="4", spacing="3", width="100%", style=RESPONSIVE_GRID_4,
        ),
        _field("Scope summary",
            rx.text_area(value=WorkItemState.b_scope, on_change=WorkItemState.set_b_scope,
                         placeholder="What does this bid cover?", width="100%", rows="2")),
        _field("Notes",
            rx.input(value=WorkItemState.b_notes, on_change=WorkItemState.set_b_notes,
                     placeholder="Notes…", size="2", width="100%")),

        rx.cond(WorkItemState.bid_form_error != "",
            rx.callout(WorkItemState.bid_form_error, color_scheme="red"), rx.fragment()),
        rx.cond(WorkItemState.bid_form_success != "",
            rx.callout(WorkItemState.bid_form_success, color_scheme="green"), rx.fragment()),

        rx.hstack(
            rx.button(
                rx.cond(WorkItemState.bid_mode == "edit", "Save bid", "Add bid"),
                on_click=WorkItemState.save_bid, color_scheme="blue", size="2",
            ),
            rx.cond(
                WorkItemState.bid_mode == "edit",
                rx.button("⭐ Select as winner", on_click=WorkItemState.select_winning_bid,
                          color_scheme="green", variant="outline", size="2"),
                rx.fragment(),
            ),
            rx.button("Clear", on_click=WorkItemState.new_bid, variant="ghost", size="2"),
            spacing="3",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Detail panel ──────────────────────────────────────────────────────────────

def _detail_panel() -> rx.Component:
    return rx.vstack(
        rx.cond(
            WorkItemState.edit_mode,
            _edit_form(),
            _detail_header(),
        ),
        rx.cond(
            WorkItemState.selected_id > 0,
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Actions", value="actions"),
                    rx.tabs.trigger("Bids", value="bids"),
                ),
                rx.tabs.content(_actions_tab(), value="actions", padding_top="16px"),
                rx.tabs.content(_bids_tab(),    value="bids",    padding_top="16px"),
                default_value="actions", width="100%",
            ),
            rx.fragment(),
        ),
        spacing="3", width="100%", align_items="stretch",
    )


# ── Page ──────────────────────────────────────────────────────────────────────

WORK_ITEMS_RESIZER_SCRIPT = """
(function() {
    function installWorkItemsResizer() {
        if (window.__lucidWorkItemsResizerCleanup) {
            try { window.__lucidWorkItemsResizerCleanup(); } catch (e) {}
        }

        var isResizing = false;
        var startX = 0;
        var startWidth = 0;
        var leftPanel = null;

        function applySavedWidth() {
            var panel = document.getElementById('wi-list-panel');
            if (!panel) { return; }
            try {
                var savedW = parseInt(window.localStorage.getItem('lucidWorkItemsListWidth') || '', 10);
                if (savedW && savedW >= 300 && savedW <= 760) {
                    panel.style.width = savedW + 'px';
                    panel.style.minWidth = savedW + 'px';
                    panel.style.maxWidth = savedW + 'px';
                }
            } catch (err) {}
        }

        applySavedWidth();

        function getResizerFromEvent(e) {
            var path = e.composedPath ? e.composedPath() : [];
            for (var i = 0; i < path.length; i++) {
                if (path[i] && path[i].id === 'wi-panel-resizer') {
                    return path[i];
                }
            }
            var target = e.target;
            return target && target.closest ? target.closest('#wi-panel-resizer') : null;
        }

        function startResize(e) {
            var resizer = getResizerFromEvent(e);
            if (!resizer) { return; }
            leftPanel = document.getElementById('wi-list-panel');
            if (!leftPanel) { return; }
            try {
                var savedW = parseInt(window.localStorage.getItem('lucidWorkItemsListWidth') || '', 10);
                if (savedW && savedW >= 300 && savedW <= 760) {
                    leftPanel.style.width = savedW + 'px';
                    leftPanel.style.minWidth = savedW + 'px';
                    leftPanel.style.maxWidth = savedW + 'px';
                }
            } catch (err) {}
            isResizing = true;
            startX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            startWidth = leftPanel.offsetWidth || 420;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            if (resizer.setPointerCapture && e.pointerId) {
                try { resizer.setPointerCapture(e.pointerId); } catch (err) {}
            }
            e.preventDefault();
            e.stopPropagation();
        }

        function moveResize(e) {
            if (!isResizing || !leftPanel) { return; }
            var clientX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            var delta = clientX - startX;
            var newWidth = Math.min(Math.max(startWidth + delta, 300), 760);
            leftPanel.style.width = newWidth + 'px';
            leftPanel.style.minWidth = newWidth + 'px';
            leftPanel.style.maxWidth = newWidth + 'px';
            try { window.localStorage.setItem('lucidWorkItemsListWidth', String(newWidth)); } catch (err) {}
            e.preventDefault();
        }

        function stopResize() {
            if (!isResizing) { return; }
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

        window.__lucidWorkItemsResizerCleanup = function() {
            document.removeEventListener('pointerdown', startResize, true);
            document.removeEventListener('pointermove', moveResize, true);
            document.removeEventListener('pointerup', stopResize, true);
            document.removeEventListener('pointercancel', stopResize, true);
            document.removeEventListener('mousedown', startResize, true);
            document.removeEventListener('mousemove', moveResize, true);
            document.removeEventListener('mouseup', stopResize, true);
        };
    }

    installWorkItemsResizer();

    var workItemsObserver = new MutationObserver(function() {
        if (document.getElementById('wi-list-panel') && document.getElementById('wi-panel-resizer')) {
            installWorkItemsResizer();
            if (workItemsObserver) {
                workItemsObserver.disconnect();
                workItemsObserver = null;
            }
        }
    });

    if (document.body) {
        workItemsObserver.observe(document.body, { childList: true, subtree: true });
    }

    setTimeout(installWorkItemsResizer, 250);
    setTimeout(installWorkItemsResizer, 750);
    setTimeout(installWorkItemsResizer, 1500);
    setTimeout(installWorkItemsResizer, 3000);
})();
"""


def _work_items_content() -> rx.Component:
    return rx.box(
        rx.script(WORK_ITEMS_RESIZER_SCRIPT),
        rx.hstack(
            # Left panel — list
            rx.box(
                _list_panel(),
                id="wi-list-panel",
                style={
                    "width": "420px",
                    "min_width": "380px",
                    "max_width": "760px",
                    "max_height": "calc(100vh - 80px)",
                    "overflow_y": "auto",
                    "overflow_x": "hidden",
                    "background": "white",
                    "border": "1px solid #dde3f0",
                    "border_radius": "12px",
                    "padding": "20px",
                    "flex_shrink": "0",
                },
            ),
            # Drag handle
            rx.box(
                rx.box(
                    style={
                        "width": "4px",
                        "height": "40px",
                        "background": "#c5d0f0",
                        "border_radius": "2px",
                    }
                ),
                id="wi-panel-resizer",
                style={
                    "width": "12px",
                    "min_width": "12px",
                    "cursor": "col-resize",
                    "display": "flex",
                    "align_items": "center",
                    "justify_content": "center",
                    "align_self": "stretch",
                    "flex_shrink": "0",
                    "_hover": {"background": "#f0f4ff"},
                    "border_radius": "4px",
                    "transition": "background 0.15s",
                    "touch_action": "none",
                    "position": "relative",
                    "pointer_events": "auto",
                    "z_index": "10",
                },
            ),
            # Right panel — detail
            rx.box(
                rx.cond(
                    WorkItemState.show_detail,
                    _detail_panel(),
                    rx.vstack(
                        rx.text("👈 Select a work item or create a new one",
                                color="#888", size="3"),
                        align_items="center", padding_top="48px",
                    ),
                ),
                style={
                    "flex": "1",
                    "min_width": "0",
                    "max_width": "100%",
                    "max_height": "calc(100vh - 80px)",
                    "overflow_y": "auto",
                    "overflow_x": "hidden",
                    "padding_left": "16px",
                    "box_sizing": "border-box",
                },
            ),
            spacing="0",
            width="100%",
            align_items="start",
        ),
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
        flex_shrink="0",
        style={
            "box_sizing": "border-box",
            "overflow_x": "hidden",
        },
    )


def work_items_page() -> rx.Component:
    return page_shell(_work_items_content(), current_path="/work-items")
