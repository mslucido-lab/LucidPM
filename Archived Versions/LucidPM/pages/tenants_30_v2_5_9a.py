"""
Tenants page — unified tenant list + detail view.
Replaces the separate Tenants and Tenant Detail pages from Streamlit.

v2.5.9a — Persists TenantScreeningFactors on both new and edited screening records.

v2.5.9 — Adds Screening Phase 1.5 weighted assessment engine, persisted score suggestions, and immutable factor details.

v2.5.8 — Adds full Screening CRUD, editable screening records, and lightweight screening recommendations.

v2.5.7a — Fixes Screening select controls so Radix Select items never use empty-string values.

v2.5.7 — Adds Tenant Screening tab with Phase 1 screening record workflow.

v2.5.6 — Fixes RentDueDay warning callout color for Reflex frontend stability.

v2.5.5 — Adds advisory RentDueDay mismatch warning for mid-month lease starts.

v2.5.4 — Fixed Application report button URL generation:
  - Application button now uses a computed backend URL
  - Avoids fragile inline Reflex Var string concatenation

v2.5.3 — Added editable rent schedule rows:
  - Full CRUD for LeaseRentSchedule rows under selected lease
  - Select/edit/delete rent schedule rows
  - Add new schedule rows with increase type lookup
  - Keeps lease base rent sync behavior intact
"""

import reflex as rx
import pyodbc
import datetime
import os

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec, fmt_date,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES, TEST_DB_NAME,
)
from LucidPM_Reflex.components.sidebar import page_shell

try:
    from cryptography.fernet import Fernet
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


# ── Encryption helpers ────────────────────────────────────────────────────────

def _get_cipher():
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed.")
    key = os.environ.get("TENANTCRM_FERNET_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing TENANTCRM_FERNET_KEY environment variable.")
    return Fernet(key.encode("utf-8"))


def _encrypt(value: str) -> str:
    if not value or not value.strip():
        return ""
    return _get_cipher().encrypt(value.strip().encode("utf-8")).decode("utf-8")


