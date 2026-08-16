"""
Communications Report page — tenant communication history with filters and exports.

Layout:
  - Filter bar (tenant picker, start date, end date, include log checkbox)
  - Generate button
  - Results table (Date, Method, Subject, Outcome, Next Action, Property)
  - Downloads: CSV, plain-text log, PDF (via FastAPI endpoint)
"""

import base64
import datetime as dt
import io
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query,
    BRAND_PRIMARY, BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# ── Data model ────────────────────────────────────────────────────────────────

class CommRow(rx.Base):
    comm_date: str = ""
    method: str = ""
    subject: str = ""
    outcome: str = ""
    next_action_date: str = ""
    property_name: str = ""
    # kept in state for log/pdf but not shown in main table
    notes: str = ""
    body: str = ""
    template_name: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dt(val) -> str:
    if val is None:
        return ""
    if isinstance(val, dt.datetime):
        return val.strftime("%m/%d/%Y %H:%M")
    if isinstance(val, dt.date):
        return val.strftime("%m/%d/%Y")
    return str(val)


def _fmt_date_only(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (dt.datetime, dt.date)):
        return val.strftime("%m/%d/%Y")
    return str(val)


def _build_log(rows: list[CommRow]) -> str:
    if not rows:
        return ""
    lines = []
    for row in rows:
        header = f"[{row.comm_date}] {row.method}"
        if row.subject:
            header += f" - {row.subject}"
        lines.append(header.strip())
        if row.template_name:
            lines.append(f"Template: {row.template_name}")
        if row.outcome:
            lines.append(f"Outcome: {row.outcome}")
        if row.body:
            lines.append(row.body)
        if row.notes:
            lines.append(f"Notes: {row.notes}")
        if row.next_action_date:
            lines.append(f"Next action: {row.next_action_date}")
        lines.append("-" * 60)
    return "\n".join(lines)


def _build_csv(rows: list[CommRow]) -> str:
    headers = ["Date", "Method", "Subject", "Outcome", "Next Action", "Property", "Notes", "Body", "Template"]
    lines = [",".join(f'"{h}"' for h in headers)]
    for row in rows:
        vals = [
            row.comm_date, row.method, row.subject, row.outcome,
            row.next_action_date, row.property_name,
            row.notes, row.body, row.template_name,
        ]
        lines.append(",".join('"' + str(v or "").replace('"', '""') + '"' for v in vals))
    return "\n".join(lines)


def _query_comms(tenant_id: int, start: str, end: str, db: str, property_map: dict) -> list[CommRow]:
    """Query Communications table and return list of CommRow."""
    col_rows = run_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
        db=db,
    )
    available = {r["COLUMN_NAME"] for r in col_rows}

    preferred = [
        "CommunicationID", "TenantID", "CommDate", "Method", "Subject",
        "TemplateName", "Outcome", "Body", "FromTo", "NextActionDate",
        "Notes", "PropertyID",
    ]
    cols = [f"[{c}]" for c in preferred if c in available]
    if not cols:
        return []

    sql = f"SELECT {', '.join(cols)} FROM [Communications] WHERE [TenantID] = ?"
    params: list = [int(tenant_id)]

    if start and "CommDate" in available:
        sql += " AND [CommDate] >= ?"
        params.append(dt.datetime.fromisoformat(start))

    if end and "CommDate" in available:
        sql += " AND [CommDate] <= ?"
        params.append(dt.datetime.fromisoformat(end) + dt.timedelta(days=1) - dt.timedelta(seconds=1))

    order = []
    if "CommDate" in available:
        order.append("[CommDate] ASC")
    if "CommunicationID" in available:
        order.append("[CommunicationID] ASC")
    if order:
        sql += " ORDER BY " + ", ".join(order)

    raw = run_query(sql, tuple(params), db=db)

    result = []
    for r in raw:
        pid = r.get("PropertyID")
        prop_name = property_map.get(int(pid), "") if pid is not None else ""
        result.append(CommRow(
            comm_date=_fmt_dt(r.get("CommDate")),
            method=str(r.get("Method") or "").strip(),
            subject=str(r.get("Subject") or "").strip(),
            outcome=str(r.get("Outcome") or "").strip(),
            next_action_date=_fmt_date_only(r.get("NextActionDate")),
            property_name=prop_name,
            notes=str(r.get("Notes") or "").strip(),
            body=str(r.get("Body") or "").strip(),
            template_name=str(r.get("TemplateName") or "").strip(),
        ))
    return result


# ── State ─────────────────────────────────────────────────────────────────────

