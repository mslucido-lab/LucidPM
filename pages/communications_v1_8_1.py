"""
Communications Hub page — live IMAP inbox plus tenant communication history.

v1.8.1 — Sent Mail displays To recipient in list/detail and tenant matching uses recipient address for Sent Mail.

Layout:
  - Filter bar (tenant picker, start date, end date, include log checkbox)
  - Generate button
  - Results table (Date, Method, Subject, Outcome, Next Action, Property)
  - Downloads: CSV, plain-text log, PDF (via FastAPI endpoint)
"""

import base64
import datetime as dt
import io
import os
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import (
    AppState, run_query, run_exec, decrypt_value,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES,
)
from LucidPM_Reflex.components.sidebar import page_shell


DEFAULT_ATTACHMENT_FOLDER = r"C:\Dell Inspirion\TenantCRM\LeaseDocuments\Generated"


# Page width constant — dynamic sidebar width + page_shell padding (32px each side = 64px)
# Sidebar script updates --lucid-sidebar-width when resized
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"


INBOX_RESIZER_SCRIPT = """
(function() {
    function installInboxResizer() {
        if (window.__lucidInboxResizerCleanup) {
            try { window.__lucidInboxResizerCleanup(); } catch (e) {}
        }

        var isResizing = false;
        var startX = 0;
        var startWidth = 0;
        var leftPanel = null;

        function getResizerFromEvent(e) {
            var path = e.composedPath ? e.composedPath() : [];
            for (var i = 0; i < path.length; i++) {
                if (path[i] && path[i].id === 'inbox-panel-resizer') {
                    return path[i];
                }
            }
            var target = e.target;
            return target && target.closest ? target.closest('#inbox-panel-resizer') : null;
        }

        function startResize(e) {
            var resizer = getResizerFromEvent(e);
            if (!resizer) {
                return;
            }
            leftPanel = document.getElementById('inbox-message-list');
            if (!leftPanel) {
                return;
            }
            isResizing = true;
            startX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            startWidth = leftPanel.offsetWidth || 380;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            if (resizer.setPointerCapture && e.pointerId) {
                try { resizer.setPointerCapture(e.pointerId); } catch (err) {}
            }
            e.preventDefault();
            e.stopPropagation();
        }

        function moveResize(e) {
            if (!isResizing || !leftPanel) {
                return;
            }
            var clientX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
            var delta = clientX - startX;
            var newWidth = Math.min(Math.max(startWidth + delta, 240), 600);
            leftPanel.style.width = newWidth + 'px';
            leftPanel.style.minWidth = newWidth + 'px';
            leftPanel.style.maxWidth = newWidth + 'px';
            e.preventDefault();
        }

        function stopResize() {
            if (!isResizing) {
                return;
            }
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

        window.__lucidInboxResizerCleanup = function() {
            document.removeEventListener('pointerdown', startResize, true);
            document.removeEventListener('pointermove', moveResize, true);
            document.removeEventListener('pointerup', stopResize, true);
            document.removeEventListener('pointercancel', stopResize, true);
            document.removeEventListener('mousedown', startResize, true);
            document.removeEventListener('mousemove', moveResize, true);
            document.removeEventListener('mouseup', stopResize, true);
        };
    }

    // Install immediately in case elements already exist
    installInboxResizer();

    // Watch for inbox-message-list to appear in DOM after messages load
    var resizerObserver = new MutationObserver(function(mutations) {
        if (document.getElementById('inbox-message-list')) {
            installInboxResizer();
            resizerObserver.disconnect();
            resizerObserver = null;
        }
    });
    resizerObserver.observe(document.body, { childList: true, subtree: true });

    // Fallback timeouts in case MutationObserver misses it
    setTimeout(installInboxResizer, 500);
    setTimeout(installInboxResizer, 2000);
    setTimeout(installInboxResizer, 5000);
})();
"""

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




def _parse_subject_prefix(subject: str) -> tuple[str, str]:
    """Parse 'TENANT::Subject' convention.

    Returns (tenant_identifier, clean_subject).
    If no '::' found, returns ('', original_subject).
    """
    if "::" not in (subject or ""):
        return "", str(subject or "")
    parts = str(subject).split("::", 1)
    tenant_identifier = parts[0].strip()
    clean_subject = parts[1].strip()
    return tenant_identifier, clean_subject


def _match_tenant_by_name(identifier: str, db: str) -> tuple[str, int]:
    """Fuzzy match tenant identifier against TenantName."""
    if not identifier or not identifier.strip():
        return "", 0
    rows = run_query(
        "SELECT TOP 1 TenantID, TenantName FROM dbo.Tenants "
        "WHERE TenantName LIKE ? "
        "ORDER BY TenantName",
        (f"%{identifier.strip()}%",),
        db=db,
    )
    if rows:
        return str(rows[0]["TenantName"]), int(rows[0]["TenantID"])
    return "", 0

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




def _get_ai_config(db: str) -> tuple[str, str]:
    """Load API key and model from AIConfig."""
    rows = run_query(
        "SELECT TOP 1 APIKeyEncrypted, ModelName FROM dbo.AIConfig WHERE IsActive = 1",
        db=db,
    )
    if not rows or not rows[0].get("APIKeyEncrypted"):
        raise RuntimeError(
            "AI is not configured. Go to Admin Settings → AI Configuration."
        )
    api_key = decrypt_value(str(rows[0]["APIKeyEncrypted"]), db)
    model = str(rows[0].get("ModelName") or "claude-sonnet-4-6")
    return api_key, model