def _decrypt(value: str) -> str:
    if not value or not value.strip():
        return ""
    try:
        return _get_cipher().decrypt(value.strip().encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def _last4(value: str) -> str:
    digits = "".join(c for c in str(value or "") if c.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


def _mask_ssn(last4: str) -> str:
    return f"XXX-XX-{last4}" if last4 else ""


def _mask_dl(last4: str) -> str:
    return f"*****{last4}" if last4 else ""


def _looks_masked_ssn(value: str) -> bool:
    return str(value or "").strip().startswith("XXX-XX-")


def _looks_masked_dl(value: str) -> bool:
    return str(value or "").strip().startswith("*****")


def _parse_notes_dict(notes: str) -> dict:
    """Parse Tenant Notes key/value lines.

    Supports multiline values by appending non-key continuation lines to the
    previous key. This is needed for applicant address blocks written as:
        Address: 6219 Cedar Ln
        Rowlett, TX 75089
    """
    result = {}
    current_key = ""
    for line in str(notes or "").split("\n"):
        raw = str(line or "").rstrip()
        if not raw.strip():
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            current_key = key.strip().lower()
            result[current_key] = value.strip()
        elif current_key:
            existing = result.get(current_key, "")
            result[current_key] = (existing + "\n" + raw.strip()).strip() if existing else raw.strip()
    return result


NOTES_FIELD_MAP = {
    "applicant":               "individual_name",
    "application date":        "application_date",
    "business":                "business_name",
    "business email":          "business_email",
    "business phone":          "business_phone",
    "property interest":       "property_interest",
    "desired sq ft":           "desired_sqft",
    "desired move-in":         "desired_movein",
    "monthly budget":          "rent_budget",
    "owner name":              "owner_name",
    "owner 1 address":         "owner_1_address",
    "owner 1 phone":           "owner_1_phone",
    "nature of business":      "nature_of_business",
    "when established":        "when_established",
    "payment contact":         "payment_contact",
    "payment contact phone":   "payment_contact_phone",
    "payment contact email":   "payment_contact_email",
    "annual sales":            "annual_sales",
    "bank name":               "bank_name",
    "dun & bradstreet":        "dun_bradstreet",
    "bankruptcy":              "bankruptcy",
    "remarks":                 "additional_remarks",
    "form of business":        "form_of_business",
    "business website":        "business_website",
    "address":                 "address",
    "present address":         "present_address",
    "city":                    "city",
    "state":                   "state",
    "zip":                     "zip",
    "emergency contact name":  "emergency_name",
    "emergency contact phone": "emergency_phone",
    "emergency contact email": "emergency_email",
    "trade reference 1":       "trade_ref_1",
    "reference 1 name":        "reference_1_name",
    "reference 1 years doing business": "reference_1_years",
    "reference 1 phone":       "reference_1_phone",
    "trade reference 2":       "trade_ref_2",
    "reference 2 name":        "reference_2_name",
    "reference 2 years doing business": "reference_2_years",
    "reference 2 phone":       "reference_2_phone",
    "trade reference 3":       "trade_ref_3",
    "reference 3 name":        "reference_3_name",
    "reference 3 years doing business": "reference_3_years",
    "reference 3 phone":       "reference_3_phone",
    "personal reference 1":    "personal_ref_1",
    "personal reference 2":    "personal_ref_2",
    "personal reference 3":    "personal_ref_3",
}


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


class LeaseSummary(rx.Base):
    lease_id: int = 0
    suite_label: str = ""
    lease_type: str = ""
    lease_term_type: str = ""
    lease_start: str = ""
    lease_end: str = ""
    rent_amount: str = ""


class RentScheduleRow(rx.Base):
    sched_id: int = 0
    effective_start: str = ""
    effective_end: str = ""
    rent_amount: str = ""
    increase_type: str = ""
    notes: str = ""


class ScreeningRecord(rx.Base):
    screening_id: int = 0
    ordered_date: str = ""
    completed_date: str = ""
    report_file_number: str = ""
    overall_result: str = ""
    credit_score: str = ""
    evictions: str = ""
    bankruptcies: str = ""
    collections: str = ""
    charge_offs: str = ""
    delinquent_accounts: str = ""
    income_to_rent: str = ""
    income_to_debt: str = ""
    income_to_debt_incl_rent: str = ""
    criminal_result: str = ""
    eviction_result: str = ""
    credit_source_type: str = ""
    risk_tier: str = ""
    deposit_recommended: str = ""
    notes: str = ""


# ── Tenant state ──────────────────────────────────────────────────────────────

class TenantState(AppState):

    # Tenant list
    tenant_list: list[TenantSummary] = []
    status_filter: str = "Active + Default"
    property_filter: str = "All"
    property_filter_options: list[str] = ["All"]
    sort_by: str = "Name"

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

    # Status and type lookups for edit/create form
    status_names: list[str] = []
    status_ids: list[int] = []
    type_names: list[str] = []
    type_ids: list[int] = []

    # Tenant edit / create form
    tenant_edit_mode: bool = False      # True = edit panel visible
    tenant_is_new: bool = False         # True = creating new tenant
    f_tenant_name: str = ""
    f_tenant_status: str = ""
    f_tenant_type: str = ""
    f_tenant_property: str = ""
    f_tenant_suite: str = ""
    f_tenant_notes: str = ""
    tenant_form_error: str = ""
    tenant_form_success: str = ""

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

    # ── Leases ────────────────────────────────────────────────────────────────
    leases: list[LeaseSummary] = []
    selected_lease_id: int = 0
    lease_mode: str = "new"           # "new" | "edit"
    confirm_delete_lease: bool = False

    # Lease form fields
    l_property: str = ""
    l_suite: str = ""
    l_lease_type: str = ""
    l_lease_term_type: str = ""
    l_start: str = ""
    l_end: str = ""
    l_rent: str = ""
    l_deposit: str = ""
    l_due_day: str = "1"
    l_next_due: str = ""
    l_show_anniversaries: bool = False

    lease_form_error: str = ""
    lease_form_success: str = ""

    # Lease lookup options (public so UI can bind)
    property_names: list[str] = []
    property_ids: list[int] = []
    suite_names: list[str] = []
    suite_ids: list[int] = []
    lease_type_names: list[str] = []
    lease_type_ids: list[int] = []
    lease_term_type_names: list[str] = []
    lease_term_type_ids: list[int] = []

    # Rent schedule
    rent_schedule: list[RentScheduleRow] = []
    selected_sched_id: int = 0
    sched_mode: str = "new"           # "new" | "edit"
    confirm_delete_sched: bool = False
    rs_start: str = ""
    rs_end: str = ""
    rs_rent: str = ""
    rs_increase_type: str = ""
    rs_notes: str = ""
    rent_schedule_form_error: str = ""
    rent_schedule_form_success: str = ""
    increase_type_names: list[str] = []
    increase_type_ids: list[int] = []

    # ── Sensitive info ────────────────────────────────────────────────────────
    sensitive_contact_id: int = 0
    sensitive_contact_name: str = ""
    # Display values (masked by default)
    si_ssn_display: str = ""
    si_dl_display: str = ""
    si_dob: str = ""
    # Raw decrypted (only populated when revealed)
    si_ssn_raw: str = ""
    si_dl_raw: str = ""
    si_last4_ssn: str = ""
    si_last4_dl: str = ""
    # Form fields (editable)
    si_ssn_input: str = ""
    si_dl_input: str = ""
    si_dob_input: str = ""
    si_revealed: bool = False
    si_form_error: str = ""
    si_form_success: str = ""
    si_no_contact: bool = False   # True when no primary contact exists

    # ── Screening tab state ──────────────────────────────────────────────────
    screening_records: list[ScreeningRecord] = []
    screening_loading: bool = False
    selected_screening_id: int = 0
    screening_mode: str = "new"
    confirm_delete_screening: bool = False

    s_ordered_date: str = ""
    s_completed_date: str = ""
    s_report_file_number: str = ""
    s_overall_result: str = ""
    s_credit_score: str = ""
    s_evictions: str = ""
    s_bankruptcies: str = ""
    s_collections: str = ""
    s_charge_offs: str = ""
    s_delinquent_accounts: str = ""
    s_income_to_rent: str = ""
    s_income_to_debt: str = ""
    s_income_to_debt_incl_rent: str = ""
    s_criminal_result: str = ""
    s_eviction_result: str = ""
    s_credit_source_type: str = "TenantReportX"
    s_credit_source_notes: str = ""
    s_risk_tier: str = ""
    s_deposit_recommended: str = ""
    s_notes: str = ""

    # Screening Phase 1.5 assessment state
    s_calculated_score: int = 0
    s_suggested_tier: str = ""
    s_suggested_decision: str = ""
    s_suggested_deposit_premium: float = 0.0
    s_hard_flags: list[str] = []
    s_assessment_run: bool = False
    _pending_factor_details: list[dict] = []

    screening_form_error: str = ""
    screening_form_success: str = ""
    show_screening_form: bool = False

    # ── Computed vars ─────────────────────────────────────────────────────────

    @rx.var
    def editing_banner(self) -> str:
        return f"Editing: {self.f_first} {self.f_last}".strip()

    @rx.var
    def comm_editing_banner(self) -> str:
        return f"Editing: {self.c_date} — {self.c_subject}".strip(" —")

    @rx.var
    def lease_editing_banner(self) -> str:
        parts = [x for x in [self.l_suite, self.l_lease_type, self.l_start] if x]
        return "Editing: " + " · ".join(parts) if parts else "Editing lease"

    @rx.var
    def rent_schedule_editing_banner(self) -> str:
        parts = [x for x in [self.rs_start, self.rs_rent, self.rs_increase_type] if x]
        return "Editing schedule: " + " · ".join(parts) if parts else "Editing rent schedule row"

    @rx.var
    def show_detail_panel(self) -> bool:
        return self.tenant_id > 0 or self.tenant_edit_mode

    @rx.var
    def tenant_location(self) -> str:
        parts = [x for x in [self.tenant_suite, self.tenant_property] if x]
        return " · ".join(parts)

    @rx.var
    def tenant_subtitle(self) -> str:
        parts = [x for x in [self.tenant_type, f"Tenant #{self.tenant_id}"] if x]
        return " · ".join(parts)

    @rx.var
    def is_applicant(self) -> bool:
        return self.tenant_status == "Applicant"

    @rx.var
    def application_report_url(self) -> str:
        if self.tenant_id <= 0:
            return "#"
        db_name = self.db or "TenantCRM"
        return f"http://localhost:8000/api/application-report-pdf?tenant_id={self.tenant_id}&db={db_name}"

    @rx.var
    def rent_due_day_warning(self) -> str:
        try:
            if not str(self.l_start or "").strip():
                return ""
            start = datetime.datetime.strptime(str(self.l_start), "%Y-%m-%d").date()
            if start.day == 1:
                return ""
            due_text = str(self.l_due_day or "").strip()
            if not due_text:
                return ""
            due_day = int(due_text)
            if due_day != start.day:
                return (
                    f"⚠️ Rent Due Day ({due_day}) does not match the lease start day ({start.day}). "
                    "This will cause the payment schedule and proforma totals to diverge."
                )
        except Exception:
            return ""
        return ""

    # ── Load / init ───────────────────────────────────────────────────────────

    def on_load(self):
        self._load_property_options()
        self.load_tenant_list()
        self._load_lease_lookups()

    def reload_on_db_change(self):
        """Called by AppState.toggle_db — reload everything for the new DB."""
        self.tenant_list = []
        self.tenant_id = 0
        self.selected_tenant_name = ""
        self.tenant_edit_mode = False
        self.contacts = []
        self.comms = []
        self.leases = []
        self.rent_schedule = []
        self.screening_records = []
        self.show_screening_form = False
        self._load_property_options()
        self.load_tenant_list()
        self._load_lease_lookups()

    def _load_property_options(self):
        rows = run_query(
            "SELECT PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_filter_options = ["All"] + [r["PropertyName"] for r in rows]

    def _load_lease_lookups(self):
        # Properties
        rows = run_query(
            "SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName",
            db=self.db,
        )
        self.property_names = [str(r["PropertyName"]) for r in rows]
        self.property_ids   = [int(r["PropertyID"]) for r in rows]

        # Tenant statuses
        rows = run_query(
            "SELECT TenantStatusID, TenantStatusName FROM TenantStatuses ORDER BY TenantStatusName",
            db=self.db,
        )
        self.status_names = [str(r["TenantStatusName"]) for r in rows]
        self.status_ids   = [int(r["TenantStatusID"]) for r in rows]

        # Tenant types
        rows = run_query(
            "SELECT TenantTypeID, TenantTypeName FROM TenantTypes ORDER BY TenantTypeName",
            db=self.db,
        )
        self.type_names = [str(r["TenantTypeName"]) for r in rows]
        self.type_ids   = [int(r["TenantTypeID"]) for r in rows]

        # Lease types
        rows = run_query(
            "SELECT LeaseTypeID, LeaseTypeName FROM LeaseTypes ORDER BY LeaseTypeName",
            db=self.db,
        )
        self.lease_type_names = [str(r["LeaseTypeName"]) for r in rows]
        self.lease_type_ids   = [int(r["LeaseTypeID"]) for r in rows]

        # Lease term types
        rows = run_query(
            "SELECT LeaseTermTypeID, LeaseTermTypeName FROM LeaseTermTypes ORDER BY LeaseTermTypeName",
            db=self.db,
        )
        self.lease_term_type_names = [str(r["LeaseTermTypeName"]) for r in rows]
        self.lease_term_type_ids   = [int(r["LeaseTermTypeID"]) for r in rows]

        # Rent increase types
        # Some databases do not have DisplayOrder on LeaseRentIncreaseTypes yet.
        # Avoid startup failure by checking the schema before choosing ORDER BY.
        try:
            col_rows = run_query(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' "
                "AND TABLE_NAME = 'LeaseRentIncreaseTypes' "
                "AND COLUMN_NAME = 'DisplayOrder'",
                db=self.db,
            )
            order_by = "DisplayOrder, IncreaseTypeName" if col_rows else "IncreaseTypeName"
            rows = run_query(
                "SELECT LeaseRentIncreaseTypeID, IncreaseTypeName "
                f"FROM LeaseRentIncreaseTypes ORDER BY {order_by}",
                db=self.db,
            )
        except Exception:
            rows = run_query(
                "SELECT LeaseRentIncreaseTypeID, IncreaseTypeName "
                "FROM LeaseRentIncreaseTypes ORDER BY IncreaseTypeName",
                db=self.db,
            )

        self.increase_type_names = [str(r["IncreaseTypeName"]) for r in rows]
        self.increase_type_ids   = [int(r["LeaseRentIncreaseTypeID"]) for r in rows]

    def _load_suite_options(self, property_name: str):
        """Load suite options filtered to the selected property."""
        if not property_name or property_name not in self.property_names:
            self.suite_names = ["(No suite)"]
            self.suite_ids   = [0]
            return
        prop_id = self.property_ids[self.property_names.index(property_name)]
        rows = run_query(
            "SELECT SuiteID, SuiteLabel FROM PropertySuites "
            "WHERE PropertyID = ? AND IsActive = 1 ORDER BY SortOrder, SuiteLabel",
            (prop_id,), db=self.db,
        )
        self.suite_names = ["(No suite)"] + [str(r["SuiteLabel"]) for r in rows]
        self.suite_ids   = [0] + [int(r["SuiteID"]) for r in rows]

    # ── Tenant list ───────────────────────────────────────────────────────────

    def load_tenant_list(self):
        conditions = []
        params = []
        if self.status_filter == "Active + Default":
            conditions.append("s.TenantStatusName IN ('Active', 'Default')")
        elif self.status_filter == "Active + Applicant":
            conditions.append("s.TenantStatusName IN ('Active', 'Applicant')")
        elif self.status_filter != "All":
            conditions.append("s.TenantStatusName = ?")
            params.append(self.status_filter)
        if self.property_filter != "All":
            conditions.append("p.PropertyName = ?")
            params.append(self.property_filter)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order = "ps.SuiteLabel, t.TenantName" if self.sort_by == "Suite" else "t.TenantName"
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, s.TenantStatusName, "
            "ps.SuiteLabel, p.PropertyName "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            f"{where} ORDER BY {order}",
            tuple(params), db=self.db,
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
        self.tenant_ids   = [r["TenantID"] for r in rows]
        if rows and self.tenant_id == 0:
            self._load_tenant_detail(rows[0]["TenantID"])

    def set_status_filter(self, v: str):
        self.status_filter = v
        self.load_tenant_list()

    def set_property_filter(self, v: str):
        self.property_filter = v
        self.load_tenant_list()

    def set_sort_by(self, v: str):
        self.sort_by = v
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
            (tenant_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.tenant_id             = r["TenantID"]
        self.selected_tenant_name  = str(r.get("TenantName") or "")
        self.tenant_status         = str(r.get("TenantStatusName") or "")
        self.tenant_type           = str(r.get("TenantTypeName") or "")
        self.tenant_suite          = str(r.get("SuiteLabel") or "")
        self.tenant_property       = str(r.get("PropertyName") or "")
        self.tenant_notes          = str(r.get("Notes") or "")
        name = str(r.get("TenantName") or "")
        self.tenant_initials = "".join([w[0].upper() for w in name.split() if w][:2]) or "?"
        self.load_contacts()
        self.load_comms()
        self.load_leases()
        self.load_screening_records()
        self.new_contact()
        self.new_comm()
        self.new_lease()
        self._load_sensitive_info(tenant_id)
        self.tenant_edit_mode = False
        self.tenant_form_error = ""
        self.tenant_form_success = ""

    # ── Screening ─────────────────────────────────────────────────────────────

    def _fmt_screening_date(self, v) -> str:
        if v is None:
            return ""
        if hasattr(v, "strftime"):
            return v.strftime("%m/%d/%Y")
        return str(v)

    def _fmt_screening_money(self, v) -> str:
        if v is None or str(v).strip() == "":
            return ""
        try:
            return f"${float(v):,.2f}"
        except Exception:
            return str(v)

    def load_screening_records(self):
        self.screening_loading = True
        self.screening_form_error = ""
        if self.tenant_id <= 0:
            self.screening_records = []
            self.screening_loading = False
            return
        try:
            rows = run_query(
                "SELECT TenantScreeningID, OrderedDate, CompletedDate, ReportFileNumber, OverallResult, "
                "CreditScore, Evictions, Bankruptcies, Collections, ChargeOffs, DelinquentAccounts, "
                "IncomeToRent, IncomeToDebt, IncomeToDebtInclRent, CriminalResult, EvictionResult, "
                "CreditSourceType, RiskTier, DepositRecommended, Notes "
                "FROM TenantScreenings WHERE TenantID = ? ORDER BY CreatedDate DESC, TenantScreeningID DESC",
                (self.tenant_id,), db=self.db,
            )
            self.screening_records = [
                ScreeningRecord(
                    screening_id=int(r.get("TenantScreeningID") or 0),
                    ordered_date=self._fmt_screening_date(r.get("OrderedDate")),
                    completed_date=self._fmt_screening_date(r.get("CompletedDate")),
                    report_file_number=str(r.get("ReportFileNumber") or ""),
                    overall_result=str(r.get("OverallResult") or ""),
                    credit_score=str(r.get("CreditScore") or ""),
                    evictions=str(r.get("Evictions") or ""),
                    bankruptcies=str(r.get("Bankruptcies") or ""),
                    collections=str(r.get("Collections") or ""),
                    charge_offs=str(r.get("ChargeOffs") or ""),
                    delinquent_accounts=str(r.get("DelinquentAccounts") or ""),
                    income_to_rent=str(r.get("IncomeToRent") or ""),
                    income_to_debt=str(r.get("IncomeToDebt") or ""),
                    income_to_debt_incl_rent=str(r.get("IncomeToDebtInclRent") or ""),
                    criminal_result=str(r.get("CriminalResult") or ""),
                    eviction_result=str(r.get("EvictionResult") or ""),
                    credit_source_type=str(r.get("CreditSourceType") or ""),
                    risk_tier=str(r.get("RiskTier") or ""),
                    deposit_recommended=self._fmt_screening_money(r.get("DepositRecommended")),
                    notes=str(r.get("Notes") or ""),
                )
                for r in rows
            ]
        except Exception as ex:
            self.screening_records = []
            self.screening_form_error = f"Could not load screening records: {ex}"
        finally:
            self.screening_loading = False

    def clear_screening_form(self):
        self.selected_screening_id = 0
        self.screening_mode = "new"
        self.confirm_delete_screening = False
        self.s_ordered_date = ""
        self.s_completed_date = ""
        self.s_report_file_number = ""
        self.s_overall_result = ""
        self.s_credit_score = ""
        self.s_evictions = ""
        self.s_bankruptcies = ""
        self.s_collections = ""
        self.s_charge_offs = ""
        self.s_delinquent_accounts = ""
        self.s_income_to_rent = ""
        self.s_income_to_debt = ""
        self.s_income_to_debt_incl_rent = ""
        self.s_criminal_result = ""
        self.s_eviction_result = ""
        self.s_credit_source_type = "TenantReportX"
        self.s_credit_source_notes = ""
        self.s_risk_tier = ""
        self.s_deposit_recommended = ""
        self.s_notes = ""
        self.s_calculated_score = 0
        self.s_suggested_tier = ""
        self.s_suggested_decision = ""
        self.s_suggested_deposit_premium = 0.0
        self.s_hard_flags = []
        self.s_assessment_run = False
        self._pending_factor_details = []

    def start_new_screening_record(self):
        self.clear_screening_form()
        self.s_ordered_date = datetime.date.today().strftime("%Y-%m-%d")
        self.screening_form_error = ""
        self.screening_form_success = ""
        self.show_screening_form = True

    def cancel_screening_form(self):
        self.show_screening_form = False
        self.screening_form_error = ""

    def set_s_ordered_date(self, v): self.s_ordered_date = v
    def set_s_completed_date(self, v): self.s_completed_date = v
    def set_s_report_file_number(self, v): self.s_report_file_number = v
    def set_s_overall_result(self, v): self.s_overall_result = v
    def set_s_credit_score(self, v): self.s_credit_score = v
    def set_s_evictions(self, v): self.s_evictions = v
    def set_s_bankruptcies(self, v): self.s_bankruptcies = v
    def set_s_collections(self, v): self.s_collections = v
    def set_s_charge_offs(self, v): self.s_charge_offs = v
    def set_s_delinquent_accounts(self, v): self.s_delinquent_accounts = v
    def set_s_income_to_rent(self, v): self.s_income_to_rent = v
    def set_s_income_to_debt(self, v): self.s_income_to_debt = v
    def set_s_income_to_debt_incl_rent(self, v): self.s_income_to_debt_incl_rent = v
    def set_s_criminal_result(self, v): self.s_criminal_result = v
    def set_s_eviction_result(self, v): self.s_eviction_result = v
    def set_s_credit_source_type(self, v): self.s_credit_source_type = v
    def set_s_credit_source_notes(self, v): self.s_credit_source_notes = v
    def set_s_risk_tier(self, v): self.s_risk_tier = v
    def set_s_deposit_recommended(self, v): self.s_deposit_recommended = v
    def set_s_notes(self, v): self.s_notes = v

    def _date_or_none(self, value: str):
        value = str(value or "").strip()
        if not value:
            return None
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _int_or_none(self, value: str):
        value = str(value or "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _float_or_none(self, value: str):
        value = str(value or "").replace("$", "").replace(",", "").strip()
        if ":" in value:
            value = value.split(":", 1)[0].strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _money_input_value(self, value) -> str:
        if value is None or str(value).strip() == "":
            return ""
        try:
            amount = float(value)
            return str(int(amount)) if amount.is_integer() else f"{amount:.2f}"
        except Exception:
            return str(value or "")

    def _latest_monthly_rent_amount(self) -> float:
        try:
            rows = run_query(
                "SELECT TOP 1 RentAmount FROM Leases WHERE TenantID = ? ORDER BY LeaseStart DESC, LeaseID DESC",
                (self.tenant_id,), db=self.db,
            )
            if rows:
                return float(rows[0].get("RentAmount") or 0)
        except Exception:
            return 0.0
        return 0.0

    def run_screening_assessment(self):
        """
        Full weighted scorecard — financial signals only.
        Score out of 100. Hard flags cap tier at Elevated regardless of total.
        All results are advisory — user can edit every field before saving.
        """
        score = 0
        hard_flags = []
        factor_details = []

        # EVICTIONS (30 pts)
        evictions = self._int_or_none(self.s_evictions) or 0
        eviction_search_fail = str(self.s_eviction_result or "").strip().lower() == "records found"
        if evictions == 0 and not eviction_search_fail:
            ev_pts, ev_flag = 30, False
        elif evictions == 1 or eviction_search_fail:
            ev_pts, ev_flag = 15, False
        else:
            ev_pts, ev_flag = 0, True
            hard_flags.append(f"2+ evictions ({evictions} reported)")
        score += ev_pts
        factor_details.append({
            "FactorCode": "EVICTIONS", "PointsEarned": ev_pts, "PointsMax": 30,
            "HardFlag": ev_flag,
            "Notes": f"{evictions} eviction(s); search: {self.s_eviction_result or 'not entered'}",
        })

        # CREDIT SCORE (25 pts)
        credit = self._int_or_none(self.s_credit_score) or 0
        if credit >= 700:
            cr_pts = 25
        elif credit >= 650:
            cr_pts = 20
        elif credit >= 600:
            cr_pts = 15
        elif credit >= 550:
            cr_pts = 8
        else:
            cr_pts = 0
        score += cr_pts
        factor_details.append({
            "FactorCode": "CREDIT_SCORE", "PointsEarned": cr_pts, "PointsMax": 25,
            "HardFlag": False,
            "Notes": f"Credit score: {credit if credit else 'not entered'}",
        })

        # BANKRUPTCY (20 pts)
        bankruptcies = self._int_or_none(self.s_bankruptcies) or 0
        if bankruptcies == 0:
            bk_pts, bk_flag = 20, False
        else:
            bk_pts, bk_flag = 10, True
            hard_flags.append(f"Bankruptcy on record ({bankruptcies}) — confirm discharge date")
        score += bk_pts
        factor_details.append({
            "FactorCode": "BANKRUPTCY", "PointsEarned": bk_pts, "PointsMax": 20,
            "HardFlag": bk_flag,
            "Notes": f"{bankruptcies} bankruptcy record(s)",
        })

        # COLLECTIONS + CHARGE-OFFS (15 pts)
        total_derog = (self._int_or_none(self.s_collections) or 0) + (self._int_or_none(self.s_charge_offs) or 0)
        if total_derog == 0:
            dg_pts = 15
        elif total_derog <= 2:
            dg_pts = 10
        else:
            dg_pts = 5
        score += dg_pts
        factor_details.append({
            "FactorCode": "COLLECTIONS", "PointsEarned": dg_pts, "PointsMax": 15,
            "HardFlag": False,
            "Notes": f"{self._int_or_none(self.s_collections) or 0} collection(s), {self._int_or_none(self.s_charge_offs) or 0} charge-off(s)",
        })

        # INCOME TO RENT (10 pts)
        itr = self._float_or_none(self.s_income_to_rent) or 0.0
        if itr >= 4.0:
            itr_pts, itr_flag = 10, False
        elif itr >= 3.0:
            itr_pts, itr_flag = 7, False
        elif itr >= 2.5:
            itr_pts, itr_flag = 4, False
        elif itr > 0:
            itr_pts, itr_flag = 0, True
            hard_flags.append(f"Income:Rent {itr:.1f}x below 2.5x minimum")
        else:
            itr_pts, itr_flag = 0, False
        score += itr_pts
        factor_details.append({
            "FactorCode": "INCOME_RENT", "PointsEarned": itr_pts, "PointsMax": 10,
            "HardFlag": itr_flag,
            "Notes": f"Income:Rent: {itr:.2f}x" if itr else "Income:Rent not entered",
        })

        # DETERMINE TIER
        if hard_flags:
            tier = "High" if score < 40 else "Elevated"
        else:
            if score >= 80:
                tier = "Low"
            elif score >= 60:
                tier = "Moderate"
            elif score >= 40:
                tier = "Elevated"
            else:
                tier = "High"

        # DETERMINE DECISION + DEPOSIT PREMIUM
        if tier in ("Low", "Moderate"):
            decision, premium = "Approve", 0.0
        elif tier == "Elevated":
            decision, premium = "Conditional", 0.5
        else:
            decision, premium = "Decline Recommended", 1.0

        # SET STATE
        self.s_calculated_score = score
        self.s_suggested_tier = tier
        self.s_suggested_decision = decision
        self.s_suggested_deposit_premium = premium
        self.s_hard_flags = hard_flags
        self.s_assessment_run = True
        self._pending_factor_details = factor_details

        # Pre-populate user decision fields (user can edit before saving)
        self.s_overall_result = (
            "Pass" if tier in ("Low", "Moderate") else
            "Conditional" if tier == "Elevated" else "Fail"
        )
        self.s_risk_tier = tier
        rent = self._latest_monthly_rent_amount()
        if premium > 0 and rent > 0:
            self.s_deposit_recommended = str(int(round(rent * (1 + premium))))

        self.screening_form_success = (
            f"Assessment complete: {score}/100 — {tier} — {decision}. "
            "Review and edit fields before saving."
        )

    def select_screening_record(self, screening_id: int):
        self.screening_form_error = ""
        self.screening_form_success = ""
        self.confirm_delete_screening = False
        sid = int(screening_id or 0)
        if sid <= 0:
            self.screening_form_error = "Select a screening record first."
            return
        try:
            rows = run_query(
                "SELECT TenantScreeningID, OrderedDate, CompletedDate, ReportFileNumber, OverallResult, "
                "CreditScore, Evictions, Bankruptcies, Collections, ChargeOffs, DelinquentAccounts, "
                "IncomeToRent, IncomeToDebt, IncomeToDebtInclRent, CriminalResult, EvictionResult, "
                "CreditSourceType, CreditSourceNotes, RiskTier, DepositRecommended, Notes, "
                "CalculatedScore, SuggestedTier, SuggestedDecision, SuggestedDepositPremium "
                "FROM TenantScreenings WHERE TenantScreeningID = ? AND TenantID = ?",
                (sid, self.tenant_id), db=self.db,
            )
            if not rows:
                self.screening_form_error = "Screening record not found."
                return
            r = rows[0]
            def date_input(v):
                if v is None:
                    return ""
                if hasattr(v, "strftime"):
                    return v.strftime("%Y-%m-%d")
                return str(v)[:10]

            self.selected_screening_id = sid
            self.screening_mode = "edit"
            self.s_ordered_date = date_input(r.get("OrderedDate"))
            self.s_completed_date = date_input(r.get("CompletedDate"))
            self.s_report_file_number = str(r.get("ReportFileNumber") or "")
            self.s_overall_result = str(r.get("OverallResult") or "")
            self.s_credit_score = str(r.get("CreditScore") or "")
            self.s_evictions = str(r.get("Evictions") or "")
            self.s_bankruptcies = str(r.get("Bankruptcies") or "")
            self.s_collections = str(r.get("Collections") or "")
            self.s_charge_offs = str(r.get("ChargeOffs") or "")
            self.s_delinquent_accounts = str(r.get("DelinquentAccounts") or "")
            self.s_income_to_rent = str(r.get("IncomeToRent") or "")
            self.s_income_to_debt = str(r.get("IncomeToDebt") or "")
            self.s_income_to_debt_incl_rent = str(r.get("IncomeToDebtInclRent") or "")
            self.s_criminal_result = str(r.get("CriminalResult") or "")
            self.s_eviction_result = str(r.get("EvictionResult") or "")
            self.s_credit_source_type = str(r.get("CreditSourceType") or "TenantReportX")
            self.s_credit_source_notes = str(r.get("CreditSourceNotes") or "")
            self.s_risk_tier = str(r.get("RiskTier") or "")
            self.s_deposit_recommended = self._money_input_value(r.get("DepositRecommended"))
            self.s_notes = str(r.get("Notes") or "")
            self.s_calculated_score = int(r.get("CalculatedScore") or 0)
            self.s_suggested_tier = str(r.get("SuggestedTier") or "")
            self.s_suggested_decision = str(r.get("SuggestedDecision") or "")
            self.s_suggested_deposit_premium = float(r.get("SuggestedDepositPremium") or 0.0)
            self.s_hard_flags = []
            self.s_assessment_run = bool(self.s_calculated_score or self.s_suggested_tier or self.s_suggested_decision)
            self._pending_factor_details = []
            self.show_screening_form = True
        except Exception as ex:
            self.screening_form_error = f"Could not load screening record: {ex}"

    def save_screening_record(self):
        self.screening_form_error = ""
        self.screening_form_success = ""
        if self.tenant_id <= 0:
            self.screening_form_error = "Select a tenant first."
            return
        if not str(self.s_ordered_date or "").strip():
            self.screening_form_error = "Ordered Date is required."
            return

        ordered_date = self._date_or_none(self.s_ordered_date)
        if ordered_date is None:
            self.screening_form_error = "Ordered Date must be a valid date."
            return
        completed_date = self._date_or_none(self.s_completed_date)

        values = (
            ordered_date,
            completed_date,
            str(self.s_report_file_number or "").strip() or None,
            str(self.s_overall_result or "").strip() or None,
            self._int_or_none(self.s_credit_score),
            self._int_or_none(self.s_evictions),
            self._int_or_none(self.s_bankruptcies),
            self._int_or_none(self.s_collections),
            self._int_or_none(self.s_charge_offs),
            self._int_or_none(self.s_delinquent_accounts),
            self._float_or_none(self.s_income_to_rent),
            self._float_or_none(self.s_income_to_debt),
            self._float_or_none(self.s_income_to_debt_incl_rent),
            str(self.s_criminal_result or "").strip() or None,
            str(self.s_eviction_result or "").strip() or None,
            str(self.s_credit_source_type or "").strip() or None,
            str(self.s_credit_source_notes or "").strip() or None,
            str(self.s_risk_tier or "").strip() or None,
            self._float_or_none(self.s_deposit_recommended),
            str(self.s_notes or "").strip() or None,
            self._int_or_none(str(self.s_calculated_score)) if self.s_assessment_run else None,
            str(self.s_suggested_tier or "").strip() or None,
            str(self.s_suggested_decision or "").strip() or None,
            self.s_suggested_deposit_premium if self.s_assessment_run else None,
        )

        try:
            saved_screening_id = 0
            if self.screening_mode == "edit" and int(self.selected_screening_id or 0) > 0:
                saved_screening_id = int(self.selected_screening_id)
                run_exec(
                    "UPDATE TenantScreenings SET OrderedDate=?, CompletedDate=?, ReportFileNumber=?, OverallResult=?, "
                    "CreditScore=?, Evictions=?, Bankruptcies=?, Collections=?, ChargeOffs=?, DelinquentAccounts=?, "
                    "IncomeToRent=?, IncomeToDebt=?, IncomeToDebtInclRent=?, CriminalResult=?, EvictionResult=?, "
                    "CreditSourceType=?, CreditSourceNotes=?, RiskTier=?, DepositRecommended=?, Notes=?, "
                    "CalculatedScore=?, SuggestedTier=?, SuggestedDecision=?, SuggestedDepositPremium=? "
                    "WHERE TenantScreeningID=? AND TenantID=?",
                    values + (saved_screening_id, self.tenant_id),
                    db=self.db,
                )
                message = "Screening record updated."
            else:
                run_exec(
                    "INSERT INTO TenantScreenings "
                    "(TenantID, OrderedDate, CompletedDate, ReportFileNumber, OverallResult, "
                    "CreditScore, Evictions, Bankruptcies, Collections, ChargeOffs, DelinquentAccounts, "
                    "IncomeToRent, IncomeToDebt, IncomeToDebtInclRent, CriminalResult, EvictionResult, "
                    "CreditSourceType, CreditSourceNotes, RiskTier, DepositRecommended, Notes, "
                    "CalculatedScore, SuggestedTier, SuggestedDecision, SuggestedDepositPremium) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (self.tenant_id,) + values,
                    db=self.db,
                )
                rows = run_query(
                    "SELECT TOP 1 TenantScreeningID FROM TenantScreenings "
                    "WHERE TenantID=? ORDER BY CreatedDate DESC, TenantScreeningID DESC",
                    (self.tenant_id,), db=self.db,
                )
                saved_screening_id = int(rows[0].get("TenantScreeningID") or 0) if rows else 0
                message = "Screening record saved."

            if saved_screening_id > 0:
                run_exec(
                    "DELETE FROM TenantScreeningFactors WHERE TenantScreeningID = ?",
                    (saved_screening_id,),
                    db=self.db,
                )
                if self.s_assessment_run and self._pending_factor_details:
                    for factor in self._pending_factor_details:
                        run_exec(
                            "INSERT INTO TenantScreeningFactors "
                            "(TenantScreeningID, FactorCode, PointsEarned, PointsMax, HardFlag, Notes) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                saved_screening_id,
                                str(factor.get("FactorCode") or ""),
                                int(factor.get("PointsEarned") or 0),
                                int(factor.get("PointsMax") or 0),
                                1 if factor.get("HardFlag") else 0,
                                str(factor.get("Notes") or ""),
                            ),
                            db=self.db,
                        )
            self.clear_screening_form()
            self.show_screening_form = False
            self.load_screening_records()
            self.screening_form_success = message
        except Exception as ex:
            self.screening_form_error = f"Could not save screening record: {ex}"

    def confirm_delete_screening_record(self):
        self.confirm_delete_screening = True

    def cancel_delete_screening_record(self):
        self.confirm_delete_screening = False

    def delete_screening_record(self):
        self.screening_form_error = ""
        self.screening_form_success = ""
        sid = int(self.selected_screening_id or 0)
        if sid <= 0:
            self.screening_form_error = "Select a screening record to delete."
            return
        try:
            run_exec(
                "DELETE FROM TenantScreeningFactors WHERE TenantScreeningID = ?",
                (sid,), db=self.db,
            )
            run_exec(
                "DELETE FROM TenantScreenings WHERE TenantScreeningID = ? AND TenantID = ?",
                (sid, self.tenant_id), db=self.db,
            )
            self.clear_screening_form()
            self.show_screening_form = False
            self.load_screening_records()
            self.screening_form_success = "Screening record deleted."
        except Exception as ex:
            self.screening_form_error = f"Could not delete screening record: {ex}"

    # ── Sensitive info ────────────────────────────────────────────────────────

    def _load_sensitive_info(self, tenant_id: int):
        """Load primary contact and their encrypted sensitive info."""
        self.si_revealed = False
        self.si_form_error = ""
        self.si_form_success = ""
        self.si_no_contact = False

        # Find primary contact for this tenant
        contacts = run_query(
            "SELECT TOP 1 ContactID, "
            "ISNULL(FirstName,'') + ' ' + ISNULL(LastName,'') AS FullName, "
            "ISNULL(ContactRole,'') AS ContactRole "
            "FROM Contacts WHERE TenantID = ? AND IsPrimary = 1 "
            "ORDER BY ContactID",
            (tenant_id,), db=self.db,
        )
        if not contacts:
            # Fall back to any contact
            contacts = run_query(
                "SELECT TOP 1 ContactID, "
                "ISNULL(FirstName,'') + ' ' + ISNULL(LastName,'') AS FullName, "
                "ISNULL(ContactRole,'') AS ContactRole "
                "FROM Contacts WHERE TenantID = ? ORDER BY ContactID",
                (tenant_id,), db=self.db,
            )

        if not contacts:
            self.sensitive_contact_id = 0
            self.sensitive_contact_name = ""
            self.si_no_contact = True
            self.si_ssn_display = ""
            self.si_dl_display = ""
            self.si_dob = ""
            self.si_ssn_input = ""
            self.si_dl_input = ""
            self.si_dob_input = ""
            self.si_last4_ssn = ""
            self.si_last4_dl = ""
            return

        c = contacts[0]
        self.sensitive_contact_id = int(c["ContactID"])
        self.sensitive_contact_name = str(c.get("FullName") or "").strip()

        # Load encrypted record
        rows = run_query(
            "SELECT SSN_Encrypted, DL_Encrypted, DOB, Last4SSN, DL_Last4 "
            "FROM ContactSensitiveInfo WHERE ContactID = ?",
            (self.sensitive_contact_id,), db=self.db,
        )
        if rows:
            r = rows[0]
            self.si_last4_ssn = str(r.get("Last4SSN") or "")
            self.si_last4_dl  = str(r.get("DL_Last4") or "")
            dob = r.get("DOB")
            self.si_dob = fmt_date(dob) if dob else ""
            self.si_dob_input = dob.isoformat() if isinstance(dob, datetime.date) else ""
        else:
            self.si_last4_ssn = ""
            self.si_last4_dl  = ""
            self.si_dob = ""
            self.si_dob_input = ""

        # Show masked by default
        self.si_ssn_display = _mask_ssn(self.si_last4_ssn)
        self.si_dl_display  = _mask_dl(self.si_last4_dl)
        self.si_ssn_input   = self.si_ssn_display
        self.si_dl_input    = self.si_dl_display
        self.si_ssn_raw = ""
        self.si_dl_raw  = ""

    def toggle_reveal_sensitive(self, val: bool):
        self.si_revealed = val
        if not self.sensitive_contact_id:
            return
        if val:
            # Decrypt and show full values
            rows = run_query(
                "SELECT SSN_Encrypted, DL_Encrypted FROM ContactSensitiveInfo WHERE ContactID = ?",
                (self.sensitive_contact_id,), db=self.db,
            )
            if rows:
                r = rows[0]
                try:
                    self.si_ssn_raw = _decrypt(str(r.get("SSN_Encrypted") or ""))
                except Exception:
                    self.si_ssn_raw = ""
                try:
                    self.si_dl_raw = _decrypt(str(r.get("DL_Encrypted") or ""))
                except Exception:
                    self.si_dl_raw = ""
                self.si_ssn_input = self.si_ssn_raw
                self.si_dl_input  = self.si_dl_raw
        else:
            self.si_ssn_raw   = ""
            self.si_dl_raw    = ""
            self.si_ssn_input = self.si_ssn_display
            self.si_dl_input  = self.si_dl_display

    def set_si_ssn_input(self, v: str):   self.si_ssn_input = v
    def set_si_dl_input(self, v: str):    self.si_dl_input = v
    def set_si_dob_input(self, v: str):   self.si_dob_input = v

    def save_sensitive_info(self):
        self.si_form_error = ""
        self.si_form_success = ""
        if not self.sensitive_contact_id:
            self.si_form_error = "No contact found. Create a primary contact first."
            return

        # Determine real SSN and DL — if still masked, keep existing encrypted value
        ssn_to_save = "" if _looks_masked_ssn(self.si_ssn_input) else self.si_ssn_input.strip()
        dl_to_save  = "" if _looks_masked_dl(self.si_dl_input) else self.si_dl_input.strip()

        try:
            ssn_enc  = _encrypt(ssn_to_save) if ssn_to_save else None
            dl_enc   = _encrypt(dl_to_save) if dl_to_save else None
            last4ssn = _last4(ssn_to_save) if ssn_to_save else self.si_last4_ssn
            last4dl  = _last4(dl_to_save) if dl_to_save else self.si_last4_dl

            try:
                dob_val = datetime.date.fromisoformat(self.si_dob_input) if self.si_dob_input else None
            except Exception:
                dob_val = None

            now = datetime.datetime.now()

            existing = run_query(
                "SELECT ContactSensitiveInfoID FROM ContactSensitiveInfo WHERE ContactID = ?",
                (self.sensitive_contact_id,), db=self.db,
            )

            if existing:
                # Only update encrypted fields if new values were provided
                if ssn_to_save and dl_to_save:
                    run_exec(
                        "UPDATE ContactSensitiveInfo SET SSN_Encrypted=?, DL_Encrypted=?, "
                        "DOB=?, Last4SSN=?, DL_Last4=?, UpdatedOn=? WHERE ContactID=?",
                        (ssn_enc, dl_enc, dob_val, last4ssn, last4dl, now,
                         self.sensitive_contact_id), db=self.db,
                    )
                elif ssn_to_save:
                    run_exec(
                        "UPDATE ContactSensitiveInfo SET SSN_Encrypted=?, DOB=?, "
                        "Last4SSN=?, UpdatedOn=? WHERE ContactID=?",
                        (ssn_enc, dob_val, last4ssn, now, self.sensitive_contact_id),
                        db=self.db,
                    )
                elif dl_to_save:
                    run_exec(
                        "UPDATE ContactSensitiveInfo SET DL_Encrypted=?, DOB=?, "
                        "DL_Last4=?, UpdatedOn=? WHERE ContactID=?",
                        (dl_enc, dob_val, last4dl, now, self.sensitive_contact_id),
                        db=self.db,
                    )
                else:
                    # DOB only update
                    run_exec(
                        "UPDATE ContactSensitiveInfo SET DOB=?, UpdatedOn=? WHERE ContactID=?",
                        (dob_val, now, self.sensitive_contact_id), db=self.db,
                    )
            else:
                run_exec(
                    "INSERT INTO ContactSensitiveInfo "
                    "(ContactID, SSN_Encrypted, DL_Encrypted, DOB, Last4SSN, DL_Last4, CreatedOn, UpdatedOn) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (self.sensitive_contact_id, ssn_enc, dl_enc, dob_val,
                     last4ssn, last4dl, now, now), db=self.db,
                )

            self.si_form_success = "Sensitive info saved."
            # Reload to refresh display
            self._load_sensitive_info(self.tenant_id)

        except RuntimeError as ex:
            self.si_form_error = str(ex)
        except Exception as ex:
            self.si_form_error = f"Save failed: {ex}"

    # ── Tenant edit / create ──────────────────────────────────────────────────

    def start_edit_tenant(self):
        """Open the edit form pre-populated with current tenant values."""
        self.tenant_edit_mode = True
        self.tenant_is_new = False
        self.tenant_form_error = ""
        self.tenant_form_success = ""
        self.f_tenant_name     = self.selected_tenant_name
        self.f_tenant_status   = self.tenant_status
        self.f_tenant_type     = self.tenant_type
        self.f_tenant_property = self.tenant_property
        self.f_tenant_suite    = self.tenant_suite
        self.f_tenant_notes    = self.tenant_notes
        if self.f_tenant_property in self.property_names:
            self._load_suite_options(self.f_tenant_property)

    def start_new_tenant(self):
        """Open a blank create form."""
        self.tenant_id = 0
        self.tenant_edit_mode = True
        self.tenant_is_new = True
        self.tenant_form_error = ""
        self.tenant_form_success = ""
        self.f_tenant_name     = ""
        self.f_tenant_status   = self.status_names[0] if self.status_names else ""
        self.f_tenant_type     = self.type_names[0] if self.type_names else ""
        self.f_tenant_property = self.property_names[0] if self.property_names else ""
        self.f_tenant_suite    = "(No suite)"
        self.f_tenant_notes    = ""
        if self.property_names:
            self._load_suite_options(self.property_names[0])

    def cancel_tenant_edit(self):
        self.tenant_edit_mode = False
        self.tenant_form_error = ""
        self.tenant_form_success = ""

    def set_f_tenant_name(self, v: str):     self.f_tenant_name = v
    def set_f_tenant_status(self, v: str):   self.f_tenant_status = v
    def set_f_tenant_type(self, v: str):     self.f_tenant_type = v
    def set_f_tenant_notes(self, v: str):    self.f_tenant_notes = v

    def set_f_tenant_property(self, v: str):
        self.f_tenant_property = v
        self.f_tenant_suite = "(No suite)"
        self._load_suite_options(v)

    def set_f_tenant_suite(self, v: str):
        self.f_tenant_suite = v

    def save_tenant(self):
        self.tenant_form_error = ""
        self.tenant_form_success = ""
        if not self.f_tenant_name.strip():
            self.tenant_form_error = "Tenant name is required."
            return

        # Resolve IDs
        prop_id = None
        if self.f_tenant_property in self.property_names:
            prop_id = self.property_ids[self.property_names.index(self.f_tenant_property)]

        status_id = None
        if self.f_tenant_status in self.status_names:
            status_id = self.status_ids[self.status_names.index(self.f_tenant_status)]

        type_id = None
        if self.f_tenant_type in self.type_names:
            type_id = self.type_ids[self.type_names.index(self.f_tenant_type)]

        suite_id = None
        suite_label = ""
        if self.f_tenant_suite and self.f_tenant_suite != "(No suite)":
            suite_label = self.f_tenant_suite
            if self.f_tenant_suite in self.suite_names:
                idx = self.suite_names.index(self.f_tenant_suite)
                sid = self.suite_ids[idx]
                if sid != 0:
                    suite_id = sid

        if self.tenant_is_new:
            run_exec(
                "INSERT INTO Tenants (TenantName, TenantStatusID, TenantTypeID, "
                "PropertyID, Suite, SuiteID, Notes) VALUES (?,?,?,?,?,?,?)",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes),
                db=self.db,
            )
            # Find new tenant ID
            new_rows = run_query(
                "SELECT TOP 1 TenantID FROM Tenants WHERE TenantName=? ORDER BY TenantID DESC",
                (self.f_tenant_name.strip(),), db=self.db,
            )
            self.tenant_form_success = f"{self.f_tenant_name.strip()} created."
            self.tenant_edit_mode = False
            self.load_tenant_list()
            if new_rows:
                self._load_tenant_detail(int(new_rows[0]["TenantID"]))
        else:
            run_exec(
                "UPDATE Tenants SET TenantName=?, TenantStatusID=?, TenantTypeID=?, "
                "PropertyID=?, Suite=?, SuiteID=?, Notes=? WHERE TenantID=?",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes,
                 self.tenant_id),
                db=self.db,
            )
            self.tenant_form_success = f"{self.f_tenant_name.strip()} saved."
            self.tenant_edit_mode = False
            self.load_tenant_list()
            self._load_tenant_detail(self.tenant_id)

    def load_contacts(self):
        rows = run_query(
            "SELECT ContactID, FirstName, LastName, ContactRole, Title, "
            "WorkPhone, HomePhone, Email1, Email2, IsPrimary, Salutation "
            "FROM Contacts WHERE TenantID = ? "
            "ORDER BY IsPrimary DESC, LastName, FirstName",
            (self.tenant_id,), db=self.db,
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
            self.f_first      = c.first_name
            self.f_last       = c.last_name
            self.f_title      = c.title
            self.f_role       = c.role
            self.f_work_phone = c.phone
            self.f_home_phone = c.home_phone
            self.f_email1     = c.email
            self.f_email2     = c.email2
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
            (self.tenant_id,), db=self.db,
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
            (self.tenant_id,), db=self.db,
        )
        names = ["(No contact)"]
        ids   = [0]
        for r in rows:
            fn = str(r.get("FirstName") or "")
            ln = str(r.get("LastName") or "")
            names.append(f"{fn} {ln}".strip() or f"Contact #{r['ContactID']}")
            ids.append(r["ContactID"])
        self.comm_contact_names = names
        self.comm_contact_ids   = ids

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
        self.c_date              = raw_date.strftime("%Y-%m-%d") if raw_date else ""
        self.c_method            = str(r.get("Method") or "Call")
        self.c_subject           = str(r.get("Subject") or "")
        self.c_outcome           = str(r.get("Outcome") or "")
        self.c_next_action_date  = raw_next.strftime("%Y-%m-%d") if raw_next else ""
        self.c_notes             = str(r.get("Notes") or "")
        self.c_template_name     = str(r.get("TemplateName") or "")
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

    # ── Leases ────────────────────────────────────────────────────────────────

    def load_leases(self):
        rows = run_query(
            "SELECT l.LeaseID, ps.SuiteLabel, lt.LeaseTypeName, ltt.LeaseTermTypeName, "
            "l.LeaseStart, l.LeaseEnd, l.RentAmount "
            "FROM Leases l "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "LEFT JOIN LeaseTypes lt ON l.LeaseTypeID = lt.LeaseTypeID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            "WHERE l.TenantID = ? ORDER BY l.LeaseStart DESC",
            (self.tenant_id,), db=self.db,
        )
        def fmt_money(v) -> str:
            try:
                return f"${float(v):,.0f}/mo" if v is not None else ""
            except (TypeError, ValueError):
                return ""
        def fmt_dt(v) -> str:
            if v is None:
                return ""
            if hasattr(v, "strftime"):
                return v.strftime("%m/%d/%Y")
            return str(v)
        self.leases = [
            LeaseSummary(
                lease_id=int(r["LeaseID"]),
                suite_label=str(r.get("SuiteLabel") or ""),
                lease_type=str(r.get("LeaseTypeName") or ""),
                lease_term_type=str(r.get("LeaseTermTypeName") or ""),
                lease_start=fmt_dt(r.get("LeaseStart")),
                lease_end=fmt_dt(r.get("LeaseEnd")),
                rent_amount=fmt_money(r.get("RentAmount")),
            )
            for r in rows
        ]

    def select_lease(self, lease_id: int):
        self.selected_lease_id = lease_id
        self.lease_mode = "edit"
        self.lease_form_error = ""
        self.lease_form_success = ""
        self.confirm_delete_lease = False
        rows = run_query(
            "SELECT l.LeaseID, l.PropertyID, p.PropertyName, l.SuiteID, ps.SuiteLabel, "
            "l.LeaseTypeID, lt.LeaseTypeName, l.LeaseTermTypeID, ltt.LeaseTermTypeName, "
            "l.LeaseStart, l.LeaseEnd, l.RentAmount, l.DepositAmount, "
            "l.RentDueDay, l.NextDueDate, l.ShowAnniversaries "
            "FROM Leases l "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "LEFT JOIN LeaseTypes lt ON l.LeaseTypeID = lt.LeaseTypeID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            "WHERE l.LeaseID = ?",
            (lease_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        prop_name = str(r.get("PropertyName") or "")
        self.l_property      = prop_name
        self.l_suite         = str(r.get("SuiteLabel") or "(No suite)")
        self.l_lease_type    = str(r.get("LeaseTypeName") or (self.lease_type_names[0] if self.lease_type_names else ""))
        self.l_lease_term_type = str(r.get("LeaseTermTypeName") or (self.lease_term_type_names[0] if self.lease_term_type_names else ""))
        raw_start = r.get("LeaseStart")
        raw_end   = r.get("LeaseEnd")
        raw_next  = r.get("NextDueDate")
        self.l_start    = raw_start.strftime("%Y-%m-%d") if raw_start else ""
        self.l_end      = raw_end.strftime("%Y-%m-%d") if raw_end else ""
        self.l_next_due = raw_next.strftime("%Y-%m-%d") if raw_next else ""
        try:
            self.l_rent    = str(int(float(r.get("RentAmount") or 0)))
        except (TypeError, ValueError):
            self.l_rent = ""
        try:
            self.l_deposit = str(int(float(r.get("DepositAmount") or 0)))
        except (TypeError, ValueError):
            self.l_deposit = ""
        self.l_due_day           = str(int(r.get("RentDueDay") or 1))
        self.l_show_anniversaries = bool(r.get("ShowAnniversaries"))
        # Load suite options for this property
        self._load_suite_options(prop_name)
        # Load rent schedule for this lease
        self._load_rent_schedule(lease_id)
        self.new_rent_schedule_row()

    def new_lease(self):
        self.selected_lease_id = 0
        self.lease_mode = "new"
        self.lease_form_error = ""
        self.lease_form_success = ""
        self.confirm_delete_lease = False
        self.l_property      = self.property_names[0] if self.property_names else ""
        self.l_suite         = "(No suite)"
        self.l_lease_type    = self.lease_type_names[0] if self.lease_type_names else ""
        self.l_lease_term_type = self.lease_term_type_names[0] if self.lease_term_type_names else ""
        self.l_start = self.l_end = self.l_next_due = ""
        self.l_rent = self.l_deposit = ""
        self.l_due_day = "1"
        self.l_show_anniversaries = False
        self.rent_schedule = []
        self.new_rent_schedule_row()
        if self.property_names:
            self._load_suite_options(self.property_names[0])

    def set_l_property(self, v: str):
        self.l_property = v
        self.l_suite = "(No suite)"
        self._load_suite_options(v)

    def save_lease(self):
        self.lease_form_error = ""
        self.lease_form_success = ""
        # Resolve IDs
        if not self.l_property or self.l_property not in self.property_names:
            self.lease_form_error = "Property is required."
            return
        prop_id = self.property_ids[self.property_names.index(self.l_property)]
        suite_id = None
        if self.l_suite and self.l_suite != "(No suite)" and self.l_suite in self.suite_names:
            idx = self.suite_names.index(self.l_suite)
            suite_id = self.suite_ids[idx] or None
        if not self.l_lease_type or self.l_lease_type not in self.lease_type_names:
            self.lease_form_error = "Lease type is required."
            return
        lease_type_id = self.lease_type_ids[self.lease_type_names.index(self.l_lease_type)]
        lease_term_type_id = None
        if self.l_lease_term_type and self.l_lease_term_type in self.lease_term_type_names:
            lease_term_type_id = self.lease_term_type_ids[self.lease_term_type_names.index(self.l_lease_term_type)]
        # Parse dates
        try:
            lease_start = datetime.datetime.strptime(self.l_start, "%Y-%m-%d").date() if self.l_start else None
        except ValueError:
            lease_start = None
        try:
            lease_end = datetime.datetime.strptime(self.l_end, "%Y-%m-%d").date() if self.l_end else None
        except ValueError:
            lease_end = None
        try:
            next_due = datetime.datetime.strptime(self.l_next_due, "%Y-%m-%d").date() if self.l_next_due else None
        except ValueError:
            next_due = None
        try:
            rent = float(self.l_rent) if self.l_rent.strip() else 0.0
        except ValueError:
            rent = 0.0
        try:
            deposit = float(self.l_deposit) if self.l_deposit.strip() else 0.0
        except ValueError:
            deposit = 0.0
        try:
            due_day = int(self.l_due_day) if self.l_due_day.strip() else 1
            due_day = max(1, min(31, due_day))
        except ValueError:
            due_day = 1

        if self.lease_mode == "edit":
            run_exec(
                "UPDATE Leases SET PropertyID=?, SuiteID=?, LeaseTypeID=?, LeaseTermTypeID=?, "
                "LeaseStart=?, LeaseEnd=?, RentAmount=?, DepositAmount=?, RentDueDay=?, "
                "NextDueDate=?, ShowAnniversaries=? WHERE LeaseID=?",
                (prop_id, suite_id, lease_type_id, lease_term_type_id,
                 lease_start, lease_end, rent, deposit, due_day,
                 next_due, self.l_show_anniversaries, self.selected_lease_id),
                db=self.db,
            )
            # Keep base rent schedule row in sync
            run_exec(
                "UPDATE LeaseRentSchedule SET RentAmount=? "
                "WHERE LeaseID=? AND IncreaseTypeID = "
                "(SELECT TOP 1 LeaseRentIncreaseTypeID FROM LeaseRentIncreaseTypes WHERE IncreaseTypeName='Base')",
                (rent, self.selected_lease_id), db=self.db,
            )
            self.lease_form_success = "Lease saved."
            self._load_rent_schedule(self.selected_lease_id)
        else:
            # INSERT and get new ID
            run_exec(
                "INSERT INTO Leases (TenantID, PropertyID, SuiteID, LeaseTypeID, LeaseTermTypeID, "
                "LeaseStart, LeaseEnd, RentAmount, DepositAmount, RentDueDay, NextDueDate, ShowAnniversaries) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.tenant_id, prop_id, suite_id, lease_type_id, lease_term_type_id,
                 lease_start, lease_end, rent, deposit, due_day,
                 next_due, self.l_show_anniversaries),
                db=self.db,
            )
            # Get the new lease ID
            id_rows = run_query(
                "SELECT TOP 1 LeaseID FROM Leases WHERE TenantID=? ORDER BY LeaseID DESC",
                (self.tenant_id,), db=self.db,
            )
            if id_rows and lease_start:
                new_id = int(id_rows[0]["LeaseID"])
                # Auto-create base rent schedule row
                run_exec(
                    "INSERT INTO LeaseRentSchedule (LeaseID, EffectiveStartDate, EffectiveEndDate, "
                    "RentAmount, IncreaseTypeID, Notes) "
                    "VALUES (?, ?, NULL, ?, "
                    "(SELECT TOP 1 LeaseRentIncreaseTypeID FROM LeaseRentIncreaseTypes WHERE IncreaseTypeName='Base'), "
                    "'Initial rent on lease creation')",
                    (new_id, lease_start, rent), db=self.db,
                )
            self.lease_form_success = "Lease created."
            self.new_lease()
        self.load_leases()

    def confirm_delete_lease_action(self):
        self.confirm_delete_lease = True

    def cancel_delete_lease(self):
        self.confirm_delete_lease = False

    def delete_lease(self):
        if self.selected_lease_id == 0:
            return
        # Delete rent schedule rows first (FK constraint)
        run_exec("DELETE FROM LeaseRentSchedule WHERE LeaseID=?",
                 (self.selected_lease_id,), db=self.db)
        run_exec("DELETE FROM Leases WHERE LeaseID=?",
                 (self.selected_lease_id,), db=self.db)
        self.load_leases()
        self.new_lease()

    def _load_rent_schedule(self, lease_id: int):
        rows = run_query(
            "SELECT s.LeaseRentScheduleID, s.EffectiveStartDate, s.EffectiveEndDate, "
            "s.RentAmount, t.IncreaseTypeName, s.Notes "
            "FROM LeaseRentSchedule s "
            "LEFT JOIN LeaseRentIncreaseTypes t ON s.IncreaseTypeID = t.LeaseRentIncreaseTypeID "
            "WHERE s.LeaseID=? ORDER BY s.EffectiveStartDate",
            (lease_id,), db=self.db,
        )
        def fmt_dt(v) -> str:
            if v is None:
                return ""
            return v.strftime("%m/%d/%Y") if hasattr(v, "strftime") else str(v)
        def fmt_money(v) -> str:
            try:
                return f"${float(v):,.2f}" if v is not None else ""
            except (TypeError, ValueError):
                return ""
        self.rent_schedule = [
            RentScheduleRow(
                sched_id=int(r["LeaseRentScheduleID"]),
                effective_start=fmt_dt(r.get("EffectiveStartDate")),
                effective_end=fmt_dt(r.get("EffectiveEndDate")),
                rent_amount=fmt_money(r.get("RentAmount")),
                increase_type=str(r.get("IncreaseTypeName") or ""),
                notes=str(r.get("Notes") or ""),
            )
            for r in rows
        ]

    def new_rent_schedule_row(self):
        self.selected_sched_id = 0
        self.sched_mode = "new"
        self.confirm_delete_sched = False
        self.rent_schedule_form_error = ""
        self.rent_schedule_form_success = ""
        self.rs_start = self.l_start or ""
        self.rs_end = ""
        self.rs_rent = self.l_rent or ""
        # Prefer a real base-rent style type instead of blindly falling
        # back to the first lookup row, which can incorrectly become
        # "Abatement" depending on DisplayOrder.
        preferred_types = [
            "Base",
            "Base Rent",
            "Initial Rent",
            "Annual Increase",
        ]

        self.rs_increase_type = ""

        for t in preferred_types:
            if t in self.increase_type_names:
                self.rs_increase_type = t
                break

        if not self.rs_increase_type and self.increase_type_names:
            non_abatement = [
                x for x in self.increase_type_names
                if str(x).strip().lower() != "abatement"
            ]
            self.rs_increase_type = (
                non_abatement[0]
                if non_abatement
                else self.increase_type_names[0]
            )
        self.rs_notes = ""

    def select_rent_schedule_row(self, sched_id: int):
        self.selected_sched_id = sched_id
        self.sched_mode = "edit"
        self.confirm_delete_sched = False
        self.rent_schedule_form_error = ""
        self.rent_schedule_form_success = ""
        rows = run_query(
            "SELECT s.LeaseRentScheduleID, s.EffectiveStartDate, s.EffectiveEndDate, "
            "s.RentAmount, s.IncreaseTypeID, t.IncreaseTypeName, s.Notes "
            "FROM LeaseRentSchedule s "
            "LEFT JOIN LeaseRentIncreaseTypes t ON s.IncreaseTypeID = t.LeaseRentIncreaseTypeID "
            "WHERE s.LeaseRentScheduleID=?",
            (sched_id,), db=self.db,
        )
        if not rows:
            self.rent_schedule_form_error = "Rent schedule row not found."
            return
        r = rows[0]
        start = r.get("EffectiveStartDate")
        end = r.get("EffectiveEndDate")
        self.rs_start = start.strftime("%Y-%m-%d") if start and hasattr(start, "strftime") else str(start or "")
        self.rs_end = end.strftime("%Y-%m-%d") if end and hasattr(end, "strftime") else str(end or "")
        try:
            self.rs_rent = str(int(float(r.get("RentAmount") or 0)))
        except (TypeError, ValueError):
            self.rs_rent = ""
        self.rs_increase_type = str(r.get("IncreaseTypeName") or "")
        self.rs_notes = str(r.get("Notes") or "")

    def save_rent_schedule_row(self):
        self.rent_schedule_form_error = ""
        self.rent_schedule_form_success = ""
        if self.selected_lease_id <= 0:
            self.rent_schedule_form_error = "Select a lease before saving rent schedule rows."
            return
        try:
            start = datetime.datetime.strptime(self.rs_start, "%Y-%m-%d").date() if self.rs_start else None
        except ValueError:
            start = None
        try:
            end = datetime.datetime.strptime(self.rs_end, "%Y-%m-%d").date() if self.rs_end else None
        except ValueError:
            end = None
        if not start:
            self.rent_schedule_form_error = "Effective start date is required."
            return
        if end and end < start:
            self.rent_schedule_form_error = "Effective end date cannot be before start date."
            return
        try:
            rent = float(self.rs_rent) if self.rs_rent.strip() else 0.0
        except ValueError:
            self.rent_schedule_form_error = "Rent must be a valid number."
            return
        increase_type_id = None
        if self.rs_increase_type and self.rs_increase_type in self.increase_type_names:
            increase_type_id = self.increase_type_ids[self.increase_type_names.index(self.rs_increase_type)]
        if self.sched_mode == "edit" and self.selected_sched_id > 0:
            run_exec(
                "UPDATE LeaseRentSchedule SET EffectiveStartDate=?, EffectiveEndDate=?, "
                "RentAmount=?, IncreaseTypeID=?, Notes=? WHERE LeaseRentScheduleID=?",
                (start, end, rent, increase_type_id, self.rs_notes.strip(), self.selected_sched_id),
                db=self.db,
            )
            self.rent_schedule_form_success = "Rent schedule row saved."
        else:
            run_exec(
                "INSERT INTO LeaseRentSchedule "
                "(LeaseID, EffectiveStartDate, EffectiveEndDate, RentAmount, IncreaseTypeID, Notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_lease_id, start, end, rent, increase_type_id, self.rs_notes.strip()),
                db=self.db,
            )
            self.rent_schedule_form_success = "Rent schedule row created."
        self._load_rent_schedule(self.selected_lease_id)
        self.load_leases()
        self.new_rent_schedule_row()

    def confirm_delete_rent_schedule_row(self):
        self.confirm_delete_sched = True

    def cancel_delete_rent_schedule_row(self):
        self.confirm_delete_sched = False

    def delete_rent_schedule_row(self):
        if self.selected_sched_id <= 0:
            return
        run_exec(
            "DELETE FROM LeaseRentSchedule WHERE LeaseRentScheduleID=?",
            (self.selected_sched_id,), db=self.db,
        )
        self.rent_schedule_form_success = "Rent schedule row deleted."
        self._load_rent_schedule(self.selected_lease_id)
        self.load_leases()
        self.new_rent_schedule_row()

    def set_rs_start(self, v): self.rs_start = v
    def set_rs_end(self, v): self.rs_end = v
    def set_rs_rent(self, v): self.rs_rent = v
    def set_rs_increase_type(self, v): self.rs_increase_type = v
    def set_rs_notes(self, v): self.rs_notes = v

    # Lease setters
    def set_l_suite(self, v): self.l_suite = v
    def set_l_lease_type(self, v): self.l_lease_type = v
    def set_l_lease_term_type(self, v): self.l_lease_term_type = v
    def set_l_start(self, v): self.l_start = v
    def set_l_end(self, v): self.l_end = v
    def set_l_rent(self, v): self.l_rent = v
    def set_l_deposit(self, v): self.l_deposit = v
    def set_l_due_day(self, v): self.l_due_day = v
    def set_l_next_due(self, v): self.l_next_due = v
    def set_l_show_anniversaries(self, v): self.l_show_anniversaries = v


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


def _build_application_report_pdf(
    output_path: str,
    tenant_name: str,
    contact: dict,
    si: dict,
    fields: dict,
) -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=0.85*inch, rightMargin=0.85*inch,
        topMargin=0.5*inch, bottomMargin=0.85*inch,
    )
    hdr   = ParagraphStyle("AppHdr",  fontName="Times-Bold",   fontSize=10, leading=13, alignment=TA_RIGHT)
    title = ParagraphStyle("AppTtl",  fontName="Times-Bold",   fontSize=12, leading=15, alignment=TA_CENTER, spaceAfter=12)
    body  = ParagraphStyle("AppBody", fontName="Times-Roman",  fontSize=10, leading=14)
    lbl   = ParagraphStyle("AppLbl",  fontName="Times-Bold",   fontSize=10, leading=14)

    def clean(value):
        return str(value or "").strip().replace("\n", "<br/>")

    def fld(label, value):
        val = clean(value)
        return f"<b>{label}:</b>  {val if val else '________________'}"

    def row2(l1, v1, l2, v2):
        a = clean(v1) or "________________"
        b = clean(v2) or "________________"
        return f"<b>{l1}:</b>  {a}&nbsp;&nbsp;&nbsp;&nbsp;<b>{l2}:</b>  {b}"

    def ref_line(i: int) -> str:
        name = fields.get(f"reference_{i}_name", "") or fields.get(f"trade_ref_{i}", "")
        years = fields.get(f"reference_{i}_years", "")
        phone = fields.get(f"reference_{i}_phone", "")
        parts = []
        if name:
            parts.append(f"<b>Name:</b> {clean(name)}")
        if years:
            parts.append(f"<b>Years doing business:</b> {clean(years)}")
        if phone:
            parts.append(f"<b>Phone:</b> {clean(phone)}")
        return "&nbsp;&nbsp;&nbsp;&nbsp;".join(parts) if parts else "________________"

    s = []
    s.append(Paragraph(
        "Dor-Sal Capital Partners, LLC<br/>P.O. Box 117390<br/>"
        "Carrollton, TX 75011-7390<br/>Ph. 214-991-1988<br/>"
        "Email: LucidoProperties@verizon.net", hdr))
    s.append(Spacer(1,12))
    s.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    s.append(Spacer(1,10))
    s.append(Paragraph("Tenant Information Sheet", title))

    contact_name = (
        f"{contact.get('FirstName','')} {contact.get('LastName','')}".strip()
        or fields.get("individual_name","")
    )
    ssn_d = (_mask_ssn(str(si.get("Last4SSN") or ""))) or "________________"
    dl_d  = (_mask_dl(str(si.get("DL_Last4")  or ""))) or "________________"
    dob_d = str(si.get("DOB") or "") or "________________"

    s.append(Paragraph(fld("Date", fields.get("application_date", "")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Individual Name", contact_name), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("Email", contact.get("Email1",""), "Phone", contact.get("WorkPhone","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("Soc. Sec. No.", ssn_d, "D.L. No/State", dl_d), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Date of Birth", dob_d), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Address", fields.get("address","")), body)); s.append(Spacer(1,10))

    s.append(Paragraph("<b>Emergency Contact:</b>", lbl)); s.append(Spacer(1,4))
    s.append(Paragraph(fld("Name", fields.get("emergency_name","")), body)); s.append(Spacer(1,4))
    s.append(Paragraph(row2("Phone", fields.get("emergency_phone",""), "Email", fields.get("emergency_email","")), body)); s.append(Spacer(1,10))

    s.append(Paragraph(fld("Business Name", fields.get("business_name","") or tenant_name), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Present Address", fields.get("present_address","") or fields.get("address","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("City", fields.get("city",""), "State / Zip", " ".join(x for x in [fields.get("state",""), fields.get("zip","")] if x)), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("Name of Owner", fields.get("owner_name",""), "Nature of the Business", fields.get("nature_of_business","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("Owner 1 Address", fields.get("owner_1_address",""), "Owner 1 Phone", fields.get("owner_1_phone","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("When Established", fields.get("when_established",""), "Who to contact regarding payment", fields.get("payment_contact","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(row2("Payment Contact Phone", fields.get("payment_contact_phone",""), "Payment Contact Email", fields.get("payment_contact_email","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Form of Business", fields.get("form_of_business","")), body)); s.append(Spacer(1,16))

    s.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey)); s.append(Spacer(1,8))
    s.append(Paragraph(row2("Annual Sales", fields.get("annual_sales",""), "Rated in Dun & Bradstreet?", fields.get("dun_bradstreet","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Name of your bank", fields.get("bank_name","")), body)); s.append(Spacer(1,5))
    s.append(Paragraph(fld("Have you ever filed for bankruptcy?", fields.get("bankruptcy","")), body)); s.append(Spacer(1,14))
    s.append(Paragraph("<b>Trade References:</b>", lbl)); s.append(Spacer(1,6))
    for i in [1, 2, 3]:
        s.append(Paragraph(f"<b>{i})</b>  {ref_line(i)}", body))
        s.append(Spacer(1,10))

    s.append(Spacer(1,16))
    s.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey)); s.append(Spacer(1,8))
    s.append(Paragraph("<b>Personal References:</b>", lbl)); s.append(Spacer(1,6))
    for i, k in enumerate(["personal_ref_1","personal_ref_2","personal_ref_3"], 1):
        s.append(Paragraph(f"<b>{i})</b>  {fields.get(k,'') or '________________'}", body))
        s.append(Spacer(1,10))

    s.append(Spacer(1,6))
    s.append(Paragraph(fld("Additional Remarks and Information", fields.get("additional_remarks","")), body))
    s.append(Spacer(1,20))
    s.append(Paragraph(
        "<b>Authorization:</b>  Applicant authorizes Landlord and Landlord's agent, at any time "
        "before, during, or after any tenancy, to: (1) Obtain a copy of Applicant's credit report; "
        "(2) Obtain a criminal background check; and (3) Verify any rental or employment history.", body))
    s.append(Spacer(1,12))
    s.append(Paragraph(
        "<b>Notice of Landlord's Right to Continue to Show the Property:</b>  The Property remains "
        "on the market until a lease is signed by all parties.", body))
    s.append(Spacer(1,20))
    for sig in ["By:", "By (signature):", "Printed Name:", "Title:"]:
        s.append(Paragraph(f"<b>{sig}</b>  ________________________________", body))
        s.append(Spacer(1,12))

    doc.build(s)
    return output_path


# ── Tenant list panel ─────────────────────────────────────────────────────────

def tenant_list_row(t: TenantSummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(t.tenant_name, size="2", weight="bold"),
                rx.cond(
                    t.status == "Applicant",
                    rx.badge("Applicant", color_scheme="yellow", variant="soft", size="1"),
                    rx.fragment(),
                ),
                spacing="2", align="center",
            )
        ),
        rx.table.cell(rx.text(t.suite, size="2", color="#555")),
        rx.table.cell(
            rx.button("View", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_tenant_from_list(t.tenant_id))
        ),
        style=rx.cond(
            TenantState.tenant_id == t.tenant_id,
            {"background": "#f0f4ff"},
            rx.cond(
                t.status == "Applicant",
                {"background": "#FFF8E1", "border_left": "3px solid #F9A825"},
                {"background": "white"},
            ),
        ),
    )


def tenant_list_panel() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.hstack(
                rx.heading("Tenants", size="5", color=BRAND_DARK),
                rx.spacer(),
                rx.button(
                    "+ New",
                    on_click=TenantState.start_new_tenant,
                    size="2", color_scheme="blue", variant="soft",
                ),
                align="center", width="100%",
            ),
            rx.spacer(),
            rx.select(
                ["Active + Default", "Active + Applicant", "Active", "Applicant", "Inactive", "All"],
                value=TenantState.status_filter,
                on_change=TenantState.set_status_filter,
                size="1",
            ),
            align="center", width="100%",
        ),
        rx.hstack(
            rx.text("Property:", size="1", color="#666", white_space="nowrap"),
            rx.spacer(),
            rx.select(
                TenantState.property_filter_options,
                value=TenantState.property_filter,
                on_change=TenantState.set_property_filter,
                size="1", width="200px",
            ),
            align="center", spacing="2", width="100%",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(
                        rx.hstack(
                            rx.text("Name"),
                            rx.cond(TenantState.sort_by == "Name", rx.text("↑", size="1"), rx.text("", size="1")),
                            spacing="1", align="center",
                            on_click=TenantState.set_sort_by("Name"),
                            style={"cursor": "pointer"},
                        )
                    ),
                    rx.table.column_header_cell(
                        rx.hstack(
                            rx.text("Suite"),
                            rx.cond(TenantState.sort_by == "Suite", rx.text("↑", size="1"), rx.text("", size="1")),
                            spacing="1", align="center",
                            on_click=TenantState.set_sort_by("Suite"),
                            style={"cursor": "pointer"},
                        )
                    ),
                    rx.table.column_header_cell(""),
                )
            ),
            rx.table.body(rx.foreach(TenantState.tenant_list, tenant_list_row)),
            width="100%", variant="surface",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Tenant header card ────────────────────────────────────────────────────────

