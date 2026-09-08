# pages/communications_report.py
# LucidPM Reflex — Communications Report page
# Route: /communications-report

import base64
import datetime as dt
import io
from typing import Optional

import reflex as rx
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from ..state import AppState, run_query, fmt_date


# ---------------------------------------------------------------------------
# Pure helpers — no pandas, no datetime objects in return values
# ---------------------------------------------------------------------------

def _safe_str(val) -> str:
    if val is None:
        return ""
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return ""
    except Exception:
        pass
    return str(val).strip()


def _fmt_dt(val) -> str:
    if val is None:
        return ""
    if isinstance(val, dt.datetime):
        return val.strftime("%m/%d/%Y %H:%M")
    if isinstance(val, dt.date):
        return val.strftime("%m/%d/%Y")
    try:
        import pandas as pd
        return pd.to_datetime(val).strftime("%m/%d/%Y %H:%M")
    except Exception:
        return str(val)


def _fmt_date_only(val) -> str:
    if val is None:
        return ""
    if isinstance(val, dt.datetime):
        return val.strftime("%m/%d/%Y")
    if isinstance(val, dt.date):
        return val.strftime("%m/%d/%Y")
    try:
        import pandas as pd
        return pd.to_datetime(val).strftime("%m/%d/%Y")
    except Exception:
        return str(val)


