"""
Shared DB helpers, constants, and base state.
Import this from any page or component.
"""

import reflex as rx
import pyodbc
import datetime
from cryptography.fernet import Fernet

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


# ---------------------------------------------------------------------------
# Encryption utilities: Fernet-based, key persisted in AppSettings
# ---------------------------------------------------------------------------

def get_fernet(db: str) -> "Fernet":
    """Load or generate the Fernet encryption key from AppSettings."""
    rows = run_query(
        "SELECT SettingValue FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey'",
        db=db,
    )
    if rows and rows[0].get("SettingValue"):
        key = str(rows[0]["SettingValue"])
    else:
        key = Fernet.generate_key().decode("utf-8")
        run_exec(
            """
            MERGE dbo.AppSettings AS target
            USING (SELECT ? AS SettingKey, ? AS SettingValue) AS src
            ON target.SettingKey = src.SettingKey
            WHEN MATCHED THEN
                UPDATE SET SettingValue = src.SettingValue, UpdatedOn = SYSDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (SettingKey, SettingValue, UpdatedOn)
                VALUES (src.SettingKey, src.SettingValue, SYSDATETIME());
            """,
            ("LocalEncryptionKey", key),
            db=db,
        )
    return Fernet(key.encode("utf-8"))


def encrypt_value(value: str, db: str) -> str:
    """Encrypt a plaintext string. Returns empty string if value is empty."""
    if not value:
        return ""
    return get_fernet(db).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str, db: str) -> str:
    """Decrypt a Fernet-encrypted string. Returns empty string if value is empty."""
    if not value:
        return ""
    return get_fernet(db).decrypt(value.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Email utility: outbound SMTP send
# ---------------------------------------------------------------------------

def send_email(
    to_address: str,
    subject: str,
    body: str,
    db: str,
    attachment_paths: list[str] | None = None,
) -> None:
    """Send an email via the configured SMTP server.

    Loads credentials from EmailConfig. Raises on failure so callers can show
    page-specific error messages. Supports optional file attachments.
    """
    import os
    import smtplib
    import ssl
    from email.message import EmailMessage
    from email.utils import formataddr

    rows = run_query(
        "SELECT TOP 1 DisplayName, EmailAddress, SMTPServer, SMTPPort, "
        "Username, PasswordEncrypted FROM dbo.EmailConfig WHERE IsActive = 1",
        db=db,
    )
    if not rows:
        raise RuntimeError(
            "Email is not configured. Go to Admin Settings to set up email."
        )

    cfg = rows[0]
    display_name = str(cfg.get("DisplayName") or "").strip()
    from_address = str(cfg.get("EmailAddress") or "").strip()
    smtp_server = str(cfg.get("SMTPServer") or "").strip()
    smtp_port = int(cfg.get("SMTPPort") or 587)
    username = str(cfg.get("Username") or "").strip() or from_address
    password_enc = str(cfg.get("PasswordEncrypted") or "").strip()

    if not from_address or not smtp_server or not password_enc:
        raise RuntimeError("Email credentials are incomplete. Go to Admin Settings.")

    password = decrypt_value(password_enc, db)
    if not password:
        raise RuntimeError("Saved email password could not be decrypted.")

    from email.utils import formatdate, make_msgid

    msg = EmailMessage()
    msg["From"] = formataddr((display_name, from_address)) if display_name else from_address
    msg["To"] = str(to_address or "").strip()
    msg["Subject"] = str(subject or "").strip()
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_address.split("@")[-1] if "@" in from_address else None)
    msg.set_content(str(body or ""), subtype="plain", charset="utf-8")

    if attachment_paths:
        for path in attachment_paths:
            if not path or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=os.path.basename(path),
            )

    recipient = str(to_address or "").strip()
    if not recipient or "@" not in recipient:
        raise RuntimeError("Recipient email address is invalid.")

    def _send_starttls(port: int) -> None:
        with smtplib.SMTP(smtp_server, port, timeout=45, local_hostname="localhost") as server:
            server.ehlo_or_helo_if_needed()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(username, password)
            server.send_message(msg, from_addr=from_address, to_addrs=[recipient])

    def _send_plain(port: int) -> None:
        """Send using Outlook-style Auto fallback with no TLS upgrade.

        Some legacy Spectrum/Roadrunner SMTP endpoints report usable auth on
        port 587 but close during DATA after Python forces STARTTLS. Outlook's
        "Auto" setting may continue without STARTTLS. This method intentionally
        mirrors that legacy path as a fallback only.
        """
        with smtplib.SMTP(smtp_server, port, timeout=45, local_hostname="localhost") as server:
            server.ehlo_or_helo_if_needed()
            server.login(username, password)
            server.send_message(msg, from_addr=from_address, to_addrs=[recipient])

    def _send_auto(port: int) -> None:
        """Mimic Outlook Encryption=Auto.

        Connect normally, inspect server capabilities, upgrade to STARTTLS only
        when advertised, then authenticate and submit. If STARTTLS is not
        advertised, continue with the plain authenticated SMTP path.
        """
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, port, timeout=45, local_hostname="localhost") as server:
            server.ehlo_or_helo_if_needed()
            if server.has_extn("starttls"):
                server.starttls(context=context)
                server.ehlo()
            server.login(username, password)
            server.send_message(msg, from_addr=from_address, to_addrs=[recipient])

    def _send_ssl(port: int) -> None:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, timeout=45, context=context, local_hostname="localhost") as server:
            server.ehlo_or_helo_if_needed()
            server.login(username, password)
            server.send_message(msg, from_addr=from_address, to_addrs=[recipient])


    def _append_to_sent_mail(sent_msg) -> None:
        """Copy sent message to IMAP Sent Mail folder.

        Non-fatal. If the IMAP append fails, the send still succeeded.
        """
        import imaplib
        import ssl
        import time

        imap_host = smtp_server.replace("smtp.", "imap.", 1)
        imap = None
        try:
            ctx = ssl.create_default_context()
            try:
                imap = imaplib.IMAP4_SSL(imap_host, 993, ssl_context=ctx)
            except Exception:
                try:
                    imap = imaplib.IMAP4(imap_host, 143)
                except Exception:
                    return

            imap.login(username, password)

            def _decode_mailbox_name(raw_item) -> str:
                text = raw_item.decode("utf-8", errors="replace") if isinstance(raw_item, bytes) else str(raw_item)
                if ' "/" ' in text:
                    return text.rsplit(' "/" ', 1)[-1].strip().strip('"')
                if ' "." ' in text:
                    return text.rsplit(' "." ', 1)[-1].strip().strip('"')
                return text.split()[-1].strip().strip('"') if text.split() else ""

            sent_folder = "Sent Mail"
            try:
                status, boxes = imap.list()
                if status == "OK" and boxes:
                    for item in boxes:
                        name = _decode_mailbox_name(item)
                        low = name.lower()
                        if "\\sent" in low or "sent" in low:
                            sent_folder = name
                            break
            except Exception:
                pass

            mailbox = f'"{sent_folder}"' if " " in str(sent_folder) or "/" in str(sent_folder) else str(sent_folder)
            imap.append(
                mailbox,
                "\\Seen",
                imaplib.Time2Internaldate(time.time()),
                sent_msg.as_bytes(),
            )
        except Exception:
            pass
        finally:
            try:
                if imap:
                    imap.logout()
            except Exception:
                pass

    attempts: list[tuple[str, int, object]] = []

    def _try(label: str, fn, port: int) -> bool:
        try:
            fn(port)
            return True
        except Exception as ex:
            attempts.append((label, port, ex))
            return False

    smtp_server_lc = smtp_server.lower()
    spectrum_legacy = (
        smtp_server_lc == "smtp.biz.rr.com"
        or smtp_server_lc.endswith(".rr.com")
        or "charter" in smtp_server_lc
        or "spectrum" in smtp_server_lc
    )

    if smtp_port == 465:
        if _try("SMTP SSL", _send_ssl, 465):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP Plain", _send_plain, 587):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP Auto", _send_auto, 587):
            _append_to_sent_mail(msg)
            return
    elif spectrum_legacy:
        # Outlook shows Encryption=Auto for this legacy Spectrum/Roadrunner
        # account, but Python STARTTLS is reset by the server during the TLS
        # handshake. A raw Python test confirmed plain authenticated SMTP on
        # port 587 logs in successfully. For this provider family, try the
        # Outlook-compatible plain authenticated path first.
        if _try("SMTP Plain", _send_plain, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP Auto", _send_auto, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP STARTTLS", _send_starttls, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP SSL", _send_ssl, 465):
            _append_to_sent_mail(msg)
            return
    else:
        # Normal providers should use STARTTLS/Auto before any plain fallback.
        if _try("SMTP Auto", _send_auto, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP STARTTLS", _send_starttls, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP Plain", _send_plain, smtp_port):
            _append_to_sent_mail(msg)
            return
        if _try("SMTP SSL", _send_ssl, 465):
            _append_to_sent_mail(msg)
            return

    detail = " | ".join(f"{label} {port}: {type(ex).__name__}: {ex}" for label, port, ex in attempts)
    raise RuntimeError(
        "SMTP send failed after provider-specific plain SMTP, Outlook-style Auto, STARTTLS, and SSL fallback attempts. "
        + detail
    )

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
        from LucidPM.pages.dashboard import DashboardState
        from LucidPM.pages.rent_roll import RentRollState
        from LucidPM.pages.property_financials import PropertyFinancialsState
        from LucidPM.pages.property_financials_analytics import PropertyFinancialsAnalyticsState
        from LucidPM.pages.proforma import ProformaState
        from LucidPM.pages.waiting_list import WaitingListState
        from LucidPM.pages.communications import CommunicationsState
        from LucidPM.pages.tenants import TenantState
        from LucidPM.pages.work_items import WorkItemState
        from LucidPM.pages.leases_expiring import LeasesExpiringState
        from LucidPM.pages.lease_documents import LeaseDocumentState
        from LucidPM.pages.lease_package_builder import LeasePackageBuilderState
        from LucidPM.pages.admin_settings import AdminSettingsState
        yield AdminSettingsState.reload_on_db_change
        yield LeaseDocumentState.reload_on_db_change
        yield LeasePackageBuilderState.reload_on_db_change
        yield LeasesExpiringState.reload_on_db_change
        yield WorkItemState.reload_on_db_change
        yield TenantState.reload_on_db_change
        yield CommunicationsState.reload_on_db_change
        yield DashboardState.reload_on_db_change
        yield RentRollState.reload_on_db_change
        yield PropertyFinancialsState.reload_on_db_change
        yield PropertyFinancialsAnalyticsState.reload_on_db_change
        yield ProformaState.reload_on_db_change
        yield WaitingListState.reload_on_db_change