def _form_field(label: str, component: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color="#666"),
        component,
        spacing="1", width="100%",
    )


def tenant_edit_form() -> rx.Component:
    """Inline edit/create form shown when tenant_edit_mode is True."""
    return rx.box(
        rx.vstack(
            rx.text(
                rx.cond(TenantState.tenant_is_new, "New tenant", "Edit tenant"),
                size="3", weight="bold", color=BRAND_DARK,
            ),
            rx.grid(
                _form_field("Tenant name *",
                    rx.input(value=TenantState.f_tenant_name,
                             on_change=TenantState.set_f_tenant_name,
                             placeholder="Business or individual name",
                             size="2", width="100%"),
                ),
                _form_field("Status",
                    rx.cond(
                        TenantState.status_names.length() > 0,
                        rx.select(TenantState.status_names,
                                  value=TenantState.f_tenant_status,
                                  on_change=TenantState.set_f_tenant_status,
                                  size="2"),
                        rx.text("Loading...", size="2"),
                    ),
                ),
                _form_field("Type",
                    rx.cond(
                        TenantState.type_names.length() > 0,
                        rx.select(TenantState.type_names,
                                  value=TenantState.f_tenant_type,
                                  on_change=TenantState.set_f_tenant_type,
                                  size="2"),
                        rx.text("Loading...", size="2"),
                    ),
                ),
                columns="3", spacing="3", width="100%",
            ),
            rx.grid(
                _form_field("Property",
                    rx.cond(
                        TenantState.property_names.length() > 0,
                        rx.select(TenantState.property_names,
                                  value=TenantState.f_tenant_property,
                                  on_change=TenantState.set_f_tenant_property,
                                  size="2"),
                        rx.text("Loading...", size="2"),
                    ),
                ),
                _form_field("Suite",
                    rx.cond(
                        TenantState.suite_names.length() > 0,
                        rx.select(TenantState.suite_names,
                                  value=TenantState.f_tenant_suite,
                                  on_change=TenantState.set_f_tenant_suite,
                                  size="2"),
                        rx.text("No suites", size="2"),
                    ),
                ),
                columns="2", spacing="3", width="100%",
            ),
            _form_field("Notes",
                rx.text_area(value=TenantState.f_tenant_notes,
                             on_change=TenantState.set_f_tenant_notes,
                             placeholder="Notes...",
                             width="100%", rows="3"),
            ),
            rx.cond(
                TenantState.tenant_form_error != "",
                rx.callout(TenantState.tenant_form_error, color="red", variant="soft"),
                rx.fragment(),
            ),
            rx.hstack(
                rx.button("Save", on_click=TenantState.save_tenant,
                          color_scheme="blue", size="2"),
                rx.button("Cancel", on_click=TenantState.cancel_tenant_edit,
                          variant="outline", color_scheme="gray", size="2"),
                spacing="3",
            ),
            spacing="3", width="100%", align_items="start",
        ),
        style={
            "background": "white", "border": "1px solid #dde3f0",
            "border_left": f"5px solid {BRAND_PRIMARY}", "border_radius": "12px",
            "padding": "16px 20px", "margin_bottom": "8px",
        },
    )