def _log_text(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = []
    for row in rows:
        ts_txt = row.get("CommDate_display", "")
        method = _safe_str(row.get("Method"))
        subject = _safe_str(row.get("Subject"))
        body = _safe_str(row.get("Body"))
        fromto = _safe_str(row.get("FromTo"))
        template = _safe_str(row.get("TemplateName"))
        outcome = _safe_str(row.get("Outcome"))
        notes = _safe_str(row.get("Notes"))
        next_action = row.get("NextActionDate_display", "")

        header = f"[{ts_txt}] {method}"
        if fromto:
            header += f" ({fromto})"
        if subject:
            header += f" - {subject}"
        lines.append(header.strip())
        if template:
            lines.append(f"Template: {template}")
        if outcome:
            lines.append(f"Outcome: {outcome}")
        if body:
            lines.append(body)
        if notes:
            lines.append(f"Notes: {notes}")
        if next_action:
            lines.append(f"Next action: {next_action}")
        lines.append("-" * 60)
    return "\n".join(lines)


def _pdf_bytes(rows: list[dict], tenant_name: str, date_range: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Tenant Communications Report — {tenant_name or 'Tenant'}", styles["Title"]))
    if date_range:
        story.append(Paragraph(date_range, styles["Normal"]))
    story.append(Spacer(1, 12))

    if not rows:
        story.append(Paragraph("No communications found.", styles["Normal"]))
    else:
        for row in rows:
            ts_txt = row.get("CommDate_display", "")
            method = _safe_str(row.get("Method"))
            subject = _safe_str(row.get("Subject"))
            outcome = _safe_str(row.get("Outcome"))
            template = _safe_str(row.get("TemplateName"))
            notes = _safe_str(row.get("Notes"))
            next_action = row.get("NextActionDate_display", "")

            parts = [p for p in [ts_txt, method, subject] if p]
            story.append(Paragraph(" | ".join(parts) or "Communication", styles["Heading4"]))
            if template:
                story.append(Paragraph(f"Template: {template}", styles["Normal"]))
            if outcome:
                story.append(Paragraph(f"Outcome: {outcome}", styles["Normal"]))
            if notes:
                story.append(Paragraph(notes.replace("\n", "<br/>"), styles["Normal"]))
            if next_action:
                story.append(Paragraph(f"Next action: {next_action}", styles["Normal"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _query_comms(tenant_id: int, start: str, end: str, db: str) -> list[dict]:
    """
    Query Communications for a tenant. Returns list[dict] with only str/None values —
    safe for Reflex state serialization.
    """
    col_rows = run_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
        db=db,
    )
    available = {r["COLUMN_NAME"] for r in col_rows}

    preferred = [
        "CommunicationID", "TenantID", "CommDate", "Method", "Subject",
        "TemplateName", "Outcome", "Body", "FromTo", "NextActionDate",
        "Notes", "ContactID", "PropertyID",
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

    raw_rows = run_query(sql, tuple(params), db=db)

    # Normalize: convert all values to str/None and add display-formatted columns
    safe_rows = []
    for row in raw_rows:
        safe: dict = {}
        for k, v in row.items():
            if v is None:
                safe[k] = None
            elif isinstance(v, (dt.datetime, dt.date)):
                safe[k] = v.isoformat()
            else:
                safe[k] = str(v)
        # Pre-formatted display strings used by table and log
        safe["CommDate_display"] = _fmt_dt(row.get("CommDate"))
        safe["NextActionDate_display"] = _fmt_date_only(row.get("NextActionDate"))
        safe_rows.append(safe)

    return safe_rows


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class CommReportState(AppState):
    # Tenant picker — parallel lists, both list[str] to stay serializable
    tenant_labels: list[str] = []
    tenant_ids_str: list[str] = []
    selected_tenant_label: str = ""

    # Filters
    start_date: str = ""
    end_date: str = ""
    include_log: bool = True

    # Results — list[dict] with str/None values only
    report_rows: list[dict] = []
    log_text: str = ""
    tenant_name: str = ""
    row_count: int = 0

    # UI flags
    loading: bool = False
    error_msg: str = ""
    generated: bool = False

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def on_load(self):
        today = dt.date.today()
        self.start_date = (today - dt.timedelta(days=90)).isoformat()
        self.end_date = today.isoformat()
        self.error_msg = ""
        self.generated = False
        self.report_rows = []
        self.log_text = ""
        self.row_count = 0
        self._load_tenants()

    def reload_on_db_change(self):
        """Yielded by AppState.toggle_db — refresh tenant list for new DB."""
        self.generated = False
        self.report_rows = []
        self.log_text = ""
        self.error_msg = ""
        self._load_tenants()

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _load_tenants(self):
        try:
            rows = run_query(
                "SELECT [TenantID], [TenantName] FROM [Tenants] ORDER BY [TenantName]",
                db=self.db,
            )
            labels, ids = [], []
            for r in rows:
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

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def set_tenant(self, label: str):
        self.selected_tenant_label = label
        self.generated = False
        self.report_rows = []
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
        self.report_rows = []
        self.log_text = ""
        self.row_count = 0

        tenant_id = self._get_tenant_id()
        if tenant_id is None:
            self.error_msg = "Please select a tenant."
            return

        self.loading = True
        try:
            rows = _query_comms(tenant_id, self.start_date, self.end_date, self.db)

            name_rows = run_query(
                "SELECT [TenantName] FROM [Tenants] WHERE [TenantID] = ?",
                (int(tenant_id),),
                db=self.db,
            )
            self.tenant_name = (
                str(name_rows[0]["TenantName"]).strip() if name_rows else f"Tenant {tenant_id}"
            )

            self.report_rows = rows
            self.row_count = len(rows)
            self.log_text = _log_text(rows) if self.include_log else ""
            self.generated = True

        except Exception as ex:
            self.error_msg = f"Error generating report: {ex}"
        finally:
            self.loading = False

    def download_csv(self):
        if not self.report_rows:
            return
        cols = ["CommDate_display", "Method", "Subject", "Outcome",
                "NextActionDate_display", "TemplateName", "Notes", "Body"]
        lines = [",".join(f'"{c}"' for c in cols)]
        for row in self.report_rows:
            lines.append(",".join(
                '"' + str(row.get(c) or "").replace('"', '""') + '"' for c in cols
            ))
        b64 = base64.b64encode("\n".join(lines).encode("utf-8")).decode()
        tid = self._get_tenant_id() or "unknown"
        return rx.download(
            data=f"data:text/csv;base64,{b64}",
            filename=f"tenant_{tid}_communications_report.csv",
        )

    def download_txt(self):
        if not self.log_text:
            return
        b64 = base64.b64encode(self.log_text.encode("utf-8")).decode()
        tid = self._get_tenant_id() or "unknown"
        return rx.download(
            data=f"data:text/plain;base64,{b64}",
            filename=f"tenant_{tid}_communications_report.txt",
        )

    def download_pdf(self):
        if not self.report_rows:
            return
        pdf = _pdf_bytes(
            self.report_rows,
            self.tenant_name,
            f"{self.start_date} to {self.end_date}",
        )
        b64 = base64.b64encode(pdf).decode()
        tid = self._get_tenant_id() or "unknown"
        return rx.download(
            data=f"data:application/pdf;base64,{b64}",
            filename=f"tenant_{tid}_communications_report.pdf",
        )


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------

def _filter_bar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text("Tenant", size="1", color_scheme="gray"),
                rx.cond(
                    CommReportState.tenant_labels.length() > 0,
                    rx.select(
                        CommReportState.tenant_labels,
                        value=CommReportState.selected_tenant_label,
                        on_change=CommReportState.set_tenant,
                        width="280px",
                    ),
                    rx.text("Loading…", size="2", color_scheme="gray"),
                ),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                rx.text("Start date", size="1", color_scheme="gray"),
                rx.input(
                    type="date",
                    value=CommReportState.start_date,
                    on_change=CommReportState.set_start_date,
                    width="160px",
                ),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                rx.text("End date", size="1", color_scheme="gray"),
                rx.input(
                    type="date",
                    value=CommReportState.end_date,
                    on_change=CommReportState.set_end_date,
                    width="160px",
                ),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                rx.text("Options", size="1", color_scheme="gray"),
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
                align="start",
                padding_top="8px",
            ),
            rx.button(
                rx.cond(CommReportState.loading, "Generating…", "Generate Report"),
                on_click=CommReportState.generate_report,
                disabled=CommReportState.loading,
                color_scheme="blue",
                size="2",
                margin_top="20px",
            ),
            spacing="4",
            align="end",
            wrap="wrap",
        ),
        background=rx.color("gray", 2),
        border=f"1px solid {rx.color('gray', 4)}",
        border_radius="8px",
        padding="16px",
        width="100%",
    )


def _table_row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.get("CommDate_display", ""), size="1"), padding="6px 10px"),
        rx.table.cell(rx.text(row.get("Method", ""), size="1"), padding="6px 10px"),
        rx.table.cell(rx.text(row.get("Subject", ""), size="1"), padding="6px 10px"),
        rx.table.cell(rx.text(row.get("Outcome", ""), size="1"), padding="6px 10px"),
        rx.table.cell(rx.text(row.get("NextActionDate_display", ""), size="1"), padding="6px 10px"),
        rx.table.cell(rx.text(row.get("TemplateName", ""), size="1"), padding="6px 10px"),
        rx.table.cell(
            rx.text(row.get("Notes", ""), size="1", style={"white_space": "pre-wrap"}),
            padding="6px 10px",
            max_width="220px",
        ),
        _hover={"background": "#F0F4FF"},
        vertical_align="top",
    )


