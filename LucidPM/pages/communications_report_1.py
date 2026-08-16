# pages/communications_report.py
# LucidPM Reflex — Communications Report page
# Route: /communications-report
# Migrated from page_communications_report() in app3_master_v2_4_9.py

import base64
import datetime as dt
import io
from typing import Optional

import pandas as pd
import reflex as rx
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..state import AppState


# ---------------------------------------------------------------------------
# Helpers (ported from Streamlit app)
# ---------------------------------------------------------------------------

def _communications_log_text(rows: list[dict]) -> str:
    """Format list-of-dicts records into a readable plain-text log."""
    if not rows:
        return ""

    lines = []
    for row in rows:
        ts = row.get("CommDate")
        try:
            ts_txt = pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M") if ts and not pd.isna(ts) else ""
        except Exception:
            ts_txt = str(ts or "")

        method = str(row.get("Method") or "").strip()
        subject = str(row.get("Subject") or "").strip()
        body = str(row.get("Body") or "").strip()
        fromto = str(row.get("FromTo") or "").strip()
        template_name = str(row.get("TemplateName") or "").strip()
        outcome = str(row.get("Outcome") or "").strip()
        notes = str(row.get("Notes") or "").strip()
        next_action = row.get("NextActionDate")
        try:
            next_action_txt = (
                pd.to_datetime(next_action).strftime("%Y-%m-%d")
                if next_action and not pd.isna(next_action)
                else ""
            )
        except Exception:
            next_action_txt = str(next_action or "")

        header = f"[{ts_txt}] {method} {f'({fromto})' if fromto else ''} - {subject}".strip()
        lines.append(header)
        if template_name:
            lines.append(f"Template: {template_name}")
        if outcome:
            lines.append(f"Outcome: {outcome}")
        if body:
            lines.append(body)
        if notes:
            lines.append(f"Notes: {notes}")
        if next_action_txt:
            lines.append(f"Next action: {next_action_txt}")
        lines.append("-" * 60)

    return "\n".join(lines)