def tenant_header_card() -> rx.Component:
    return rx.cond(
        TenantState.tenant_edit_mode,
        tenant_edit_form(),
        rx.box(
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
                            rx.cond(
                                TenantState.tenant_status == "Applicant",
                                pill(TenantState.tenant_status, "#FFF8E1", "#E65100"),
                                pill(TenantState.tenant_status, "#eeeeee", "#555555"),
                            ),
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
                rx.spacer(),
                rx.cond(
                    TenantState.is_applicant,
                    rx.link(
                        rx.button(
                            "Application",
                            size="1", variant="soft", color_scheme="orange",
                        ),
                        href=TenantState.application_report_url,
                        is_external=True,
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    TenantState.tenant_id > 0,
                    rx.button(
                        "✏ Edit",
                        on_click=TenantState.start_edit_tenant,
                        size="1", variant="outline", color_scheme="blue",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    TenantState.tenant_form_success != "",
                    rx.badge(TenantState.tenant_form_success,
                             color_scheme="green", variant="soft"),
                    rx.fragment(),
                ),
                align="center", spacing="4", width="100%",
            ),
            style={
                "background": "white", "border": "1px solid #dde3f0",
                "border_left": f"5px solid {BRAND_PRIMARY}", "border_radius": "12px",
                "padding": "16px 20px", "margin_bottom": "8px",
                "box_shadow": "0 1px 4px rgba(74,99,168,0.07)",
            },
        ),
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


# ── Leases tab ────────────────────────────────────────────────────────────────

def lease_row(l: LeaseSummary) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(l.suite_label, size="2", weight="bold")),
        rx.table.cell(rx.text(l.lease_type, size="2", color="#555")),
        rx.table.cell(rx.text(l.lease_term_type, size="2", color="#555")),
        rx.table.cell(rx.text(l.lease_start, size="2", color="#555")),
        rx.table.cell(rx.text(l.lease_end, size="2", color="#555")),
        rx.table.cell(rx.text(l.rent_amount, size="2", weight="bold", color=BRAND_DARK)),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_lease(l.lease_id))
        ),
        style=rx.cond(
            TenantState.selected_lease_id == l.lease_id,
            {"background": "#f0f4ff"}, {"background": "white"},
        ),
    )