def _results_table() -> rx.Component:
    headers = ["Date", "Method", "Subject", "Outcome", "Next Action", "Template", "Notes"]
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    *[
                        rx.table.column_header_cell(
                            h,
                            style={
                                "font_size": "11px",
                                "font_weight": "700",
                                "color": "#4A63A8",
                                "padding": "8px 10px",
                                "white_space": "nowrap",
                            },
                        )
                        for h in headers
                    ]
                )
            ),
            rx.table.body(rx.foreach(CommReportState.report_rows, _table_row)),
            width="100%",
        ),
        overflow_x="auto",
        border="1px solid #E2E8F0",
        border_radius="6px",
        width="100%",
    )


def _download_bar() -> rx.Component:
    return rx.hstack(
        rx.button("⬇ CSV", on_click=CommReportState.download_csv,
                  variant="outline", color_scheme="blue", size="2"),
        rx.cond(
            CommReportState.include_log & (CommReportState.log_text != ""),
            rx.button("⬇ TXT Log", on_click=CommReportState.download_txt,
                      variant="outline", color_scheme="blue", size="2"),
        ),
        rx.button("⬇ PDF", on_click=CommReportState.download_pdf,
                  variant="outline", color_scheme="blue", size="2"),
        spacing="3",
    )


def _results_section() -> rx.Component:
    return rx.cond(
        CommReportState.generated,
        rx.vstack(
            rx.hstack(
                rx.text(CommReportState.tenant_name, size="4", weight="bold", color="#2F4C97"),
                rx.badge(
                    CommReportState.row_count.to_string() + " records",
                    color_scheme="blue",
                    variant="soft",
                ),
                rx.text(
                    CommReportState.start_date + " → " + CommReportState.end_date,
                    size="2",
                    color_scheme="gray",
                ),
                spacing="3",
                align="center",
            ),
            _download_bar(),
            rx.cond(
                CommReportState.row_count > 0,
                _results_table(),
                rx.callout(
                    "No communications found for this tenant in the selected date range.",
                    icon="info",
                    color_scheme="gray",
                ),
            ),
            rx.cond(
                CommReportState.include_log & (CommReportState.log_text != ""),
                rx.vstack(
                    rx.text("Plain-text log", size="2", weight="bold", color="#4A63A8"),
                    rx.text_area(
                        value=CommReportState.log_text,
                        read_only=True,
                        height="320px",
                        width="100%",
                        style={"font_family": "monospace", "font_size": "12px", "background": "#F8FAFC"},
                    ),
                    spacing="2",
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@rx.page(route="/communications-report", on_load=CommReportState.on_load)
def communications_report_page() -> rx.Component:
    return rx.vstack(
        rx.heading("Communications Report", size="5", color="#2F4C97"),
        rx.cond(
            CommReportState.error_msg != "",
            rx.callout(
                CommReportState.error_msg,
                icon="triangle_alert",
                color_scheme="red",
                width="100%",
            ),
        ),
        _filter_bar(),
        _results_section(),
        spacing="5",
        padding="24px",
        width="100%",
        align="start",
    )
