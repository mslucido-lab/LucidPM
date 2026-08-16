"""
Communications Hub page — live IMAP inbox plus tenant communication history.

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
    AppState, run_query, run_exec, decrypt_value,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES,
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




def _fetch_imap_inbox(db: str, max_messages: int = 50) -> list[dict]:
    """Connect to IMAP and fetch recent messages from INBOX."""
    import email as email_lib
    import email.utils as email_utils
    import imaplib
    import ssl
    from email.header import decode_header

    rows = run_query(
        "SELECT TOP 1 IMAPServer, IMAPPort, Username, EmailAddress, PasswordEncrypted "
        "FROM dbo.EmailConfig WHERE IsActive = 1",
        db=db,
    )
    if not rows:
        raise RuntimeError("Email is not configured. Go to Admin Settings to set up email.")

    cfg = rows[0]
    imap_server = str(cfg.get("IMAPServer") or "").strip()
    imap_port = int(cfg.get("IMAPPort") or 993)
    username = str(cfg.get("Username") or "").strip() or str(cfg.get("EmailAddress") or "").strip()
    password_enc = str(cfg.get("PasswordEncrypted") or "").strip()

    if not imap_server or not username or not password_enc:
        raise RuntimeError("Email credentials are incomplete. Go to Admin Settings.")

    password = decrypt_value(password_enc, db)
    if not password:
        raise RuntimeError("Saved email password could not be decrypted.")

    def _decode_header_str(value) -> str:
        if not value:
            return ""
        parts = decode_header(str(value))
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return "".join(decoded)

    def _extract_body(msg) -> str:
        if msg.is_multipart():
            html_fallback = ""
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition") or "")
                if "attachment" in disposition.lower():
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    text_value = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
                if content_type == "text/plain":
                    return text_value
                if content_type == "text/html" and not html_fallback:
                    html_fallback = text_value
            return html_fallback
        try:
            payload = msg.get_payload(decode=True)
            if payload is None:
                return str(msg.get_payload() or "")
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            return ""

    imap = None
    ssl_error = None
    try:
        ctx = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL(imap_server, imap_port, ssl_context=ctx)
    except Exception as ex:
        ssl_error = ex
        try:
            imap = imaplib.IMAP4(imap_server, 143)
        except Exception as plain_ex:
            raise RuntimeError(f"IMAP connection failed. SSL: {ssl_error} | Plain 143: {plain_ex}")

    try:
        imap.login(username, password)
        imap.select("INBOX", readonly=True)
        status, data = imap.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("IMAP search failed.")
        uids = data[0].split() if data and data[0] else []
        uids = list(reversed(uids[-max_messages:]))
        messages = []
        for uid in uids:
            try:
                status, msg_data = imap.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                from_raw = _decode_header_str(msg.get("From", ""))
                from_name, from_addr = email_utils.parseaddr(from_raw)
                subject = _decode_header_str(msg.get("Subject", "(No subject)")) or "(No subject)"
                date_str = str(msg.get("Date", ""))
                body = _extract_body(msg)
                body = str(body or "")
                snippet = body[:120].replace("\n", " ").replace("\r", " ").strip()
                messages.append({
                    "uid": uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
                    "from_address": str(from_addr or "").lower().strip(),
                    "from_name": str(from_name or from_addr or "").strip(),
                    "subject": str(subject or "(No subject)"),
                    "date_str": date_str,
                    "snippet": snippet,
                    "body": body,
                })
            except Exception:
                continue
        return messages
    finally:
        try:
            imap.logout()
        except Exception:
            pass

# ── State ─────────────────────────────────────────────────────────────────────

class CommunicationsState(AppState):

    # Tab control
    active_tab: str = "inbox"

    # Inbox
    inbox_messages: list[dict] = []
    inbox_loading: bool = False
    inbox_error: str = ""
    last_refreshed_at: str = ""
    selected_message_uid: str = ""
    selected_message: dict = {}

    # Tenant matching
    inbox_tenant_names: list[str] = []
    inbox_tenant_ids: list[int] = []
    log_tenant_name: str = ""
    log_tenant_id: int = 0
    log_success: str = ""
    log_error: str = ""
    email_not_configured: bool = False

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

    # Log Entry tab
    log_entry_tenant_label: str = ""
    log_entry_date: str = ""
    log_entry_method: str = "Email"
    log_entry_subject: str = ""
    log_entry_body: str = ""
    log_entry_outcome: str = ""
    log_entry_next_action: str = ""
    log_entry_error: str = ""
    log_entry_success: str = ""
    log_entry_saving: bool = False

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
        self._load_inbox_tenant_options()
        self.log_entry_date = dt.date.today().isoformat()
        self.log_entry_tenant_label = self.tenant_labels[0] if self.tenant_labels else ""

    def reload_on_db_change(self):
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.error_msg = ""
        self._load_tenants()
        self._load_inbox_tenant_options()
        self.log_entry_tenant_label = self.tenant_labels[0] if self.tenant_labels else ""
        self.log_entry_date = dt.date.today().isoformat()

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

    # ── Inbox event handlers ─────────────────────────────────────────────────────

    def set_active_tab(self, tab: str):
        self.active_tab = tab

    @rx.var
    def minutes_since_refresh(self) -> int:
        if not self.last_refreshed_at:
            return -1
        try:
            last = dt.datetime.fromisoformat(self.last_refreshed_at)
            delta = dt.datetime.now() - last
            return int(delta.total_seconds() // 60)
        except Exception:
            return -1

    @rx.var
    def refresh_status_text(self) -> str:
        mins = self.minutes_since_refresh
        if mins == -1:
            return "Inbox not yet loaded."
        if mins == 0:
            return "Refreshed just now."
        suffix = "" if mins == 1 else "s"
        return f"Last refreshed {mins} minute{suffix} ago."

    @rx.var
    def refresh_is_stale(self) -> bool:
        mins = self.minutes_since_refresh
        return mins >= 10

    @rx.var
    def inbox_tenant_options(self) -> list[str]:
        return self.inbox_tenant_names

    def _load_inbox_tenant_options(self):
        try:
            rows = run_query(
                "SELECT t.TenantID, t.TenantName "
                "FROM dbo.Tenants t "
                "LEFT JOIN dbo.TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
                "WHERE ISNULL(s.TenantStatusName, '') IN ('Active', 'Month-to-Month', 'Default') "
                "OR s.TenantStatusName IS NULL "
                "ORDER BY t.TenantName",
                db=self.db,
            )
            self.inbox_tenant_names = [str(r.get("TenantName") or "") for r in rows]
            self.inbox_tenant_ids = [int(r.get("TenantID") or 0) for r in rows]
            if self.inbox_tenant_names and self.log_tenant_name not in self.inbox_tenant_names:
                self.log_tenant_name = self.inbox_tenant_names[0]
                self.log_tenant_id = self.inbox_tenant_ids[0]
        except Exception as ex:
            self.inbox_tenant_names = []
            self.inbox_tenant_ids = []
            self.log_tenant_name = ""
            self.log_tenant_id = 0
            self.log_error = f"Could not load tenants: {ex}"

    def refresh_inbox(self):
        self.inbox_loading = True
        self.inbox_error = ""
        self.log_success = ""
        self.log_error = ""
        self.selected_message_uid = ""
        self.selected_message = {}

        try:
            cfg_rows = run_query(
                "SELECT TOP 1 PasswordEncrypted FROM dbo.EmailConfig WHERE IsActive = 1",
                db=self.db,
            )
            if not cfg_rows or not cfg_rows[0].get("PasswordEncrypted"):
                self.email_not_configured = True
                self.inbox_messages = []
                self.inbox_loading = False
                return
            self.email_not_configured = False
            self.inbox_messages = _fetch_imap_inbox(db=self.db, max_messages=50)
            self.last_refreshed_at = dt.datetime.now().isoformat()
        except Exception as ex:
            self.inbox_error = f"Could not load inbox: {ex}"
            self.inbox_messages = []
        finally:
            self.inbox_loading = False

        self._load_inbox_tenant_options()

    def select_inbox_message(self, uid: str):
        self.selected_message_uid = uid
        self.log_success = ""
        self.log_error = ""
        matches = [m for m in self.inbox_messages if str(m.get("uid") or "") == str(uid)]
        if not matches:
            self.selected_message = {}
            return
        msg = matches[0]
        from_addr = str(msg.get("from_address") or "").lower().strip()
        matched_name = ""
        matched_id = 0
        if from_addr:
            tenant_rows = run_query(
                "SELECT TOP 1 t.TenantID, t.TenantName "
                "FROM dbo.Tenants t "
                "INNER JOIN dbo.Contacts c ON c.TenantID = t.TenantID "
                "WHERE LOWER(ISNULL(c.Email1, '')) = ? OR LOWER(ISNULL(c.Email2, '')) = ?",
                (from_addr, from_addr),
                db=self.db,
            )
            if tenant_rows:
                matched_name = str(tenant_rows[0].get("TenantName") or "")
                matched_id = int(tenant_rows[0].get("TenantID") or 0)
        selected = dict(msg)
        selected["matched_tenant_name"] = matched_name
        selected["matched_tenant_id"] = matched_id
        self.selected_message = selected
        if matched_name and matched_name in self.inbox_tenant_names:
            self.log_tenant_name = matched_name
            self.log_tenant_id = matched_id

    def set_log_tenant(self, name: str):
        self.log_tenant_name = name
        if name in self.inbox_tenant_names:
            idx = self.inbox_tenant_names.index(name)
            self.log_tenant_id = self.inbox_tenant_ids[idx]

    def log_message_to_tenant(self):
        self.log_error = ""
        self.log_success = ""
        if not self.selected_message:
            self.log_error = "No message selected."
            return
        if not self.log_tenant_id or self.log_tenant_id <= 0:
            self.log_error = "Select a tenant to log this message to."
            return

        subject = str(self.selected_message.get("subject") or "(No subject)").strip()
        body = str(self.selected_message.get("body") or "").strip()
        from_address = str(self.selected_message.get("from_address") or "").strip()

        try:
            # Communications schema differs between DB versions. Build the insert
            # from the columns that actually exist so older DBs without Body/FromTo
            # still log the inbound email into Notes.
            col_rows = run_query(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
                db=self.db,
            )
            available = {str(r.get("COLUMN_NAME") or "") for r in col_rows}

            prop_rows = run_query(
                "SELECT PropertyID FROM dbo.Tenants WHERE TenantID = ?",
                (int(self.log_tenant_id),),
                db=self.db,
            )
            prop_id = int(prop_rows[0].get("PropertyID")) if prop_rows and prop_rows[0].get("PropertyID") else None

            columns = ["TenantID", "CommDate", "Method"]
            values_sql = ["?", "SYSDATETIME()", "?"]
            params = [int(self.log_tenant_id), "Email"]

            if "Subject" in available:
                columns.append("Subject")
                values_sql.append("?")
                params.append(subject)

            if "Body" in available:
                columns.append("Body")
                values_sql.append("?")
                params.append(body)

            if "FromTo" in available:
                columns.append("FromTo")
                values_sql.append("?")
                params.append(from_address)

            if "Outcome" in available:
                columns.append("Outcome")
                values_sql.append("?")
                params.append("Received")

            if "PropertyID" in available:
                columns.append("PropertyID")
                values_sql.append("?")
                params.append(prop_id)

            if "Notes" in available:
                note_parts = []
                if from_address and "FromTo" not in available:
                    note_parts.append(f"From: {from_address}")
                if body and "Body" not in available:
                    note_parts.append(body)
                if note_parts:
                    columns.append("Notes")
                    values_sql.append("?")
                    params.append("\n\n".join(note_parts))

            sql = (
                "INSERT INTO dbo.Communications ("
                + ", ".join(f"[{c}]" for c in columns)
                + ") VALUES ("
                + ", ".join(values_sql)
                + ")"
            )
            run_exec(sql, tuple(params), db=self.db)
            self.log_success = f"Logged to {self.log_tenant_name}."
        except Exception as ex:
            self.log_error = f"Log failed: {ex}"

    # ── Log Entry event handlers ─────────────────────────────────────────────────

    def set_log_entry_tenant(self, label: str):
        self.log_entry_tenant_label = label

    def set_log_entry_date(self, v: str):
        self.log_entry_date = v

    def set_log_entry_method(self, v: str):
        self.log_entry_method = v

    def set_log_entry_subject(self, v: str):
        self.log_entry_subject = v

    def set_log_entry_body(self, v: str):
        self.log_entry_body = v

    def set_log_entry_outcome(self, v: str):
        self.log_entry_outcome = v

    def set_log_entry_next_action(self, v: str):
        self.log_entry_next_action = v

    def save_log_entry(self):
        """Validate and insert a manual comm log entry."""
        self.log_entry_error = ""
        self.log_entry_success = ""

        if not self.log_entry_tenant_label or self.log_entry_tenant_label not in self.tenant_labels:
            self.log_entry_error = "Please select a tenant."
            return
        if not self.log_entry_date.strip():
            self.log_entry_error = "Date is required."
            return
        if not self.log_entry_method.strip():
            self.log_entry_error = "Method is required."
            return
        if not self.log_entry_subject.strip() and not self.log_entry_body.strip():
            self.log_entry_error = "Enter a subject or body."
            return

        try:
            idx = self.tenant_labels.index(self.log_entry_tenant_label)
            tenant_id = int(self.tenant_ids_str[idx])
        except (ValueError, IndexError):
            self.log_entry_error = "Could not resolve tenant."
            return

        try:
            comm_date = dt.datetime.fromisoformat(self.log_entry_date)
        except Exception:
            self.log_entry_error = "Invalid date format."
            return

        next_action = None
        if self.log_entry_next_action.strip():
            try:
                next_action = dt.datetime.fromisoformat(self.log_entry_next_action.strip())
            except Exception:
                self.log_entry_error = "Invalid next action date format."
                return

        prop_rows = run_query(
            "SELECT PropertyID FROM dbo.Tenants WHERE TenantID = ?",
            (tenant_id,),
            db=self.db,
        )
        prop_id = int(prop_rows[0]["PropertyID"]) if prop_rows and prop_rows[0].get("PropertyID") else None

        self.log_entry_saving = True
        try:
            col_rows = run_query(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
                db=self.db,
            )
            available = {str(r.get("COLUMN_NAME") or "") for r in col_rows}

            columns = ["TenantID", "CommDate", "Method"]
            values_sql = ["?", "?", "?"]
            params = [tenant_id, comm_date, self.log_entry_method.strip()]

            if "Subject" in available and self.log_entry_subject.strip():
                columns.append("Subject")
                values_sql.append("?")
                params.append(self.log_entry_subject.strip())

            if "Body" in available and self.log_entry_body.strip():
                columns.append("Body")
                values_sql.append("?")
                params.append(self.log_entry_body.strip())
            elif "Notes" in available and self.log_entry_body.strip():
                columns.append("Notes")
                values_sql.append("?")
                params.append(self.log_entry_body.strip())

            if "Outcome" in available and self.log_entry_outcome.strip():
                columns.append("Outcome")
                values_sql.append("?")
                params.append(self.log_entry_outcome.strip())

            if "NextActionDate" in available and next_action is not None:
                columns.append("NextActionDate")
                values_sql.append("?")
                params.append(next_action)

            if "PropertyID" in available and prop_id is not None:
                columns.append("PropertyID")
                values_sql.append("?")
                params.append(prop_id)

            col_str = ", ".join(f"[{c}]" for c in columns)
            val_str = ", ".join(values_sql)
            run_exec(
                f"INSERT INTO dbo.Communications ({col_str}) VALUES ({val_str})",
                tuple(params),
                db=self.db,
            )

            self.log_entry_tenant_label = self.tenant_labels[0] if self.tenant_labels else ""
            self.log_entry_date = dt.date.today().isoformat()
            self.log_entry_method = "Email"
            self.log_entry_subject = ""
            self.log_entry_body = ""
            self.log_entry_outcome = ""
            self.log_entry_next_action = ""
            self.log_entry_success = "Communication logged successfully."

        except Exception as ex:
            self.log_entry_error = f"Save failed: {ex}"
        finally:
            self.log_entry_saving = False

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




def inbox_message_row(msg: dict) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(msg["from_name"], size="2", weight="bold", color=BRAND_DARK),
                rx.spacer(),
                rx.text(msg["date_str"], size="1", color="#999"),
                width="100%",
            ),
            rx.text(msg["subject"], size="2", color="#333"),
            rx.text(
                msg["snippet"],
                size="1",
                color="#888",
                overflow="hidden",
                white_space="nowrap",
                text_overflow="ellipsis",
                max_width="340px",
            ),
            spacing="0",
            width="100%",
        ),
        padding="10px 12px",
        border_radius="8px",
        border="1px solid #E5E7EB",
        cursor="pointer",
        on_click=CommunicationsState.select_inbox_message(msg["uid"]),
        background=rx.cond(
            CommunicationsState.selected_message_uid == msg["uid"],
            "#EEF2FF",
            "white",
        ),
        width="100%",
    )


def inbox_message_detail() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.text(
                CommunicationsState.selected_message["subject"],
                size="4",
                weight="bold",
                color=BRAND_DARK,
            ),
            rx.hstack(
                rx.text("From:", size="2", color="#555", weight="medium"),
                rx.text(CommunicationsState.selected_message["from_name"], size="2"),
                rx.text(CommunicationsState.selected_message["from_address"], size="2", color="#888"),
                spacing="2",
            ),
            rx.text(CommunicationsState.selected_message["date_str"], size="2", color="#888"),
            spacing="1",
            width="100%",
        ),
        rx.divider(),
        rx.box(
            rx.text(
                CommunicationsState.selected_message["body"],
                size="2",
                white_space="pre-wrap",
            ),
            max_height="300px",
            overflow_y="auto",
            width="100%",
            padding="8px",
            background="#F9FAFB",
            border_radius="6px",
        ),
        rx.divider(),
        rx.vstack(
            rx.cond(
                CommunicationsState.selected_message["matched_tenant_name"] != "",
                rx.callout.root(
                    rx.callout.text(
                        rx.hstack(
                            rx.text("Matched tenant:", size="2", weight="medium"),
                            rx.text(
                                CommunicationsState.selected_message["matched_tenant_name"],
                                size="2",
                                color=BRAND_DARK,
                                weight="bold",
                            ),
                            spacing="2",
                        )
                    ),
                    color_scheme="green",
                    width="100%",
                ),
                rx.callout.root(
                    rx.callout.text("No tenant match found for this sender address."),
                    color_scheme="amber",
                    width="100%",
                ),
            ),
            rx.hstack(
                rx.text("Log to tenant:", size="2", color="#555", weight="medium"),
                rx.cond(
                    CommunicationsState.inbox_tenant_options.length() > 0,
                    rx.select(
                        CommunicationsState.inbox_tenant_options,
                        value=CommunicationsState.log_tenant_name,
                        on_change=CommunicationsState.set_log_tenant,
                    ),
                    rx.text("No tenant options loaded.", size="2", color="#888"),
                ),
                rx.button(
                    "Log to Comm Log",
                    on_click=CommunicationsState.log_message_to_tenant,
                    color_scheme="blue",
                    size="2",
                ),
                align="center",
                spacing="3",
                wrap="wrap",
            ),
            rx.cond(
                CommunicationsState.log_success != "",
                rx.callout.root(
                    rx.callout.text(CommunicationsState.log_success),
                    color_scheme="green",
                    width="100%",
                ),
                rx.fragment(),
            ),
            rx.cond(
                CommunicationsState.log_error != "",
                rx.callout.root(
                    rx.callout.text(CommunicationsState.log_error),
                    color_scheme="red",
                    width="100%",
                ),
                rx.fragment(),
            ),
            width="100%",
            spacing="3",
        ),
        width="100%",
        flex="1",
        spacing="3",
        padding="16px",
        border="1px solid #E5E7EB",
        border_radius="8px",
    )


def inbox_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.button(
                "Refresh Inbox",
                on_click=CommunicationsState.refresh_inbox,
                loading=CommunicationsState.inbox_loading,
                color_scheme="blue",
                variant="outline",
            ),
            rx.vstack(
                rx.text(CommunicationsState.refresh_status_text, size="2", color="#666"),
                rx.cond(
                    CommunicationsState.refresh_is_stale,
                    rx.text(
                        "⚠️ Inbox may be out of date. Click Refresh to update.",
                        size="2",
                        color="#C78A35",
                        weight="medium",
                    ),
                    rx.fragment(),
                ),
                spacing="0",
            ),
            align="center",
            spacing="4",
            width="100%",
        ),
        rx.callout.root(
            rx.callout.text(
                "Inbox does not auto-refresh. Click Refresh to check for new messages.",
                size="2",
            ),
            color_scheme="blue",
            width="100%",
        ),
        rx.cond(
            CommunicationsState.email_not_configured,
            rx.callout.root(
                rx.callout.text("Email is not configured. Go to Admin Settings > Email Configuration."),
                color_scheme="red",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.inbox_error != "",
            rx.callout.root(
                rx.callout.text(CommunicationsState.inbox_error),
                color_scheme="red",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.inbox_messages.length() == 0,
            rx.cond(
                CommunicationsState.last_refreshed_at != "",
                rx.text("No messages found.", size="2", color="#888"),
                rx.text("Click Refresh to load your inbox.", size="2", color="#888"),
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.inbox_messages.length() > 0,
            rx.hstack(
                rx.vstack(
                    rx.foreach(CommunicationsState.inbox_messages, inbox_message_row),
                    width="380px",
                    spacing="1",
                    overflow_y="auto",
                    max_height="600px",
                ),
                rx.cond(
                    CommunicationsState.selected_message_uid != "",
                    inbox_message_detail(),
                    rx.box(
                        rx.text("Select a message to view.", size="2", color="#888"),
                        padding="2rem",
                        border="1px solid #E5E7EB",
                        border_radius="8px",
                        flex="1",
                    ),
                ),
                width="100%",
                align="start",
                spacing="4",
            ),
            rx.fragment(),
        ),
        width="100%",
        spacing="4",
        align_items="start",
    )

def log_entry_tab() -> rx.Component:
    return rx.vstack(
        rx.text(
            "Manually log any communication: call, email, text, in-person, or other. "
            "Paste email text directly into the Body field.",
            size="2",
            color="#666",
        ),
        rx.cond(
            CommunicationsState.log_entry_success != "",
            rx.callout.root(
                rx.callout.text(CommunicationsState.log_entry_success),
                color_scheme="green",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.log_entry_error != "",
            rx.callout.root(
                rx.callout.text(CommunicationsState.log_entry_error),
                color_scheme="red",
                width="100%",
            ),
            rx.fragment(),
        ),
        rx.card(
            rx.vstack(
                rx.vstack(
                    rx.text("Tenant", size="2", color="#555", weight="medium"),
                    rx.cond(
                        CommunicationsState.tenant_labels.length() > 0,
                        rx.select(
                            CommunicationsState.tenant_labels,
                            value=CommunicationsState.log_entry_tenant_label,
                            on_change=CommunicationsState.set_log_entry_tenant,
                            width="100%",
                        ),
                        rx.text("No tenants loaded.", size="2", color="#888"),
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Date", size="2", color="#555", weight="medium"),
                        rx.input(
                            type="date",
                            value=CommunicationsState.log_entry_date,
                            on_change=CommunicationsState.set_log_entry_date,
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Method", size="2", color="#555", weight="medium"),
                        rx.select(
                            METHOD_CHOICES,
                            value=CommunicationsState.log_entry_method,
                            on_change=CommunicationsState.set_log_entry_method,
                            width="100%",
                        ),
                        spacing="1",
                        width="200px",
                    ),
                    width="100%",
                    spacing="4",
                    align="end",
                ),
                rx.vstack(
                    rx.text("Subject", size="2", color="#555", weight="medium"),
                    rx.input(
                        value=CommunicationsState.log_entry_subject,
                        on_change=CommunicationsState.set_log_entry_subject,
                        placeholder="Subject or brief description",
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Body / Message", size="2", color="#555", weight="medium"),
                    rx.text(
                        "Paste email text, call notes, or any communication content here.",
                        size="1",
                        color="#999",
                    ),
                    rx.text_area(
                        value=CommunicationsState.log_entry_body,
                        on_change=CommunicationsState.set_log_entry_body,
                        placeholder="Paste or type communication content...",
                        rows="10",
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Outcome", size="2", color="#555", weight="medium"),
                        rx.input(
                            value=CommunicationsState.log_entry_outcome,
                            on_change=CommunicationsState.set_log_entry_outcome,
                            placeholder="e.g. Resolved, Follow-up needed",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Next Action Date", size="2", color="#555", weight="medium"),
                        rx.input(
                            type="date",
                            value=CommunicationsState.log_entry_next_action,
                            on_change=CommunicationsState.set_log_entry_next_action,
                            width="100%",
                        ),
                        spacing="1",
                        width="200px",
                    ),
                    width="100%",
                    spacing="4",
                    align="end",
                ),
                rx.hstack(
                    rx.button(
                        "Save to Comm Log",
                        on_click=CommunicationsState.save_log_entry,
                        loading=CommunicationsState.log_entry_saving,
                        color_scheme="blue",
                        size="2",
                    ),
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        width="100%",
        spacing="4",
        align_items="start",
    )


# ── Page content ──────────────────────────────────────────────────────────────

def tenant_communications_tab() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Heading
            rx.heading("Tenant Communications", size="5", color=BRAND_DARK),

            # Error banner
            rx.cond(
                CommunicationsState.error_msg != "",
                rx.callout(
                    CommunicationsState.error_msg,
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
                            CommunicationsState.tenant_labels.length() > 0,
                            rx.select(
                                CommunicationsState.tenant_labels,
                                value=CommunicationsState.selected_tenant_label,
                                on_change=CommunicationsState.set_tenant,
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
                            value=CommunicationsState.start_date,
                            on_change=CommunicationsState.set_start_date,
                            type="date",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    # End date
                    rx.vstack(
                        rx.text("End date", size="1", color="#666"),
                        rx.input(
                            value=CommunicationsState.end_date,
                            on_change=CommunicationsState.set_end_date,
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
                                checked=CommunicationsState.include_log,
                                on_change=CommunicationsState.set_include_log,
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
                        rx.cond(CommunicationsState.loading, "Generating…", "Generate Report"),
                        on_click=CommunicationsState.generate_report,
                        disabled=CommunicationsState.loading,
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
                CommunicationsState.generated,
                rx.vstack(
                    # Summary row + downloads
                    rx.hstack(
                        rx.text(
                            CommunicationsState.tenant_name,
                            size="3",
                            weight="bold",
                            color=BRAND_DARK,
                        ),
                        rx.badge(
                            CommunicationsState.row_count.to_string() + " records",
                            color_scheme="blue",
                            variant="soft",
                        ),
                        rx.text(
                            CommunicationsState.start_date + " → " + CommunicationsState.end_date,
                            size="2",
                            color="#888",
                        ),
                        rx.spacer(),
                        # CSV download
                        rx.button(
                            "⬇ CSV",
                            on_click=CommunicationsState.download_csv,
                            variant="outline",
                            color_scheme="blue",
                            size="2",
                        ),
                        # TXT log download
                        rx.cond(
                            CommunicationsState.has_log,
                            rx.button(
                                "⬇ TXT Log",
                                on_click=CommunicationsState.download_txt,
                                variant="outline",
                                color_scheme="blue",
                                size="2",
                            ),
                            rx.fragment(),
                        ),
                        # PDF — same pattern as rent roll: link to FastAPI endpoint
                        rx.cond(
                            CommunicationsState.row_count > 0,
                            rx.link(
                                rx.button(
                                    "⬇ PDF",
                                    variant="outline",
                                    color_scheme="blue",
                                    size="2",
                                ),
                                href=CommunicationsState.pdf_url,
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
                        CommunicationsState.row_count > 0,
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
                                    rx.foreach(CommunicationsState.rows, comm_table_row)
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
                        CommunicationsState.has_log,
                        rx.vstack(
                            rx.text("Plain-text log", size="2", weight="bold", color=BRAND_PRIMARY),
                            rx.text_area(
                                value=CommunicationsState.log_text,
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


def communications_content() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("Communications", size="6", color=BRAND_DARK),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Inbox", value="inbox"),
                    rx.tabs.trigger("Tenant Communications", value="report"),
                    rx.tabs.trigger("Log Entry", value="log"),
                ),
                rx.tabs.content(inbox_tab(), value="inbox", padding_top="16px"),
                rx.tabs.content(tenant_communications_tab(), value="report", padding_top="16px"),
                rx.tabs.content(log_entry_tab(), value="log", padding_top="16px"),
                value=CommunicationsState.active_tab,
                on_change=CommunicationsState.set_active_tab,
                width="100%",
            ),
            width="100%",
            spacing="4",
            align_items="start",
        ),
        padding="24px",
        width="100%",
    )


def communications_page() -> rx.Component:
    return page_shell(communications_content(), current_path="/communications")