class CommReportState(AppState):

    # Tenant picker
    tenant_labels: list[str] = []
    tenant_ids_str: list[str] = []
    selected_tenant_label: str = ""

    # Filters
    start_date: str = ""
    end_date: str = ""
    include_log: bool = True

    # Results
    rows: list[CommRow] = []
    log_text: str = ""
    tenant_name: str = ""
    row_count: int = 0

    # UI flags
    loading: bool = False
    error_msg: str = ""
    generated: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_load(self):
        today = dt.date.today()
        self.start_date = (today - dt.timedelta(days=90)).isoformat()
        self.end_date = today.isoformat()
        self.error_msg = ""
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.row_count = 0
        self._load_tenants()

    def reload_on_db_change(self):
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.error_msg = ""
        self._load_tenants()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_tenants(self):
        try:
            raw = run_query(
                "SELECT [TenantID], [TenantName] FROM [Tenants] ORDER BY [TenantName]",
                db=self.db,
            )
            labels, ids = [], []
            for r in raw:
                tid = int(r["TenantID"])
                name = str(r.get("TenantName") or "").strip() or f"Tenant {tid}"
                labels.append(f"{name} (ID={tid})")
                ids.append(str(tid))
            self.tenant_labels = labels
            self.tenant_ids_str = ids
            self.selected_tenant_label = labels[0] if labels else ""
        except Exception as ex:
            self.error_msg = f"Could not load tenants: {ex}"

    def _get_tenant_id(self) -> Optional[int]:
        try:
            idx = self.tenant_labels.index(self.selected_tenant_label)
            return int(self.tenant_ids_str[idx])
        except (ValueError, IndexError):
            return None

    def _get_property_map(self) -> dict:
        try:
            raw = run_query(
                "SELECT [PropertyID], [PropertyName] FROM [Properties]",
                db=self.db,
            )
            return {int(r["PropertyID"]): str(r["PropertyName"]) for r in raw}
        except Exception:
            return {}

    # ── Event handlers ─────────────────────────────────────────────────────────

    def set_tenant(self, label: str):
        self.selected_tenant_label = label
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.error_msg = ""

    def set_start_date(self, val: str):
        self.start_date = val

    def set_end_date(self, val: str):
        self.end_date = val

    def set_include_log(self, val: bool):
        self.include_log = val

    def generate_report(self):
        self.error_msg = ""
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.row_count = 0

        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            self.error_msg = "Please select a tenant."
            return

        self.loading = True
        try:
            property_map = self._get_property_map()
            rows = _query_comms(tenant_id, self.start_date, self.end_date, self.db, property_map)

            name_rows = run_query(
                "SELECT [TenantName] FROM [Tenants] WHERE [TenantID] = ?",
                (int(tenant_id),),
                db=self.db,
            )
            self.tenant_name = (
                str(name_rows[0]["TenantName"]).strip() if name_rows else f"Tenant {tenant_id}"
            )

            self.rows = rows
            self.row_count = len(rows)
            self.log_text = _build_log(rows) if self.include_log else ""
            self.generated = True

        except Exception as ex:
            self.error_msg = f"Error generating report: {ex}"
        finally:
            self.loading = False

    def download_csv(self):
        if not self.rows:
            return
        csv_str = _build_csv(self.rows)
        b64 = base64.b64encode(csv_str.encode("utf-8")).decode()
        tid = self._get_tenant_id() or "unknown"
        return rx.download(
            data=f"data:text/csv;base64,{b64}",
            filename=f"tenant_{tid}_communications.csv",
        )

    def download_txt(self):
        if not self.log_text:
            return
        b64 = base64.b64encode(self.log_text.encode("utf-8")).decode()
        tid = self._get_tenant_id() or "unknown"
        return rx.download(
            data=f"data:text/plain;base64,{b64}",
            filename=f"tenant_{tid}_communications_log.txt",
        )

    # ── Computed vars ──────────────────────────────────────────────────────────

    @rx.var
    def pdf_url(self) -> str:
        tid = ""
        try:
            idx = self.tenant_labels.index(self.selected_tenant_label)
            tid = self.tenant_ids_str[idx]
        except (ValueError, IndexError):
            pass
        return (
            f"http://localhost:8000/api/communications-pdf"
            f"?tenant_id={tid}&start={self.start_date}&end={self.end_date}&db={self.db}"
        )

    @rx.var
    def has_log(self) -> bool:
        return self.include_log and bool(self.log_text)


# ── UI helpers ────────────────────────────────────────────────────────────────

def comm_table_row(row: CommRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.comm_date, size="2", color="#555")),
        rx.table.cell(rx.text(row.method, size="2")),
        rx.table.cell(rx.text(row.subject, size="2")),
        rx.table.cell(rx.text(row.outcome, size="2", color="#555")),
        rx.table.cell(rx.text(row.next_action_date, size="2", color="#555")),
        rx.table.cell(rx.text(row.property_name, size="2", color="#555")),
        _hover={"background": "#F0F4FF"},
        vertical_align="top",
    )


# ── Page content ──────────────────────────────────────────────────────────────

