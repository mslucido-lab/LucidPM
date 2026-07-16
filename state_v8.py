"""
Shared DB helpers, constants, and base state.
Import this from any page or component.
"""

import reflex as rx
import pyodbc
import datetime

SQL_SERVER = "localhost\\SQLEXPRESS"
PROD_DB_NAME = "TenantCRM"
TEST_DB_NAME = "TenantCRM_Test"

BRAND_PRIMARY = "#4A63A8"
BRAND_DARK = "#2F4C97"
BRAND_LIGHT_BG = "#F4F6FA"

METHOD_CHOICES = [
    "Call", "Email", "Text", "In person", "Letter",
    "Door Posting", "Email & CMRRR", "Email & Text",
    "Email, Door Posting, and Text", "Other",
]


def get_conn(db: str) -> pyodbc.Connection:
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={db};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def run_query(sql: str, params: tuple = (), db: str = TEST_DB_NAME) -> list[dict]:
    with get_conn(db) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def run_exec(sql: str, params: tuple = (), db: str = TEST_DB_NAME) -> None:
    with get_conn(db) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()


def fmt_date(d) -> str:
    if d is None:
        return ""
    if isinstance(d, (datetime.datetime, datetime.date)):
        return d.strftime("%m/%d/%Y")
    return str(d)


def fmt_currency(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return ""


class AppState(rx.State):
    """Global state shared across all pages."""
    use_test_db: bool = True
    # Increments each time the DB is toggled — child states watch this to reload
    db_version: int = 0

    @rx.var
    def db(self) -> str:
        return TEST_DB_NAME if self.use_test_db else PROD_DB_NAME

    @rx.var
    def db_label(self) -> str:
        return "TEST" if self.use_test_db else "PRODUCTION"

    @rx.var
    def db_toggle_label(self) -> str:
        return "Switch to Production" if self.use_test_db else "Switch to Test"

    def toggle_db(self):
        self.use_test_db = not self.use_test_db
        self.db_version += 1
        # Yield reload events for all page states that need refreshing
        from LucidPM_Reflex.pages.dashboard import DashboardState
        from LucidPM_Reflex.pages.rent_roll import RentRollState
        from LucidPM_Reflex.pages.property_financials import PropertyFinancialsState
        from LucidPM_Reflex.pages.property_financials_analytics import PropertyFinancialsAnalyticsState
        from LucidPM_Reflex.pages.proforma import ProformaState
        from LucidPM_Reflex.pages.waiting_list import WaitingListState
        from LucidPM_Reflex.pages.communications_report import CommReportState
        from LucidPM_Reflex.pages.tenants import TenantState
        from LucidPM_Reflex.pages.work_items import WorkItemState
        from LucidPM_Reflex.pages.leases_expiring import LeasesExpiringState
        from LucidPM_Reflex.pages.lease_documents import LeaseDocumentState
        from LucidPM_Reflex.pages.lease_package_builder import LeasePackageBuilderState
        from LucidPM_Reflex.pages.admin_settings import AdminSettingsState
        yield AdminSettingsState.reload_on_db_change
        yield LeaseDocumentState.reload_on_db_change
        yield LeasePackageBuilderState.reload_on_db_change
        yield LeasesExpiringState.reload_on_db_change
        yield WorkItemState.reload_on_db_change
        yield TenantState.reload_on_db_change
        yield CommReportState.reload_on_db_change
        yield DashboardState.reload_on_db_change
        yield RentRollState.reload_on_db_change
        yield PropertyFinancialsState.reload_on_db_change
        yield PropertyFinancialsAnalyticsState.reload_on_db_change
        yield ProformaState.reload_on_db_change
        yield WaitingListState.reload_on_db_change