def _fetch_imap_inbox(db: str, max_messages: int = 50, folder: str = "INBOX") -> list[dict]:
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

    def _extract_images(msg) -> list[dict]:
        """Extract image attachments as base64 data URIs."""
        import base64 as b64
        images = []
        if not msg.is_multipart():
            return images

        for part in msg.walk():
            content_type = part.get_content_type()
            if not content_type.startswith("image/"):
                continue
            try:
                raw_data = part.get_payload(decode=True)
                if not raw_data or len(raw_data) < 30000:
                    continue
            except Exception:
                continue

            filename = part.get_filename() or f"image.{content_type.split('/')[-1]}"
            filename = _decode_header_str(filename)
            b64_data = b64.b64encode(raw_data).decode("utf-8")
            data_uri = f"data:{content_type};base64,{b64_data}"

            images.append({
                "filename": str(filename),
                "data_uri": data_uri,
                "content_type": str(content_type),
            })

        return images

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

        def _decode_mailbox_name(raw_item) -> str:
            text = raw_item.decode("utf-8", errors="replace") if isinstance(raw_item, bytes) else str(raw_item)
            if ' "/" ' in text:
                return text.rsplit(' "/" ', 1)[-1].strip().strip('"')
            if ' "." ' in text:
                return text.rsplit(' "." ', 1)[-1].strip().strip('"')
            return text.split()[-1].strip().strip('"') if text.split() else ""

        def _discover_sent_folders() -> list[str]:
            discovered = []
            try:
                status, boxes = imap.list()
                if status != "OK" or not boxes:
                    return discovered
                for item in boxes:
                    name = _decode_mailbox_name(item)
                    low = name.lower()
                    if "\\sent" in low or "sent" in low:
                        discovered.append(name)
            except Exception:
                pass
            return discovered

        folder_candidates = [folder]
        if str(folder) == "Sent Mail":
            folder_candidates = [
                "Sent Mail",
                "Sent",
                "Sent Items",
                "Sent Messages",
                "Sent Mailbox",
                "INBOX.Sent",
                "INBOX.Sent Mail",
                "[Gmail]/Sent Mail",
            ]
            for discovered in _discover_sent_folders():
                if discovered and discovered not in folder_candidates:
                    folder_candidates.append(discovered)

        selected = False
        select_errors = []
        for candidate in folder_candidates:
            mailbox = f'"{candidate}"' if " " in str(candidate) or "/" in str(candidate) else str(candidate)
            try:
                status, _ = imap.select(mailbox, readonly=True)
                if status == "OK":
                    selected = True
                    break
                select_errors.append(f"{candidate}: {status}")
            except Exception as ex:
                select_errors.append(f"{candidate}: {ex}")

        if not selected:
            discovered = _discover_sent_folders()
            extra = (" | discovered sent folders: " + ", ".join(discovered)) if discovered else " | no sent folders discovered by LIST"
            raise RuntimeError("IMAP folder select failed: " + " | ".join(select_errors) + extra)

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
                to_raw = _decode_header_str(msg.get("To", ""))
                from_name, from_addr = email_utils.parseaddr(from_raw)
                to_name, to_addr = email_utils.parseaddr(to_raw)
                is_sent_folder = str(folder or "").strip().lower() == "sent mail"
                display_name = to_name or to_addr if is_sent_folder else from_name or from_addr
                display_address = to_addr if is_sent_folder else from_addr
                display_label = "To" if is_sent_folder else "From"
                subject = _decode_header_str(msg.get("Subject", "(No subject)")) or "(No subject)"
                tenant_prefix, clean_subject = _parse_subject_prefix(subject)
                images = _extract_images(msg)
                date_str = str(msg.get("Date", ""))
                body = _extract_body(msg)
                body = str(body or "")
                snippet = body[:120].replace("\n", " ").replace("\r", " ").strip()
                messages.append({
                    "uid": uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
                    "from_address": str(from_addr or "").lower().strip(),
                    "from_name": str(from_name or from_addr or "").strip(),
                    "to_address": str(to_addr or "").lower().strip(),
                    "to_name": str(to_name or to_addr or "").strip(),
                    "display_name": str(display_name or "").strip(),
                    "display_address": str(display_address or "").lower().strip(),
                    "display_label": display_label,
                    "is_sent_folder": is_sent_folder,
                    "subject": str(clean_subject or "(No subject)"),
                    "raw_subject": str(subject or "(No subject)"),
                    "date_str": date_str,
                    "snippet": snippet,
                    "body": body,
                    "images": images,
                    "has_images": len(images) > 0,
                    "tenant_prefix": tenant_prefix,
                    "matched_tenant_name": "",
                    "matched_tenant_id": 0,
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
    inbox_folder: str = "INBOX"
    inbox_messages: list[dict] = []
    inbox_loading: bool = False
    inbox_error: str = ""
    last_refreshed_at: str = ""
    selected_message_uid: str = ""
    selected_message: dict = {}

    # Image viewer
    selected_message_images: list[dict] = []
    selected_image_index: int = 0

    # AI processing
    ai_processing: bool = False
    ai_result: str = ""
    ai_error: str = ""
    ai_processed_uid: str = ""

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
    log_entry_contact_names: list[str] = ["(No contact)"]
    log_entry_contact_ids: list[int] = [0]
    log_entry_contact_name: str = "(No contact)"
    log_entry_date: str = ""
    log_entry_method: str = "Email"
    log_entry_subject: str = ""
    log_entry_body: str = ""
    log_entry_outcome: str = ""
    log_entry_next_action: str = ""
    log_entry_error: str = ""
    log_entry_success: str = ""
    log_entry_saving: bool = False

    # Reply compose modal
    compose_email_open: bool = False
    compose_to: str = ""
    compose_subject: str = ""
    compose_body: str = ""
    compose_sending: bool = False
    compose_error: str = ""
    compose_success: str = ""
    compose_is_reply: bool = False

    # New email compose from Communications page
    compose_tenant_label: str = ""
    compose_contact_options: list[str] = []
    compose_contact_emails: list[str] = []
    compose_selected_contact: str = ""

    # Attachment picker
    attach_filenames: list[str] = []
    attach_file_bytes: list[bytes] = []

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
        self._load_log_entry_contacts()

    def reload_on_db_change(self):
        self.generated = False
        self.rows = []
        self.log_text = ""
        self.error_msg = ""
        self._load_tenants()
        self._load_inbox_tenant_options()
        self.log_entry_tenant_label = self.tenant_labels[0] if self.tenant_labels else ""
        self.log_entry_date = dt.date.today().isoformat()
        self._load_log_entry_contacts()

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

    def set_inbox_folder(self, folder: str):
        """Switch between INBOX and Sent Mail and refresh."""
        self.inbox_folder = folder
        self.inbox_messages = []
        self.selected_message_uid = ""
        self.selected_message = {}
        self.selected_message_images = []
        self.selected_image_index = 0
        self.ai_result = ""
        self.ai_error = ""
        self.ai_processed_uid = ""
        self.log_success = ""
        self.log_error = ""
        yield CommunicationsState.refresh_inbox

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
        self.selected_message_images = []
        self.selected_image_index = 0
        self.ai_result = ""
        self.ai_error = ""
        self.ai_processed_uid = ""

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
            self.inbox_messages = _fetch_imap_inbox(db=self.db, max_messages=50, folder=self.inbox_folder)
            self.last_refreshed_at = dt.datetime.now().isoformat()
        except Exception as ex:
            detail = str(ex) or repr(ex) or type(ex).__name__
            self.inbox_error = f"Could not load inbox: {type(ex).__name__}: {detail}"
            self.inbox_messages = []
        finally:
            self.inbox_loading = False

        self._load_inbox_tenant_options()

    def select_inbox_message(self, uid: str):
        self.selected_message_uid = uid
        self.log_success = ""
        self.log_error = ""
        self.selected_message_images = []
        self.selected_image_index = 0
        self.ai_result = ""
        self.ai_error = ""
        self.ai_processed_uid = ""

        matches = [m for m in self.inbox_messages if str(m.get("uid") or "") == str(uid)]
        if not matches:
            self.selected_message = {}
            return

        msg = dict(matches[0])
        tenant_prefix = str(msg.get("tenant_prefix") or "")
        matched_name = ""
        matched_id = 0

        if tenant_prefix:
            matched_name, matched_id = _match_tenant_by_name(tenant_prefix, self.db)

        if not matched_name:
            match_addr = str(
                msg.get("to_address") if bool(msg.get("is_sent_folder")) else msg.get("from_address")
            or "").lower().strip()
            if match_addr:
                tenant_rows = run_query(
                    "SELECT TOP 1 t.TenantID, t.TenantName "
                    "FROM dbo.Tenants t "
                    "INNER JOIN dbo.Contacts c ON c.TenantID = t.TenantID "
                    "WHERE LOWER(ISNULL(c.Email1, '')) = ? OR LOWER(ISNULL(c.Email2, '')) = ?",
                    (match_addr, match_addr),
                    db=self.db,
                )
                if tenant_rows:
                    matched_name = str(tenant_rows[0].get("TenantName") or "")
                    matched_id = int(tenant_rows[0].get("TenantID") or 0)

        msg["matched_tenant_name"] = matched_name
        msg["matched_tenant_id"] = matched_id
        self.selected_message = msg

        self.selected_message_images = list(msg.get("images") or [])
        self.selected_image_index = 0

        if matched_name and matched_name in self.inbox_tenant_names:
            self.log_tenant_name = matched_name
            idx = self.inbox_tenant_names.index(matched_name)
            self.log_tenant_id = self.inbox_tenant_ids[idx]

    def set_selected_image_index(self, idx: int):
        self.selected_image_index = idx

    def process_image_with_ai(self):
        """Send the selected message image to Claude vision API for analysis."""
        import anthropic

        self.ai_error = ""
        self.ai_result = ""
        self.ai_processing = True

        if not self.selected_message_images:
            self.ai_error = "No image attachment found in this message."
            self.ai_processing = False
            return

        if not self.selected_message_uid:
            self.ai_error = "No message selected."
            self.ai_processing = False
            return

        try:
            api_key, model = _get_ai_config(self.db)
        except RuntimeError as ex:
            self.ai_error = str(ex)
            self.ai_processing = False
            return

        img = self.selected_message_images[0]
        data_uri = str(img.get("data_uri") or "")
        content_type = str(img.get("content_type") or "image/jpeg")

        if ";base64," not in data_uri:
            self.ai_error = "Image format not supported."
            self.ai_processing = False
            return

        b64_data = data_uri.split(";base64,", 1)[1]

        system_prompt = (
            "You are a property management communications assistant. "
            "Your job is to read screenshots of text message or iMessage conversations "
            "and produce a concise, factual summary suitable for a legal comm log record. "
            "Focus on: what was communicated, any commitments or agreements made, "
            "dates or timeframes mentioned, and next steps. "
            "Write in third person, past tense. Be objective and factual. "
            "Do not include opinions, interpretations, or speculation. "
            "Format: 2-4 sentences maximum. Start with the approximate date if visible."
        )

        user_prompt = (
            "Please read this text message screenshot and produce a factual comm log entry summary."
        )

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": content_type,
                                    "data": b64_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": user_prompt,
                            },
                        ],
                    }
                ],
            )
            result_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    result_text += block.text
            self.ai_result = result_text.strip()
            self.ai_processed_uid = self.selected_message_uid

        except Exception as ex:
            self.ai_error = f"AI processing failed: {ex}"
        finally:
            self.ai_processing = False

    def set_ai_result(self, v: str):
        """Allow user to edit the AI result before sending to log entry."""
        self.ai_result = v

    def send_to_log_entry(self):
        """Pre-populate Log Entry tab with AI result and switch to that tab."""
        if not self.ai_result.strip():
            return

        self.log_entry_body = self.ai_result.strip()
        self.log_entry_method = "Text"
        self.log_entry_subject = str(self.selected_message.get("subject") or "")
        self.log_entry_error = ""
        self.log_entry_success = ""

        matched_name = str(self.selected_message.get("matched_tenant_name") or "")
        if matched_name:
            preferred_label = ""
            for label in self.tenant_labels:
                if label.startswith(matched_name + " (ID="):
                    preferred_label = label
                    break
            if preferred_label:
                self.log_entry_tenant_label = preferred_label
                self._load_log_entry_contacts()

        import datetime as dt
        self.log_entry_date = dt.date.today().isoformat()
        self.active_tab = "log"

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

    # ── Reply compose + attachment handlers ───────────────────────────────────────

    async def handle_attachment_upload(self, files: list[rx.UploadFile]):
        self.attach_filenames = []
        self.attach_file_bytes = []
        for f in files:
            data = await f.read()
            self.attach_filenames.append(f.filename)
            self.attach_file_bytes.append(data)

    def clear_attachments(self):
        self.attach_filenames = []
        self.attach_file_bytes = []

    def open_reply(self):
        """Open compose modal pre-populated from selected inbox message."""
        if not self.selected_message:
            return

        self.compose_error = ""
        self.compose_success = ""
        self.compose_sending = False
        self.compose_is_reply = True

        from_addr = str(self.selected_message.get("from_address") or "")
        subject = str(self.selected_message.get("subject") or "")

        self.compose_to = from_addr
        self.compose_subject = f"Re: {subject}" if subject and not subject.startswith("Re:") else subject
        self.compose_body = ""
        self.attach_filenames = []
        self.attach_file_bytes = []

        self.compose_email_open = True

    def close_compose_email(self):
        self.compose_email_open = False
        self.compose_error = ""
        self.compose_success = ""
        self.compose_sending = False
        self.compose_is_reply = False

    def set_compose_to(self, v: str):
        self.compose_to = v

    def set_compose_subject(self, v: str):
        self.compose_subject = v

    def set_compose_body(self, v: str):
        self.compose_body = v

    def send_compose_email(self):
        """Send reply and log to comm log when a tenant is selected."""
        from LucidPM_Reflex.state import send_email
        import tempfile, os

        if self.compose_sending:
            return

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

        self.compose_sending = True

        tmp_paths = []
        for name, data in zip(self.attach_filenames, self.attach_file_bytes):
            suffix = os.path.splitext(name)[-1] or ".pdf"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            named_path = os.path.join(os.path.dirname(tmp.name), name)
            os.rename(tmp.name, named_path)
            tmp_paths.append(named_path)

        try:
            send_email(
                to_address=self.compose_to.strip(),
                subject=self.compose_subject.strip(),
                body=self.compose_body.strip(),
                db=self.db,
                attachment_paths=tmp_paths or None,
            )
        except Exception as ex:
            self.compose_error = f"Failed to send: {ex}"
            self.compose_sending = False
            return
        finally:
            for p in tmp_paths:
                try:
                    os.unlink(p)
                except Exception:
                    pass

        if self.log_tenant_id and self.log_tenant_id > 0:
            try:
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
                prop_id = int(prop_rows[0]["PropertyID"]) if prop_rows and prop_rows[0].get("PropertyID") else None

                columns = ["TenantID", "CommDate", "Method"]
                values_sql = ["?", "SYSDATETIME()", "?"]
                params = [int(self.log_tenant_id), "Email"]

                if "Subject" in available:
                    columns.append("Subject"); values_sql.append("?")
                    params.append(self.compose_subject.strip())
                if "Body" in available:
                    columns.append("Body"); values_sql.append("?")
                    params.append(self.compose_body.strip())
                elif "Notes" in available:
                    columns.append("Notes"); values_sql.append("?")
                    params.append(self.compose_body.strip())
                if "FromTo" in available:
                    columns.append("FromTo"); values_sql.append("?")
                    params.append(self.compose_to.strip())
                if "Outcome" in available:
                    columns.append("Outcome"); values_sql.append("?")
                    params.append("Sent")
                if "PropertyID" in available and prop_id is not None:
                    columns.append("PropertyID"); values_sql.append("?")
                    params.append(prop_id)

                col_str = ", ".join(f"[{c}]" for c in columns)
                val_str = ", ".join(values_sql)
                run_exec(
                    f"INSERT INTO dbo.Communications ({col_str}) VALUES ({val_str})",
                    tuple(params),
                    db=self.db,
                )
            except Exception:
                pass

        self.compose_success = "Reply sent." + (f" Logged to {self.log_tenant_name}." if self.log_tenant_id > 0 else "")
        self.compose_sending = False
        self.compose_email_open = False

    def open_compose_new(self):
        """Open compose modal for new outbound email."""
        self.compose_error = ""
        self.compose_success = ""
        self.compose_subject = ""
        self.compose_body = ""
        self.compose_sending = False
        self.compose_is_reply = False
        self.compose_to = ""
        self.compose_contact_options = []
        self.compose_contact_emails = []
        self.compose_selected_contact = ""
        self.compose_tenant_label = self.tenant_labels[0] if self.tenant_labels else ""
        self.attach_filenames = []
        self.attach_file_bytes = []
        yield CommunicationsState.load_compose_contacts

    def set_compose_tenant(self, label: str):
        self.compose_tenant_label = label
        yield CommunicationsState.load_compose_contacts

    def load_compose_contacts(self):
        """Load contacts with emails for the selected compose tenant."""
        self.compose_contact_options = []
        self.compose_contact_emails = []
        self.compose_to = ""
        self.compose_selected_contact = ""

        if not self.compose_tenant_label or self.compose_tenant_label not in self.tenant_labels:
            self.compose_email_open = True
            return

        idx = self.tenant_labels.index(self.compose_tenant_label)
        tenant_id = int(self.tenant_ids_str[idx])

        rows = run_query(
            "SELECT FirstName, LastName, Email1, IsPrimary, ContactRole "
            "FROM dbo.Contacts "
            "WHERE TenantID = ? AND Email1 IS NOT NULL AND Email1 != '' "
            "ORDER BY IsPrimary DESC, LastName, FirstName",
            (tenant_id,),
            db=self.db,
        )

        options = []
        emails = []
        for r in rows:
            first = str(r.get("FirstName") or "").strip()
            last = str(r.get("LastName") or "").strip()
            email = str(r.get("Email1") or "").strip()
            role = str(r.get("ContactRole") or "").strip()
            is_primary = bool(r.get("IsPrimary"))
            name = f"{first} {last}".strip() or email
            badge = "Primary" if is_primary else role
            label = f"{name} ({badge})" if badge else name
            options.append(label)
            emails.append(email)

        self.compose_contact_options = options
        self.compose_contact_emails = emails
        if options:
            self.compose_selected_contact = options[0]
            self.compose_to = emails[0]
        self.compose_email_open = True

    def set_compose_contact_new(self, label: str):
        self.compose_selected_contact = label
        if label in self.compose_contact_options:
            idx = self.compose_contact_options.index(label)
            self.compose_to = self.compose_contact_emails[idx]

    def close_compose_new(self):
        self.compose_email_open = False
        self.compose_error = ""
        self.compose_success = ""
        self.compose_sending = False
        self.compose_is_reply = False

    def send_compose_new(self):
        """Send new email from Communications and log to comm log."""
        from LucidPM_Reflex.state import send_email
        import tempfile, os

        if self.compose_sending:
            return

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

        self.compose_sending = True

        tmp_paths = []
        for name, data in zip(self.attach_filenames, self.attach_file_bytes):
            suffix = os.path.splitext(name)[-1] or ".pdf"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            named_path = os.path.join(os.path.dirname(tmp.name), name)
            os.rename(tmp.name, named_path)
            tmp_paths.append(named_path)

        try:
            send_email(
                to_address=self.compose_to.strip(),
                subject=self.compose_subject.strip(),
                body=self.compose_body.strip(),
                db=self.db,
                attachment_paths=tmp_paths or None,
            )
        except Exception as ex:
            self.compose_error = f"Failed to send: {ex}"
            self.compose_sending = False
            return
        finally:
            for p in tmp_paths:
                try:
                    os.unlink(p)
                except Exception:
                    pass

        if self.compose_tenant_label and self.compose_tenant_label in self.tenant_labels:
            try:
                idx = self.tenant_labels.index(self.compose_tenant_label)
                tenant_id = int(self.tenant_ids_str[idx])

                col_rows = run_query(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Communications'",
                    db=self.db,
                )
                available = {str(r.get("COLUMN_NAME") or "") for r in col_rows}

                prop_rows = run_query(
                    "SELECT PropertyID FROM dbo.Tenants WHERE TenantID = ?",
                    (tenant_id,), db=self.db,
                )
                prop_id = int(prop_rows[0]["PropertyID"]) if prop_rows and prop_rows[0].get("PropertyID") else None

                columns = ["TenantID", "CommDate", "Method"]
                values_sql = ["?", "SYSDATETIME()", "?"]
                params = [tenant_id, "Email"]

                if "Subject" in available:
                    columns.append("Subject"); values_sql.append("?")
                    params.append(self.compose_subject.strip())
                if "Body" in available:
                    columns.append("Body"); values_sql.append("?")
                    params.append(self.compose_body.strip())
                elif "Notes" in available:
                    columns.append("Notes"); values_sql.append("?")
                    params.append(self.compose_body.strip())
                if "FromTo" in available:
                    columns.append("FromTo"); values_sql.append("?")
                    params.append(self.compose_to.strip())
                if "Outcome" in available:
                    columns.append("Outcome"); values_sql.append("?")
                    params.append("Sent")
                if "PropertyID" in available and prop_id is not None:
                    columns.append("PropertyID"); values_sql.append("?")
                    params.append(prop_id)

                col_str = ", ".join(f"[{c}]" for c in columns)
                val_str = ", ".join(values_sql)
                run_exec(
                    f"INSERT INTO dbo.Communications ({col_str}) VALUES ({val_str})",
                    tuple(params), db=self.db,
                )
            except Exception:
                pass

        self.compose_success = "Email sent."
        self.compose_sending = False
        self.compose_email_open = False
        self.compose_is_reply = False

    # ── Log Entry event handlers ─────────────────────────────────────────────────

    def _get_tenant_id_from_label(self, label: str) -> Optional[int]:
        try:
            idx = self.tenant_labels.index(label)
            return int(self.tenant_ids_str[idx])
        except (ValueError, IndexError):
            return None

    def _load_log_entry_contacts(self):
        tenant_id = self._get_tenant_id_from_label(self.log_entry_tenant_label)
        names = ["(No contact)"]
        ids = [0]

        if tenant_id:
            try:
                rows = run_query(
                    "SELECT ContactID, FirstName, LastName, Email1, IsPrimary "
                    "FROM dbo.Contacts "
                    "WHERE TenantID = ? "
                    "ORDER BY IsPrimary DESC, LastName, FirstName",
                    (tenant_id,),
                    db=self.db,
                )
                for r in rows:
                    cid = int(r.get("ContactID") or 0)
                    first = str(r.get("FirstName") or "").strip()
                    last = str(r.get("LastName") or "").strip()
                    email = str(r.get("Email1") or "").strip()
                    is_primary = bool(r.get("IsPrimary"))
                    name = f"{first} {last}".strip() or email or f"Contact #{cid}"
                    label = f"{name} (Primary)" if is_primary else name
                    if email:
                        label = f"{label} — {email}"
                    names.append(label)
                    ids.append(cid)
            except Exception:
                pass

        self.log_entry_contact_names = names
        self.log_entry_contact_ids = ids
        self.log_entry_contact_name = names[0]

    def set_log_entry_tenant(self, label: str):
        self.log_entry_tenant_label = label
        self._load_log_entry_contacts()

    def set_log_entry_contact(self, label: str):
        self.log_entry_contact_name = label

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

        tenant_id = self._get_tenant_id_from_label(self.log_entry_tenant_label)
        if tenant_id is None:
            self.log_entry_error = "Could not resolve tenant."
            return

        contact_id = None
        if (
            self.log_entry_contact_name
            and self.log_entry_contact_name in self.log_entry_contact_names
        ):
            contact_idx = self.log_entry_contact_names.index(self.log_entry_contact_name)
            resolved_contact_id = self.log_entry_contact_ids[contact_idx]
            contact_id = int(resolved_contact_id) if int(resolved_contact_id or 0) > 0 else None

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

            if "ContactID" in available and contact_id is not None:
                columns.append("ContactID")
                values_sql.append("?")
                params.append(contact_id)

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
            self._load_log_entry_contacts()
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
                rx.text(msg["display_name"], size="2", weight="bold", color=BRAND_DARK),
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