def _communications_pdf_bytes(
    rows: list[dict], tenant_name: str = "Tenant", date_range_text: str = ""
) -> bytes:
    """Generate a PDF from list-of-dicts communications records."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    safe_name = str(tenant_name or "Tenant").strip() or "Tenant"
    story.append(Paragraph(f"Tenant Communications Report — {safe_name}", styles["Title"]))
    if date_range_text:
        story.append(Paragraph(str(date_range_text), styles["Normal"]))
    story.append(Spacer(1, 12))

    if not rows:
        story.append(Paragraph("No communications found.", styles["Normal"]))
    else:
        for row in rows:
            ts = row.get("CommDate")
            try:
                ts_txt = pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M") if ts and not pd.isna(ts) else ""
            except Exception:
                ts_txt = str(ts or "")

            method = str(row.get("Method") or "").strip()
            subject = str(row.get("Subject") or "").strip()
            notes = str(row.get("Notes") or "").strip()
            outcome = str(row.get("Outcome") or "").strip()
            template_name = str(row.get("TemplateName") or "").strip()
            next_action = row.get("NextActionDate")
            try:
                next_action_txt = (
                    pd.to_datetime(next_action).strftime("%Y-%m-%d")
                    if next_action and not pd.isna(next_action)
                    else ""
                )
            except Exception:
                next_action_txt = str(next_action or "")

            header_parts = [p for p in [ts_txt, method, subject] if p]
            header = " | ".join(header_parts) if header_parts else "Communication"
            story.append(Paragraph(header, styles["Heading4"]))

            if template_name:
                story.append(Paragraph(f"Template: {template_name}", styles["Normal"]))
            if outcome:
                story.append(Paragraph(f"Outcome: {outcome}", styles["Normal"]))
            if notes:
                story.append(Paragraph(notes.replace("\n", "<br/>"), styles["Normal"]))
            if next_action_txt:
                story.append(Paragraph(f"Next action: {next_action_txt}", styles["Normal"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _fmt_date(val) -> str:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        return pd.to_datetime(val).strftime("%m/%d/%Y")
    except Exception:
        return str(val or "")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class CommReportState(AppState):
    # Tenant picker
    tenant_options: list[str] = []          # "Name (ID=N)" display labels
    tenant_ids: list[int] = []              # parallel list of IDs
    selected_tenant_label: str = ""

    # Filters
    start_date: str = ""                    # ISO date string YYYY-MM-DD
    end_date: str = ""
    include_log: bool = True

    # Results
    report_rows: list[dict] = []            # list of dicts for the table
    log_text: str = ""
    tenant_name: str = ""
    row_count: int = 0

    # UI state
    loading: bool = False
    error_msg: str = ""
    generated: bool = False

    def on_load(self):
        """Load tenant list on page mount."""
        today = dt.date.today()
        self.start_date = (today - dt.timedelta(days=90)).isoformat()
        self.end_date = today.isoformat()
        self.error_msg = ""
        self.generated = False
        self.report_rows = []
        self.log_text = ""
        self._load_tenants()

    def _load_tenants(self):
        try:
            from ..state import df_query, get_active_db_name
            df = df_query(
                "SELECT [TenantID], [TenantName] FROM [Tenants] ORDER BY [TenantName]",
                database_name=get_active_db_name(),
            )
            labels = []
            ids = []
            for _, row in df.iterrows():
                tid = int(row["TenantID"])
                name = str(row.get("TenantName") or "").strip() or f"Tenant {tid}"
                labels.append(f"{name} (ID={tid})")
                ids.append(tid)
            self.tenant_options = labels
            self.tenant_ids = ids
            if labels:
                self.selected_tenant_label = labels[0]
        except Exception as ex:
            self.error_msg = f"Could not load tenants: {ex}"

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

    def toggle_include_log(self, val: bool):
        self.include_log = val

    def generate_report(self):
        self.error_msg = ""
        self.generated = False
        self.report_rows = []
        self.log_text = ""

        # Resolve tenant ID
        tenant_id = self._resolve_tenant_id()
        if tenant_id is None:
            self.error_msg = "Please select a tenant."
            return

        self.loading = True
        try:
            from ..state import df_query, get_active_db_name
            db = get_active_db_name()

            # Resolve column availability
            col_df = df_query(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
                database_name=db,
            )
            available_columns = set(col_df["COLUMN_NAME"].tolist()) if not col_df.empty else set()

            preferred = [
                "CommunicationID", "TenantID", "CommDate", "Method", "Subject",
                "TemplateName", "Outcome", "Body", "FromTo", "NextActionDate",
                "Notes", "ContactID", "PropertyID",
            ]
            selected = [f"[{c}]" for c in preferred if c in available_columns]
            if not selected:
                self.error_msg = "Could not find expected columns in Communications table."
                self.loading = False
                return

            sql = f"SELECT {', '.join(selected)} FROM [Communications] WHERE [TenantID] = ?"
            params: list = [int(tenant_id)]

            if self.start_date and "CommDate" in available_columns:
                sql += " AND [CommDate] >= ?"
                params.append(pd.to_datetime(self.start_date))

            if self.end_date and "CommDate" in available_columns:
                sql += " AND [CommDate] <= ?"
                end_dt = pd.to_datetime(self.end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                params.append(end_dt)

            order_parts = []
            if "CommDate" in available_columns:
                order_parts.append("[CommDate] ASC")
            if "CommunicationID" in available_columns:
                order_parts.append("[CommunicationID] ASC")
            if order_parts:
                sql += " ORDER BY " + ", ".join(order_parts)

            df = df_query(sql, tuple(params), database_name=db)

            # Backfill missing optional columns
            for col in ["Body", "FromTo", "TemplateName", "Outcome", "Notes"]:
                if col not in df.columns:
                    df[col] = ""
            for col in ["ContactID", "PropertyID", "NextActionDate"]:
                if col not in df.columns:
                    df[col] = None

            # Format dates for display
            for date_col in ["CommDate", "NextActionDate"]:
                if date_col in df.columns:
                    df[date_col + "_display"] = df[date_col].apply(_fmt_date)

            # Resolve tenant name
            tname_df = df_query(
                "SELECT [TenantName] FROM [Tenants] WHERE [TenantID] = ?",
                (int(tenant_id),),
                database_name=db,
            )
            self.tenant_name = (
                str(tname_df.iloc[0]["TenantName"]).strip()
                if not tname_df.empty
                else f"Tenant {tenant_id}"
            )

            self.row_count = len(df)
            # Convert to JSON-serializable dicts; convert NaT/nan to None
            self.report_rows = [
                {k: (None if (isinstance(v, float) and pd.isna(v)) else str(v) if not isinstance(v, (int, float, bool, type(None))) else v)
                 for k, v in row.items()}
                for row in df.to_dict(orient="records")
            ]

            if self.include_log:
                self.log_text = _communications_log_text(self.report_rows)

            self.generated = True

        except Exception as ex:
            self.error_msg = f"Error generating report: {ex}"
        finally:
            self.loading = False

    def download_csv(self):
        if not self.report_rows:
            return
        df = pd.DataFrame(self.report_rows)
        csv_str = df.to_csv(index=False)
        b64 = base64.b64encode(csv_str.encode("utf-8")).decode()
        filename = f"tenant_{self._resolve_tenant_id()}_communications_report.csv"
        return rx.download(data=f"data:text/csv;base64,{b64}", filename=filename)

    def download_txt(self):
        if not self.log_text:
            return
        b64 = base64.b64encode(self.log_text.encode("utf-8")).decode()
        filename = f"tenant_{self._resolve_tenant_id()}_communications_report.txt"
        return rx.download(data=f"data:text/plain;base64,{b64}", filename=filename)

    def download_pdf(self):
        if not self.report_rows:
            return
        date_range = f"{self.start_date} to {self.end_date}"
        pdf_bytes = _communications_pdf_bytes(
            self.report_rows,
            tenant_name=self.tenant_name,
            date_range_text=date_range,
        )
        b64 = base64.b64encode(pdf_bytes).decode()
        filename = f"tenant_{self._resolve_tenant_id()}_communications_report.pdf"
        return rx.download(data=f"data:application/pdf;base64,{b64}", filename=filename)

    def _resolve_tenant_id(self) -> Optional[int]:
        """Match selected label back to a tenant ID."""
        try:
            idx = self.tenant_options.index(self.selected_tenant_label)
            return self.tenant_ids[idx]
        except (ValueError, IndexError):
            return None

    # Computed vars for the results table columns
    @rx.var
    def table_rows(self) -> list[dict]:
        """Slim down to display columns only."""
        display_cols = [
            "CommDate_display", "Method", "Subject", "Outcome",
            "NextActionDate_display", "TemplateName", "Notes",
        ]
        result = []
        for row in self.report_rows:
            slim = {c: str(row.get(c) or "") for c in display_cols}
            result.append(slim)
        return result

    @rx.var
    def has_rows(self) -> bool:
        return len(self.report_rows) > 0

    @rx.var
    def has_log(self) -> bool:
        return bool(self.log_text)

    @rx.var
    def date_range_label(self) -> str:
        return f"{self.start_date} to {self.end_date}"


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

def _filter_bar() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text("Tenant", size="1", color="gray"),
            rx.cond(
                CommReportState.tenant_options.length() > 0,
                rx.select(
                    CommReportState.tenant_options,
                    value=CommReportState.selected_tenant_label,
                    on_change=CommReportState.set_tenant,
                    width="280px",
                ),
                rx.text("Loading tenants…", color="gray", size="2"),
            ),
            spacing="1",
            align="start",
        ),
        rx.vstack(
            rx.text("Start date", size="1", color="gray"),
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
            rx.text("End date", size="1", color="gray"),
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
            rx.text("Options", size="1", color="gray"),
            rx.hstack(
                rx.checkbox(
                    checked=CommReportState.include_log,
                    on_change=CommReportState.toggle_include_log,
                ),
                rx.text("Include plain-text log", size="2"),
                align="center",
                spacing="2",
            ),
            spacing="1",
            align="start",
            justify="end",
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
        width="100%",
    )


def _results_table() -> rx.Component:
    """Render the communications table."""
    col_headers = ["Date", "Method", "Subject", "Outcome", "Next Action", "Template", "Notes"]

    header_cells = [
        rx.table.column_header_cell(
            col,
            style={"font_size": "12px", "font_weight": "600", "color": "#4A63A8"},
        )
        for col in col_headers
    ]

    col_keys = [
        "CommDate_display", "Method", "Subject", "Outcome",
        "NextActionDate_display", "TemplateName", "Notes",
    ]

    def _row(row: dict) -> rx.Component:
        return rx.table.row(
            *[
                rx.table.cell(
                    rx.text(row[k], size="1", style={"white_space": "pre-wrap", "max_width": "200px"}),
                )
                for k in col_keys
            ],
            style={"vertical_align": "top"},
            _hover={"background": "#F0F4FF"},
        )

    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(*header_cells)),
            rx.table.body(rx.foreach(CommReportState.table_rows, _row)),
            width="100%",
        ),
        overflow_x="auto",
        width="100%",
        border="1px solid #E2E8F0",
        border_radius="6px",
    )


def _download_bar() -> rx.Component:
    return rx.hstack(
        rx.button(
            "⬇ Download CSV",
            on_click=CommReportState.download_csv,
            variant="outline",
            color_scheme="blue",
            size="2",
        ),
        rx.cond(
            CommReportState.include_log & CommReportState.has_log,
            rx.button(
                "⬇ Download TXT Log",
                on_click=CommReportState.download_txt,
                variant="outline",
                color_scheme="blue",
                size="2",
            ),
        ),
        rx.cond(
            CommReportState.has_rows,
            rx.button(
                "⬇ Download PDF",
                on_click=CommReportState.download_pdf,
                variant="outline",
                color_scheme="blue",
                size="2",
            ),
        ),
        spacing="3",
        wrap="wrap",
    )


def _log_panel() -> rx.Component:
    return rx.cond(
        CommReportState.include_log & CommReportState.has_log,
        rx.vstack(
            rx.text("Plain-text log", size="2", weight="bold", color="#4A63A8"),
            rx.text_area(
                value=CommReportState.log_text,
                read_only=True,
                height="320px",
                width="100%",
                font_family="monospace",
                font_size="12px",
                style={"background": "#F8FAFC", "border": "1px solid #CBD5E0"},
            ),
            spacing="2",
            width="100%",
        ),
    )


def _results_section() -> rx.Component:
    return rx.cond(
        CommReportState.generated,
        rx.vstack(
            rx.hstack(
                rx.text(
                    f"Results for {CommReportState.tenant_name}",
                    size="3",
                    weight="bold",
                    color="#2F4C97",
                ),
                rx.badge(
                    CommReportState.row_count.to_string() + " records",
                    color_scheme="blue",
                    variant="soft",
                ),
                rx.text(CommReportState.date_range_label, size="2", color="gray"),
                spacing="3",
                align="center",
            ),
            _download_bar(),
            rx.cond(
                CommReportState.has_rows,
                _results_table(),
                rx.callout(
                    "No communications found for this tenant in the selected date range.",
                    icon="info",
                    color_scheme="gray",
                ),
            ),
            _log_panel(),
            spacing="4",
            width="100%",
        ),
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@rx.page(route="/communications-report", on_load=CommReportState.on_load)
def communications_report_page() -> rx.Component:
    return rx.vstack(
        # Header
        rx.hstack(
            rx.heading("Communications Report", size="5", color="#2F4C97"),
            justify="between",
            width="100%",
        ),

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

        # Filters
        rx.box(
            _filter_bar(),
            background="#F8FAFC",
            border="1px solid #E2E8F0",
            border_radius="8px",
            padding="16px",
            width="100%",
        ),

        # Results
        _results_section(),

        spacing="5",
        padding="24px",
        width="100%",
        align="start",
    )