def rent_schedule_row(r: RentScheduleRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(r.effective_start, size="2")),
        rx.table.cell(rx.text(r.effective_end, size="2", color="#555")),
        rx.table.cell(rx.text(r.rent_amount, size="2", weight="bold")),
        rx.table.cell(rx.text(r.increase_type, size="2", color="#555")),
        rx.table.cell(rx.text(r.notes, size="2", color="#555")),
        rx.table.cell(
            rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                      on_click=TenantState.select_rent_schedule_row(r.sched_id))
        ),
        style=rx.cond(
            TenantState.selected_sched_id == r.sched_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )


def leases_tab() -> rx.Component:
    return rx.vstack(
        # ── Lease list ──
        rx.cond(
            TenantState.leases.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Suite"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("Term"),
                        rx.table.column_header_cell("Start"),
                        rx.table.column_header_cell("End"),
                        rx.table.column_header_cell("Rent"),
                        rx.table.column_header_cell(""),
                    )
                ),
                rx.table.body(rx.foreach(TenantState.leases, lease_row)),
                width="100%", variant="surface",
            ),
            rx.text("No leases yet.", color="#888", size="2"),
        ),
        rx.button("+ New lease", on_click=TenantState.new_lease,
                  variant="outline", color_scheme="blue", size="2"),

        rx.divider(),

        # ── Lease form ──
        rx.cond(
            TenantState.lease_mode == "edit",
            edit_banner(TenantState.lease_editing_banner),
            rx.text("New lease", size="3", weight="bold", color=BRAND_DARK),
        ),

        # Row 1: property, suite, lease type, term type
        rx.grid(
            rx.vstack(
                rx.text("Property *", size="1", color="#666"),
                rx.cond(
                    TenantState.property_names.length() > 0,
                    rx.select(TenantState.property_names, value=TenantState.l_property,
                              on_change=TenantState.set_l_property, size="2", width="100%"),
                    rx.text("Loading...", size="2", color="#888"),
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Suite", size="1", color="#666"),
                rx.cond(
                    TenantState.suite_names.length() > 0,
                    rx.select(TenantState.suite_names, value=TenantState.l_suite,
                              on_change=TenantState.set_l_suite, size="2", width="100%"),
                    rx.text("Select property first", size="2", color="#888"),
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Lease type *", size="1", color="#666"),
                rx.cond(
                    TenantState.lease_type_names.length() > 0,
                    rx.select(TenantState.lease_type_names, value=TenantState.l_lease_type,
                              on_change=TenantState.set_l_lease_type, size="2", width="100%"),
                    rx.text("Loading...", size="2", color="#888"),
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Term type", size="1", color="#666"),
                rx.cond(
                    TenantState.lease_term_type_names.length() > 0,
                    rx.select(TenantState.lease_term_type_names, value=TenantState.l_lease_term_type,
                              on_change=TenantState.set_l_lease_term_type, size="2", width="100%"),
                    rx.text("Loading...", size="2", color="#888"),
                ),
                spacing="1", width="100%",
            ),
            columns="4", spacing="4", width="100%",
        ),

        # Row 2: start, end, rent, deposit
        rx.grid(
            rx.vstack(
                rx.text("Lease start", size="1", color="#666"),
                rx.input(value=TenantState.l_start, on_change=TenantState.set_l_start,
                         type="date", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Lease end", size="1", color="#666"),
                rx.input(value=TenantState.l_end, on_change=TenantState.set_l_end,
                         type="date", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Monthly rent ($)", size="1", color="#666"),
                rx.input(value=TenantState.l_rent, on_change=TenantState.set_l_rent,
                         placeholder="0", type="number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Deposit ($)", size="1", color="#666"),
                rx.input(value=TenantState.l_deposit, on_change=TenantState.set_l_deposit,
                         placeholder="0", type="number", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            columns="4", spacing="4", width="100%",
        ),

        # Row 3: due day, next due date, show anniversaries
        rx.grid(
            rx.vstack(
                rx.text("Rent due day", size="1", color="#666"),
                rx.input(value=TenantState.l_due_day, on_change=TenantState.set_l_due_day,
                         placeholder="1", type="number", size="2", width="100%"),
                rx.cond(
                    TenantState.rent_due_day_warning != "",
                    rx.callout(TenantState.rent_due_day_warning, color_scheme="orange", variant="soft", size="1"),
                    rx.fragment(),
                ),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text("Next due date", size="1", color="#666"),
                rx.input(value=TenantState.l_next_due, on_change=TenantState.set_l_next_due,
                         type="date", size="2", width="100%"),
                spacing="1", width="100%",
            ),
            rx.vstack(
                rx.text(" ", size="1", color="#666"),  # spacer label
                rx.hstack(
                    rx.switch(checked=TenantState.l_show_anniversaries,
                              on_change=TenantState.set_l_show_anniversaries),
                    rx.text("Show anniversaries", size="2"),
                    align="center", spacing="2",
                ),
                spacing="1", width="100%",
            ),
            columns="3", spacing="4", width="100%",
        ),

        # Feedback
        rx.cond(TenantState.lease_form_error != "",
                rx.callout(TenantState.lease_form_error, color="red", variant="soft"),
                rx.fragment()),
        rx.cond(TenantState.lease_form_success != "",
                rx.callout(TenantState.lease_form_success, color="green", variant="soft"),
                rx.fragment()),

        # Buttons
        rx.hstack(
            rx.button(
                rx.cond(TenantState.lease_mode == "edit", "Save lease", "Create lease"),
                on_click=TenantState.save_lease, color_scheme="blue", size="2",
            ),
            rx.cond(
                TenantState.lease_mode == "edit",
                rx.hstack(
                    rx.cond(
                        TenantState.confirm_delete_lease,
                        # Confirmation state
                        rx.hstack(
                            rx.text("Delete this lease and its rent schedule?",
                                    size="2", color="#c62828"),
                            rx.button("Yes, delete", on_click=TenantState.delete_lease,
                                      color_scheme="red", size="2"),
                            rx.button("Cancel", on_click=TenantState.cancel_delete_lease,
                                      variant="ghost", size="2"),
                            spacing="2", align="center",
                        ),
                        # Normal state — show delete button
                        rx.button("Delete lease",
                                  on_click=TenantState.confirm_delete_lease_action,
                                  color_scheme="red", variant="outline", size="2"),
                    ),
                    spacing="2",
                ),
                rx.fragment(),
            ),
            rx.button("Cancel", on_click=TenantState.new_lease, variant="ghost", size="2"),
            rx.link(
                rx.button("Build lease package", variant="soft", color_scheme="blue", size="2"),
                href="/lease-package-builder",
            ),
            spacing="3", align="center",
        ),

        # ── Rent schedule ──
        rx.cond(
            TenantState.lease_mode == "edit",
            rx.vstack(
                rx.divider(),
                rx.hstack(
                    rx.text("Rent schedule", size="3", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.button("+ New schedule row", on_click=TenantState.new_rent_schedule_row,
                              variant="outline", color_scheme="blue", size="2"),
                    align="center", width="100%",
                ),
                rx.cond(
                    TenantState.rent_schedule.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Effective start"),
                                rx.table.column_header_cell("Effective end"),
                                rx.table.column_header_cell("Rent"),
                                rx.table.column_header_cell("Type"),
                                rx.table.column_header_cell("Notes"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(TenantState.rent_schedule, rent_schedule_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No rent schedule rows.", color="#888", size="2"),
                ),
                rx.cond(
                    TenantState.sched_mode == "edit",
                    edit_banner(TenantState.rent_schedule_editing_banner),
                    rx.text("New rent schedule row", size="3", weight="bold", color=BRAND_DARK),
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("Effective start *", size="1", color="#666"),
                        rx.input(value=TenantState.rs_start, on_change=TenantState.set_rs_start,
                                 type="date", size="2", width="100%"),
                        spacing="1", width="100%",
                    ),
                    rx.vstack(
                        rx.text("Effective end", size="1", color="#666"),
                        rx.input(value=TenantState.rs_end, on_change=TenantState.set_rs_end,
                                 type="date", size="2", width="100%"),
                        spacing="1", width="100%",
                    ),
                    rx.vstack(
                        rx.text("Rent ($)", size="1", color="#666"),
                        rx.input(value=TenantState.rs_rent, on_change=TenantState.set_rs_rent,
                                 placeholder="0", type="number", size="2", width="100%"),
                        spacing="1", width="100%",
                    ),
                    rx.vstack(
                        rx.text("Increase type", size="1", color="#666"),
                        rx.cond(
                            TenantState.increase_type_names.length() > 0,
                            rx.select(TenantState.increase_type_names,
                                      value=TenantState.rs_increase_type,
                                      on_change=TenantState.set_rs_increase_type,
                                      size="2", width="100%"),
                            rx.text("Loading...", size="2", color="#888"),
                        ),
                        spacing="1", width="100%",
                    ),
                    columns="4", spacing="4", width="100%",
                ),
                rx.vstack(
                    rx.text("Notes", size="1", color="#666"),
                    rx.text_area(value=TenantState.rs_notes, on_change=TenantState.set_rs_notes,
                                 placeholder="Optional schedule notes...", width="100%", rows="2"),
                    spacing="1", width="100%",
                ),
                rx.cond(TenantState.rent_schedule_form_error != "",
                        rx.callout(TenantState.rent_schedule_form_error, color="red", variant="soft"),
                        rx.fragment()),
                rx.cond(TenantState.rent_schedule_form_success != "",
                        rx.callout(TenantState.rent_schedule_form_success, color="green", variant="soft"),
                        rx.fragment()),
                rx.hstack(
                    rx.button(
                        rx.cond(TenantState.sched_mode == "edit", "Save schedule row", "Create schedule row"),
                        on_click=TenantState.save_rent_schedule_row,
                        color_scheme="blue", size="2",
                    ),
                    rx.cond(
                        TenantState.sched_mode == "edit",
                        rx.hstack(
                            rx.cond(
                                TenantState.confirm_delete_sched,
                                rx.hstack(
                                    rx.text("Delete this rent schedule row?", size="2", color="#c62828"),
                                    rx.button("Yes, delete", on_click=TenantState.delete_rent_schedule_row,
                                              color_scheme="red", size="2"),
                                    rx.button("Cancel", on_click=TenantState.cancel_delete_rent_schedule_row,
                                              variant="ghost", size="2"),
                                    spacing="2", align="center",
                                ),
                                rx.button("Delete schedule row",
                                          on_click=TenantState.confirm_delete_rent_schedule_row,
                                          color_scheme="red", variant="outline", size="2"),
                            ),
                            spacing="2",
                        ),
                        rx.fragment(),
                    ),
                    rx.button("Cancel", on_click=TenantState.new_rent_schedule_row,
                              variant="ghost", size="2"),
                    spacing="3", align="center",
                ),
                spacing="3", width="100%", align_items="start",
            ),
            rx.fragment(),
        ),

        spacing="4", width="100%", align_items="start",
    )


# ── Screening tab ─────────────────────────────────────────────────────────────

def screening_row(r: ScreeningRecord) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(r.ordered_date, size="2")),
        rx.table.cell(rx.text(r.completed_date, size="2", color="#555")),
        rx.table.cell(rx.text(r.report_file_number, size="2", color="#555")),
        rx.table.cell(rx.badge(r.overall_result, color_scheme=rx.cond(r.overall_result == "Fail", "red", rx.cond(r.overall_result == "Conditional", "orange", "green")), variant="soft")),
        rx.table.cell(rx.text(r.credit_score, size="2")),
        rx.table.cell(rx.text(r.evictions, size="2")),
        rx.table.cell(rx.text(r.bankruptcies, size="2")),
        rx.table.cell(rx.text(r.criminal_result, size="2")),
        rx.table.cell(rx.text(r.eviction_result, size="2")),
        rx.table.cell(rx.text(r.credit_source_type, size="2")),
        rx.table.cell(rx.text(r.risk_tier, size="2")),
        rx.table.cell(rx.text(r.deposit_recommended, size="2")),
        rx.table.cell(
            rx.button(
                "Edit",
                size="1",
                variant="soft",
                color_scheme="blue",
                on_click=TenantState.select_screening_record(r.screening_id),
            )
        ),
        style=rx.cond(
            TenantState.selected_screening_id == r.screening_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )

def screening_hard_flag_line(flag: str) -> rx.Component:
    return rx.callout(
        flag,
        color_scheme="amber",
        variant="soft",
        size="1",
        width="100%",
    )


def screening_assessment_panel() -> rx.Component:
    return rx.cond(
        TenantState.s_assessment_run,
        rx.box(
            rx.vstack(
                rx.text("Assessment result", size="2", weight="bold", color=BRAND_DARK),
                rx.grid(
                    rx.text("Score: " + TenantState.s_calculated_score.to_string() + " / 100", size="2"),
                    rx.text("Tier: " + TenantState.s_suggested_tier, size="2"),
                    rx.text("Decision: " + TenantState.s_suggested_decision, size="2"),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.cond(
                    TenantState.s_hard_flags.length() > 0,
                    rx.vstack(
                        rx.foreach(TenantState.s_hard_flags, screening_hard_flag_line),
                        spacing="2",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                align_items="start",
                spacing="2",
                width="100%",
            ),
            border="1px solid #E0E0E0",
            border_radius="10px",
            padding="12px",
            background="#FAFAFA",
            width="100%",
        ),
        rx.fragment(),
    )


def screening_form() -> rx.Component:
    return rx.vstack(
        rx.text(rx.cond(TenantState.screening_mode == "edit", "Edit screening record", "Add screening record"), size="3", weight="bold", color=BRAND_DARK),
        rx.grid(
            _form_field("Ordered Date *", rx.input(value=TenantState.s_ordered_date, on_change=TenantState.set_s_ordered_date, type="date", size="2", width="100%")),
            _form_field("Completed Date", rx.input(value=TenantState.s_completed_date, on_change=TenantState.set_s_completed_date, type="date", size="2", width="100%")),
            _form_field("Report File #", rx.input(value=TenantState.s_report_file_number, on_change=TenantState.set_s_report_file_number, size="2", width="100%")),
            columns="3", spacing="4", width="100%",
        ),
        rx.grid(
            _form_field("Overall Result", rx.select(["Pass", "Fail", "Conditional"], value=TenantState.s_overall_result, on_change=TenantState.set_s_overall_result, placeholder="Select result", size="2", width="100%")),
            _form_field("Credit Score", rx.input(value=TenantState.s_credit_score, on_change=TenantState.set_s_credit_score, type="number", size="2", width="100%")),
            _form_field("Risk Tier", rx.select(["Low", "Moderate", "Elevated", "High"], value=TenantState.s_risk_tier, on_change=TenantState.set_s_risk_tier, placeholder="Select risk tier", size="2", width="100%")),
            columns="3", spacing="4", width="100%",
        ),
        rx.grid(
            _form_field("Evictions", rx.input(value=TenantState.s_evictions, on_change=TenantState.set_s_evictions, type="number", size="2", width="100%")),
            _form_field("Bankruptcies", rx.input(value=TenantState.s_bankruptcies, on_change=TenantState.set_s_bankruptcies, type="number", size="2", width="100%")),
            _form_field("Collections", rx.input(value=TenantState.s_collections, on_change=TenantState.set_s_collections, type="number", size="2", width="100%")),
            _form_field("Charge-offs", rx.input(value=TenantState.s_charge_offs, on_change=TenantState.set_s_charge_offs, type="number", size="2", width="100%")),
            columns="4", spacing="4", width="100%",
        ),
        rx.grid(
            _form_field("Delinquent Accounts", rx.input(value=TenantState.s_delinquent_accounts, on_change=TenantState.set_s_delinquent_accounts, type="number", size="2", width="100%")),
            _form_field("Income:Rent Ratio", rx.input(value=TenantState.s_income_to_rent, on_change=TenantState.set_s_income_to_rent, placeholder="733.33:1", type="text", size="2", width="100%")),
            _form_field("Income:Debt Ratio", rx.input(value=TenantState.s_income_to_debt, on_change=TenantState.set_s_income_to_debt, placeholder="876.35:1", type="text", size="2", width="100%")),
            _form_field("Income:Debt Incl. Rent", rx.input(value=TenantState.s_income_to_debt_incl_rent, on_change=TenantState.set_s_income_to_debt_incl_rent, placeholder="399.24:1", type="text", size="2", width="100%")),
            columns="4", spacing="4", width="100%",
        ),
        rx.grid(
            _form_field("Criminal Search", rx.select(["Clear", "Records Found"], value=TenantState.s_criminal_result, on_change=TenantState.set_s_criminal_result, placeholder="Select result", size="2", width="100%")),
            _form_field("Eviction Search", rx.select(["Clear", "Records Found"], value=TenantState.s_eviction_result, on_change=TenantState.set_s_eviction_result, placeholder="Select result", size="2", width="100%")),
            _form_field("Credit Source", rx.select(["TenantReportX", "Self-Pulled", "Mortgage Tri-Merge", "Other"], value=TenantState.s_credit_source_type, on_change=TenantState.set_s_credit_source_type, size="2", width="100%")),
            _form_field("Deposit Recommended", rx.input(value=TenantState.s_deposit_recommended, on_change=TenantState.set_s_deposit_recommended, type="number", size="2", width="100%")),
            columns="4", spacing="4", width="100%",
        ),
        rx.cond(
            TenantState.s_credit_source_type != "TenantReportX",
            _form_field("Credit Source Notes", rx.text_area(value=TenantState.s_credit_source_notes, on_change=TenantState.set_s_credit_source_notes, width="100%", rows="2")),
            rx.fragment(),
        ),
        _form_field("Notes", rx.text_area(value=TenantState.s_notes, on_change=TenantState.set_s_notes, width="100%", rows="4")),
        rx.cond(TenantState.screening_form_error != "", rx.callout(TenantState.screening_form_error, color_scheme="red", variant="soft"), rx.fragment()),
        rx.button("Run Assessment", on_click=TenantState.run_screening_assessment, variant="soft", color_scheme="purple", size="2"),
        screening_assessment_panel(),
        rx.hstack(
            rx.button(
                rx.cond(TenantState.screening_mode == "edit", "Update screening record", "Save screening record"),
                on_click=TenantState.save_screening_record,
                color_scheme="blue",
                size="2",
            ),
            rx.cond(
                TenantState.screening_mode == "edit",
                rx.hstack(
                    rx.cond(
                        TenantState.confirm_delete_screening,
                        rx.hstack(
                            rx.text("Delete this screening record?", size="2", color="#c62828"),
                            rx.button("Yes, delete", on_click=TenantState.delete_screening_record, color_scheme="red", size="2"),
                            rx.button("Cancel", on_click=TenantState.cancel_delete_screening_record, variant="ghost", size="2"),
                            spacing="2", align="center",
                        ),
                        rx.button("Delete screening record", on_click=TenantState.confirm_delete_screening_record, color_scheme="red", variant="outline", size="2"),
                    ),
                    spacing="2",
                ),
                rx.fragment(),
            ),
            rx.button("Cancel", on_click=TenantState.cancel_screening_form, variant="ghost", color_scheme="gray", size="2"),
            spacing="3",
            wrap="wrap",
            align="center",
        ),
        spacing="4", width="100%", align_items="start",
    )


def screening_tab() -> rx.Component:
    return rx.vstack(
        rx.cond(TenantState.screening_form_success != "", rx.callout(TenantState.screening_form_success, color_scheme="green", variant="soft"), rx.fragment()),
        rx.cond(TenantState.screening_form_error != "", rx.callout(TenantState.screening_form_error, color_scheme="red", variant="soft"), rx.fragment()),
        rx.cond(
            TenantState.show_screening_form,
            screening_form(),
            rx.vstack(
                rx.button("＋ Add Screening Record", on_click=TenantState.start_new_screening_record, variant="outline", color_scheme="blue", size="2"),
                rx.cond(
                    TenantState.screening_records.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Ordered Date"),
                                rx.table.column_header_cell("Completed Date"),
                                rx.table.column_header_cell("File #"),
                                rx.table.column_header_cell("Overall Result"),
                                rx.table.column_header_cell("Credit Score"),
                                rx.table.column_header_cell("Evictions"),
                                rx.table.column_header_cell("Bankruptcies"),
                                rx.table.column_header_cell("Criminal"),
                                rx.table.column_header_cell("Eviction Search"),
                                rx.table.column_header_cell("Credit Source"),
                                rx.table.column_header_cell("Risk Tier"),
                                rx.table.column_header_cell("Deposit Recommended"),
                                rx.table.column_header_cell("Action"),
                            )
                        ),
                        rx.table.body(rx.foreach(TenantState.screening_records, screening_row)),
                        width="100%", variant="surface",
                    ),
                    rx.text("No screening records on file.", color="#888", size="2"),
                ),
                spacing="4", width="100%", align_items="start",
            ),
        ),
        spacing="4", width="100%", align_items="start",
    )


# ── Sensitive info tab ────────────────────────────────────────────────────────

def sensitive_info_tab() -> rx.Component:
    return rx.cond(
        TenantState.si_no_contact,
        rx.callout(
            "Sensitive info is linked to the primary contact. Create a primary contact first.",
            icon="info", color_scheme="gray",
        ),
        rx.vstack(
            # Contact attribution
            rx.hstack(
                rx.badge("🔒 Encrypted", color_scheme="blue", variant="soft"),
                rx.text(
                    "Stored for: " + TenantState.sensitive_contact_name,
                    size="2", color="#666",
                ),
                spacing="3", align="center",
            ),

            # Reveal toggle
            rx.hstack(
                rx.checkbox(
                    checked=TenantState.si_revealed,
                    on_change=TenantState.toggle_reveal_sensitive,
                ),
                rx.text("Reveal full SSN and Driver License", size="2"),
                align="center", spacing="2",
            ),

            rx.divider(),

            # Form
            rx.grid(
                # SSN
                rx.vstack(
                    rx.text("Social Security Number", size="1", color="#666"),
                    rx.input(
                        value=TenantState.si_ssn_input,
                        on_change=TenantState.set_si_ssn_input,
                        placeholder="XXX-XX-XXXX",
                        type=rx.cond(TenantState.si_revealed, "text", "password"),
                        size="2", width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                # Driver License
                rx.vstack(
                    rx.text("Driver License", size="1", color="#666"),
                    rx.input(
                        value=TenantState.si_dl_input,
                        on_change=TenantState.set_si_dl_input,
                        placeholder="License number",
                        type=rx.cond(TenantState.si_revealed, "text", "password"),
                        size="2", width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                # DOB
                rx.vstack(
                    rx.text("Date of Birth", size="1", color="#666"),
                    rx.input(
                        value=TenantState.si_dob_input,
                        on_change=TenantState.set_si_dob_input,
                        type="date",
                        size="2", width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                columns="3", spacing="4", width="100%",
            ),

            # Feedback
            rx.cond(
                TenantState.si_form_error != "",
                rx.callout(TenantState.si_form_error, icon="triangle_alert",
                           color_scheme="red"), rx.fragment(),
            ),
            rx.cond(
                TenantState.si_form_success != "",
                rx.callout(TenantState.si_form_success, icon="check",
                           color_scheme="green"), rx.fragment(),
            ),

            rx.button(
                "Save sensitive info",
                on_click=TenantState.save_sensitive_info,
                color_scheme="blue", size="2",
            ),

            rx.callout(
                "SSN and Driver License are encrypted at rest using Fernet (AES-128-CBC). "
                "Only the last 4 digits are stored in plain text for reference.",
                icon="shield",
                color_scheme="gray",
                size="1",
            ),

            spacing="4", width="100%", align_items="start",
        ),
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
                rx.tabs.trigger("Screening", value="screening"),
                rx.tabs.trigger("Documents", value="documents"),
                rx.tabs.trigger("Sensitive Info", value="sensitive"),
            ),
            rx.tabs.content(contacts_tab(), value="contacts", padding_top="16px"),
            rx.tabs.content(comms_tab(), value="communications", padding_top="16px"),
            rx.tabs.content(leases_tab(), value="leases", padding_top="16px"),
            rx.tabs.content(screening_tab(), value="screening", padding_top="16px"),
            rx.tabs.content(
                rx.text("Documents — coming soon", color="#888"),
                value="documents", padding_top="16px",
            ),
            rx.tabs.content(sensitive_info_tab(), value="sensitive", padding_top="16px"),
            default_value="contacts", width="100%",
        ),
        spacing="3", width="100%", align_items="start",
    )


# ── Page ──────────────────────────────────────────────────────────────────────

RESIZER_SCRIPT = """
(function() {
    function initResizer() {
        var resizer = document.getElementById('panel-resizer');
        var leftPanel = document.getElementById('tenant-list-panel');
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


def tenants_content() -> rx.Component:
    return rx.box(
        rx.script(RESIZER_SCRIPT),
        rx.hstack(
            # Left panel — tenant list
            rx.box(
                tenant_list_panel(),
                id="tenant-list-panel",
                style={
                    "width": "420px",
                    "min_width": "420px",
                    "max_height": "calc(100vh - 80px)",
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
                rx.box(style={"width": "4px", "height": "40px",
                              "background": "#c5d0f0", "border_radius": "2px"}),
                id="panel-resizer",
                style={
                    "width": "12px", "min_width": "12px", "cursor": "col-resize",
                    "display": "flex", "align_items": "center", "justify_content": "center",
                    "align_self": "stretch", "flex_shrink": "0",
                    "_hover": {"background": "#f0f4ff"},
                    "border_radius": "4px", "transition": "background 0.15s",
                },
            ),
            # Right panel — tenant detail
            rx.box(
                rx.cond(
                    TenantState.show_detail_panel,
                    tenant_detail_panel(),
                    rx.vstack(
                        rx.text("👈 Select a tenant to view details", color="#888", size="3"),
                        align_items="center", padding_top="48px",
                    ),
                ),
                style={
                    "flex": "1",
                    "min_width": "0",
                    "max_height": "calc(100vh - 80px)",
                    "overflow_y": "auto",
                },
            ),
            spacing="0",
            width="100%",
            align_items="start",
        ),
        width="100%",
    )


def tenants_page() -> rx.Component:
    return page_shell(tenants_content(), current_path="/tenants")