def inbox_image_display(img: dict) -> rx.Component:
    return rx.vstack(
        rx.image(
            src=img["data_uri"],
            width="100%",
            max_width="500px",
            border_radius="8px",
            border="1px solid #E5E7EB",
        ),
        rx.text(
            img["filename"],
            size="1",
            color="#888",
        ),
        spacing="1",
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
                rx.text(CommunicationsState.selected_message["display_label"] + ":", size="2", color="#555", weight="medium"),
                rx.text(CommunicationsState.selected_message["display_name"], size="2"),
                rx.text(CommunicationsState.selected_message["display_address"], size="2", color="#888"),
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
        rx.cond(
            CommunicationsState.selected_message_images.length() > 0,
            rx.vstack(
                rx.divider(),
                rx.hstack(
                    rx.text("📎", size="2"),
                    rx.text(
                        CommunicationsState.selected_message_images.length().to_string()
                        + " image attachment(s)",
                        size="2",
                        color="#555",
                        weight="medium",
                    ),
                    align="center",
                    spacing="2",
                ),
                rx.foreach(
                    CommunicationsState.selected_message_images,
                    inbox_image_display,
                ),
                width="100%",
                spacing="3",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.selected_message_images.length() > 0,
            rx.vstack(
                rx.divider(),
                rx.hstack(
                    rx.button(
                        "Process with AI",
                        on_click=CommunicationsState.process_image_with_ai,
                        loading=CommunicationsState.ai_processing,
                        color_scheme="violet",
                        variant="soft",
                        size="2",
                    ),
                    rx.cond(
                        CommunicationsState.ai_processing,
                        rx.text(
                            "Reading image...",
                            size="2",
                            color="#888",
                        ),
                        rx.fragment(),
                    ),
                    align="center",
                    spacing="3",
                ),
                rx.cond(
                    CommunicationsState.ai_error != "",
                    rx.callout.root(
                        rx.callout.text(CommunicationsState.ai_error),
                        color_scheme="red",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    CommunicationsState.ai_result != "",
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "AI Summary",
                                size="2",
                                weight="bold",
                                color=BRAND_DARK,
                            ),
                            rx.text(
                                "— review and edit before saving",
                                size="2",
                                color="#888",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text_area(
                            value=CommunicationsState.ai_result,
                            on_change=CommunicationsState.set_ai_result,
                            rows="6",
                            width="100%",
                        ),
                        rx.button(
                            "Send to Log Entry →",
                            on_click=CommunicationsState.send_to_log_entry,
                            color_scheme="blue",
                            size="2",
                        ),
                        spacing="3",
                        width="100%",
                        padding="12px",
                        background="#F5F3FF",
                        border_radius="8px",
                        border="1px solid #DDD6FE",
                    ),
                    rx.fragment(),
                ),
                width="100%",
                spacing="3",
            ),
            rx.fragment(),
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
                    "Reply",
                    on_click=CommunicationsState.open_reply,
                    color_scheme="blue",
                    variant="outline",
                    size="2",
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
            rx.box(
                rx.hstack(
                    rx.text(
                        "Inbox",
                        size="2", weight="bold",
                        color=rx.cond(CommunicationsState.inbox_folder == "INBOX", "white", "#666"),
                        style={
                            "padding": "5px 20px",
                            "border_radius": "999px",
                            "background": rx.cond(
                                CommunicationsState.inbox_folder == "INBOX",
                                BRAND_PRIMARY,
                                "transparent",
                            ),
                            "cursor": "pointer",
                            "transition": "background 0.15s ease, color 0.15s ease",
                            "user_select": "none",
                        },
                        on_click=CommunicationsState.set_inbox_folder("INBOX"),
                    ),
                    rx.text(
                        "Sent Mail",
                        size="2", weight="bold",
                        color=rx.cond(CommunicationsState.inbox_folder == "Sent Mail", "white", "#666"),
                        style={
                            "padding": "5px 20px",
                            "border_radius": "999px",
                            "background": rx.cond(
                                CommunicationsState.inbox_folder == "Sent Mail",
                                BRAND_PRIMARY,
                                "transparent",
                            ),
                            "cursor": "pointer",
                            "transition": "background 0.15s ease, color 0.15s ease",
                            "user_select": "none",
                        },
                        on_click=CommunicationsState.set_inbox_folder("Sent Mail"),
                    ),
                    spacing="0",
                ),
                style={
                    "background": "#e2e8f0",
                    "border_radius": "999px",
                    "padding": "3px",
                    "display": "inline-flex",
                    "box_shadow": "inset 0 1px 2px rgba(0,0,0,0.08)",
                },
            ),
            rx.button(
                "+ Compose",
                on_click=CommunicationsState.open_compose_new,
                color_scheme="blue",
                variant="outline",
                size="2",
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    "Refresh",
                    on_click=CommunicationsState.refresh_inbox,
                    loading=CommunicationsState.inbox_loading,
                    color_scheme="blue",
                    variant="outline",
                    size="2",
                ),
                rx.vstack(
                    rx.text(
                        CommunicationsState.refresh_status_text,
                        size="2",
                        color="#666",
                        overflow="hidden",
                        white_space="nowrap",
                        text_overflow="ellipsis",
                        max_width="200px",
                    ),
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
                    align="end",
                ),
                align="center",
                spacing="3",
            ),
            width="100%",
            align="center",
            flex_wrap="wrap",
            gap="8px",
        ),
        rx.callout.root(
            rx.callout.text(
                rx.cond(
                    CommunicationsState.inbox_folder == "INBOX",
                    "Inbox does not auto-refresh. Click Refresh to check for new messages.",
                    "Sent Mail does not auto-refresh. Click Refresh to load sent messages.",
                ),
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
                rx.text(
                    rx.cond(
                        CommunicationsState.inbox_folder == "INBOX",
                        "No messages found in Inbox.",
                        "No messages found in Sent Mail.",
                    ),
                    size="2",
                    color="#888",
                ),
                rx.text("Click Refresh to load messages.", size="2", color="#888"),
            ),
            rx.fragment(),
        ),
        rx.cond(
            CommunicationsState.inbox_messages.length() > 0,
            rx.box(
                rx.script(INBOX_RESIZER_SCRIPT),
                rx.hstack(
                    rx.box(
                        rx.vstack(
                            rx.foreach(
                                CommunicationsState.inbox_messages,
                                inbox_message_row,
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        id="inbox-message-list",
                        style={
                            "width": "380px",
                            "min_width": "380px",
                            "max_height": "calc(100vh - 220px)",
                            "overflow_y": "auto",
                            "background": "white",
                            "border": "1px solid #dde3f0",
                            "border_radius": "12px",
                            "padding": "12px",
                            "flex_shrink": "0",
                        },
                    ),
                    rx.box(
                        rx.box(
                            style={
                                "width": "4px",
                                "height": "40px",
                                "background": "#c5d0f0",
                                "border_radius": "2px",
                            }
                        ),
                        id="inbox-panel-resizer",
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
                            "z_index": "10",
                        },
                    ),
                    rx.box(
                        rx.cond(
                            CommunicationsState.selected_message_uid != "",
                            inbox_message_detail(),
                            rx.box(
                                rx.text(
                                    "👈 Select a message to view",
                                    color="#888",
                                    size="3",
                                ),
                                padding="48px",
                                text_align="center",
                            ),
                        ),
                        style={
                            "flex": "1",
                            "min_width": "0",
                            "max_height": "calc(100vh - 220px)",
                            "overflow_y": "auto",
                            "background": "white",
                            "border": "1px solid #dde3f0",
                            "border_radius": "12px",
                            "padding": "16px",
                        },
                    ),
                    spacing="0",
                    width="100%",
                    align="start",
                ),
                width="100%",
            ),
            rx.fragment(),
        ),
        width="100%",
        spacing="4",
        align_items="start",
        overflow_x="hidden",
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
                rx.hstack(
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
                    rx.vstack(
                        rx.text("Contact", size="2", color="#555", weight="medium"),
                        rx.select(
                            CommunicationsState.log_entry_contact_names,
                            value=CommunicationsState.log_entry_contact_name,
                            on_change=CommunicationsState.set_log_entry_contact,
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    width="100%",
                    spacing="4",
                    align="end",
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


def attach_file_row_comms(filename: str) -> rx.Component:
    return rx.text(
        "📎 " + filename,
        size="2",
        color=BRAND_DARK,
    )


def attachment_picker_panel_comms() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Attachments", size="2", color="#555", weight="medium"),
            rx.upload(
                rx.button("Attach Files", variant="outline", size="2"),
                id="email_attachment_upload_comms",
                accept={"application/pdf": [".pdf"]},
                max_files=5,
                on_drop=CommunicationsState.handle_attachment_upload,
            ),
            rx.cond(
                CommunicationsState.attach_filenames.length() > 0,
                rx.button(
                    "Clear",
                    on_click=CommunicationsState.clear_attachments,
                    variant="ghost",
                    size="1",
                    color_scheme="red",
                ),
                rx.fragment(),
            ),
            align="center",
            spacing="3",
            width="100%",
        ),
        rx.cond(
            CommunicationsState.attach_filenames.length() > 0,
            rx.vstack(
                rx.foreach(
                    CommunicationsState.attach_filenames,
                    attach_file_row_comms,
                ),
                spacing="1",
                padding="8px",
                background="#F9FAFB",
                border_radius="6px",
                border="1px solid #E5E7EB",
                width="100%",
            ),
            rx.fragment(),
        ),
        spacing="2",
        width="100%",
    )


def comms_compose_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.cond(
                        CommunicationsState.compose_is_reply,
                        "Reply",
                        "New Email",
                    )
                ),
                rx.cond(
                    CommunicationsState.compose_error != "",
                    rx.callout.root(
                        rx.callout.text(CommunicationsState.compose_error),
                        color_scheme="red",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.vstack(
                    rx.text("To", size="2", color="#555"),
                    rx.input(
                        value=CommunicationsState.compose_to,
                        on_change=CommunicationsState.set_compose_to,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Subject", size="2", color="#555"),
                    rx.input(
                        value=CommunicationsState.compose_subject,
                        on_change=CommunicationsState.set_compose_subject,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Message", size="2", color="#555"),
                    rx.text_area(
                        value=CommunicationsState.compose_body,
                        on_change=CommunicationsState.set_compose_body,
                        placeholder="Write your reply here...",
                        rows="8",
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                attachment_picker_panel_comms(),
                rx.hstack(
                    rx.button(
                        "Send",
                        on_click=CommunicationsState.send_compose_email,
                        loading=CommunicationsState.compose_sending,
                        color_scheme="blue",
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            on_click=CommunicationsState.close_compose_email,
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
        open=CommunicationsState.compose_email_open,
    )


def compose_new_attachment_row(filename: str) -> rx.Component:
    return rx.text("📎 " + filename, size="2", color=BRAND_DARK)


def comms_compose_new_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title("New Email"),
                rx.cond(
                    CommunicationsState.compose_error != "",
                    rx.callout.root(
                        rx.callout.text(CommunicationsState.compose_error),
                        color_scheme="red", width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.vstack(
                    rx.text("Tenant", size="2", color="#555"),
                    rx.select(
                        CommunicationsState.tenant_labels,
                        value=CommunicationsState.compose_tenant_label,
                        on_change=CommunicationsState.set_compose_tenant,
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.cond(
                    CommunicationsState.compose_contact_options.length() > 0,
                    rx.vstack(
                        rx.text("Contact", size="2", color="#555"),
                        rx.select(
                            CommunicationsState.compose_contact_options,
                            value=CommunicationsState.compose_selected_contact,
                            on_change=CommunicationsState.set_compose_contact_new,
                            width="100%",
                        ),
                        spacing="1", width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.vstack(
                    rx.text("To", size="2", color="#555"),
                    rx.input(
                        value=CommunicationsState.compose_to,
                        on_change=CommunicationsState.set_compose_to,
                        placeholder="recipient@example.com",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Subject", size="2", color="#555"),
                    rx.input(
                        value=CommunicationsState.compose_subject,
                        on_change=CommunicationsState.set_compose_subject,
                        placeholder="Subject",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Message", size="2", color="#555"),
                    rx.text_area(
                        value=CommunicationsState.compose_body,
                        on_change=CommunicationsState.set_compose_body,
                        placeholder="Write your message here...",
                        rows="8",
                        width="100%",
                    ),
                    spacing="1", width="100%",
                ),
                rx.upload(
                    rx.button("Attach Files", variant="outline", size="2"),
                    id="comms_compose_new_upload",
                    accept={"application/pdf": [".pdf"]},
                    max_files=5,
                    on_drop=CommunicationsState.handle_attachment_upload,
                ),
                rx.cond(
                    CommunicationsState.attach_filenames.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            CommunicationsState.attach_filenames,
                            compose_new_attachment_row,
                        ),
                        spacing="1",
                    ),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.button(
                        "Send",
                        on_click=CommunicationsState.send_compose_new,
                        loading=CommunicationsState.compose_sending,
                        color_scheme="blue",
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            on_click=CommunicationsState.close_compose_new,
                            variant="outline",
                        ),
                    ),
                    spacing="3", justify="end", width="100%",
                ),
                spacing="4", width="100%",
            ),
            max_width="600px",
        ),
        open=rx.cond(
            CommunicationsState.compose_is_reply,
            False,
            CommunicationsState.compose_email_open,
        ),
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
            rx.script(INBOX_RESIZER_SCRIPT),
            rx.heading("Communications", size="6", color=BRAND_DARK),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Inbox", value="inbox"),
                    rx.tabs.trigger("Tenant Communications", value="report"),
                    rx.tabs.trigger("Log Entry", value="log"),
                    width="100%",
                ),
                rx.tabs.content(
                    inbox_tab(),
                    value="inbox",
                    padding_top="16px",
                    width="100%",
                ),
                rx.tabs.content(
                    tenant_communications_tab(),
                    value="report",
                    padding_top="16px",
                    width="100%",
                ),
                rx.tabs.content(
                    log_entry_tab(),
                    value="log",
                    padding_top="16px",
                    width="100%",
                ),
                value=CommunicationsState.active_tab,
                on_change=CommunicationsState.set_active_tab,
                width="100%",
                style={
                    "width": "100%",
                    "min_width": "100%",
                },
            ),
            width="100%",
            spacing="4",
            align_items="stretch",
            padding="0",
        ),
        padding="0",
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
        flex_shrink="0",
        style={
            "box_sizing": "border-box",
            "overflow_x": "hidden",
        },
    )


def communications_page() -> rx.Component:
    return page_shell(
        rx.fragment(
            communications_content(),
            comms_compose_modal(),
            comms_compose_new_modal(),
        ),
        current_path="/communications",
    )