def comm_report_content() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Heading
            rx.heading("Communications Report", size="5", color=BRAND_DARK),

            # Error banner
            rx.cond(
                CommReportState.error_msg != "",
                rx.callout(
                    CommReportState.error_msg,
                    icon="triangle_alert",
                    color_scheme="red",
                    width="100%",
                ),
            ),

            # Filter bar
            rx.box(
                rx.hstack(
                    # Tenant picker
                    rx.vstack(
                        rx.text("Tenant", size="1", color="#666"),
                        rx.cond(
                            CommReportState.tenant_labels.length() > 0,
                            rx.select(
                                CommReportState.tenant_labels,
                                value=CommReportState.selected_tenant_label,
                                on_change=CommReportState.set_tenant,
                                size="2",
                                width="280px",
                            ),
                            rx.text("Loading…", size="2", color="#999"),
                        ),
                        spacing="1",
                    ),
                    # Start date
                    rx.vstack(
                        rx.text("Start date", size="1", color="#666"),
                        rx.input(
                            value=CommReportState.start_date,
                            on_change=CommReportState.set_start_date,
                            type="date",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    # End date
                    rx.vstack(
                        rx.text("End date", size="1", color="#666"),
                        rx.input(
                            value=CommReportState.end_date,
                            on_change=CommReportState.set_end_date,
                            type="date",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    # Include log checkbox
                    rx.vstack(
                        rx.text("Options", size="1", color="#666"),
                        rx.hstack(
                            rx.checkbox(
                                checked=CommReportState.include_log,
                                on_change=CommReportState.set_include_log,
                            ),
                            rx.text("Include plain-text log", size="2"),
                            align="center",
                            spacing="2",
                        ),
                        spacing="1",
                        padding_top="8px",
                    ),
                    # Generate button
                    rx.button(
                        rx.cond(CommReportState.loading, "Generating…", "Generate Report"),
                        on_click=CommReportState.generate_report,
                        disabled=CommReportState.loading,
                        color_scheme="blue",
                        size="2",
                        style={"align_self": "flex-end"},
                    ),
                    spacing="4",
                    align="end",
                    wrap="wrap",
                    width="100%",
                ),
                background="#F8FAFC",
                border="1px solid #E2E8F0",
                border_radius="8px",
                padding="16px",
                width="100%",
            ),

            # Results
            rx.cond(
                CommReportState.generated,
                rx.vstack(
                    # Summary row + downloads
                    rx.hstack(
                        rx.text(
                            CommReportState.tenant_name,
                            size="3",
                            weight="bold",
                            color=BRAND_DARK,
                        ),
                        rx.badge(
                            CommReportState.row_count.to_string() + " records",
                            color_scheme="blue",
                            variant="soft",
                        ),
                        rx.text(
                            CommReportState.start_date + " → " + CommReportState.end_date,
                            size="2",
                            color="#888",
                        ),
                        rx.spacer(),
                        # CSV download
                        rx.button(
                            "⬇ CSV",
                            on_click=CommReportState.download_csv,
                            variant="outline",
                            color_scheme="blue",
                            size="2",
                        ),
                        # TXT log download
                        rx.cond(
                            CommReportState.has_log,
                            rx.button(
                                "⬇ TXT Log",
                                on_click=CommReportState.download_txt,
                                variant="outline",
                                color_scheme="blue",
                                size="2",
                            ),
                            rx.fragment(),
                        ),
                        # PDF — same pattern as rent roll: link to FastAPI endpoint
                        rx.cond(
                            CommReportState.row_count > 0,
                            rx.link(
                                rx.button(
                                    "⬇ PDF",
                                    variant="outline",
                                    color_scheme="blue",
                                    size="2",
                                ),
                                href=CommReportState.pdf_url,
                                is_external=True,
                            ),
                            rx.fragment(),
                        ),
                        align="center",
                        width="100%",
                        spacing="3",
                        wrap="wrap",
                    ),

                    # Table
                    rx.cond(
                        CommReportState.row_count > 0,
                        rx.box(
                            rx.table.root(
                                rx.table.header(
                                    rx.table.row(
                                        rx.table.column_header_cell("Date"),
                                        rx.table.column_header_cell("Method"),
                                        rx.table.column_header_cell("Subject"),
                                        rx.table.column_header_cell("Outcome"),
                                        rx.table.column_header_cell("Next Action"),
                                        rx.table.column_header_cell("Property"),
                                    )
                                ),
                                rx.table.body(
                                    rx.foreach(CommReportState.rows, comm_table_row)
                                ),
                                width="100%",
                                variant="surface",
                            ),
                            width="100%",
                            overflow_x="auto",
                        ),
                        rx.text(
                            "No communications found for this tenant in the selected date range.",
                            color="#888",
                            size="2",
                        ),
                    ),

                    # Plain-text log
                    rx.cond(
                        CommReportState.has_log,
                        rx.vstack(
                            rx.text("Plain-text log", size="2", weight="bold", color=BRAND_PRIMARY),
                            rx.text_area(
                                value=CommReportState.log_text,
                                read_only=True,
                                height="320px",
                                width="100%",
                                style={
                                    "font_family": "monospace",
                                    "font_size": "12px",
                                    "background": "#F8FAFC",
                                },
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),

                    spacing="4",
                    width="100%",
                    align_items="start",
                ),
            ),

            spacing="5",
            width="100%",
            align_items="start",
            padding="24px",
        ),
        width="100%",
    )


def communications_report_page() -> rx.Component:
    return page_shell(comm_report_content(), current_path="/communications-report")
