"""
Admin Settings page.

Stores simple app-level preferences in dbo.AppSettings.

v1.2.2
- Adds responsive page-width handling tied to the resizable sidebar.
- Makes Settings form rows wrap on narrower layouts.

v1.2.3
- Expands Settings page to the dynamic available page width.
- Removes inner page padding so cards align with other responsive modules.
- Fixes local encryption helper resolution.
- Adds EmailConfig settings card for IMAP/SMTP configuration.
- Adds AIConfig settings card for Anthropic API configuration.
- Stores password/API key encrypted using existing encryption utilities.
"""

import reflex as rx

from LucidPM_Reflex.state import (
    AppState,
    run_query,
    run_exec,
    BRAND_DARK,
)
from LucidPM_Reflex.components.sidebar import page_shell


# Page width constant — dynamic sidebar width + page_shell padding (32px each side = 64px)
# Sidebar script updates --lucid-sidebar-width when resized.
FULL_PAGE_WIDTH = "calc(100vw - var(--lucid-sidebar-width, 220px) - 64px)"


def _get_or_create_encryption_key(db: str) -> str:
    """Return a local Fernet key stored in AppSettings. Creates one if missing."""
    rows = run_query(
        "SELECT SettingValue FROM AppSettings WHERE SettingKey = 'LocalEncryptionKey'",
        db=db,
    )
    if rows and str(rows[0].get("SettingValue") or "").strip():
        return str(rows[0].get("SettingValue") or "").strip()

    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("utf-8")
    run_exec(
        """
        IF EXISTS (SELECT 1 FROM AppSettings WHERE SettingKey = 'LocalEncryptionKey')
            UPDATE AppSettings SET SettingValue = ?, UpdatedOn = SYSDATETIME() WHERE SettingKey = 'LocalEncryptionKey'
        ELSE
            INSERT INTO AppSettings (SettingKey, SettingValue, UpdatedOn) VALUES ('LocalEncryptionKey', ?, SYSDATETIME())
        """,
        (key, key),
        db=db,
    )
    return key


def encrypt_value(value: str, db: str) -> str:
    """Encrypt a string value for storage."""
    if not value:
        return ""
    from cryptography.fernet import Fernet

    key = _get_or_create_encryption_key(db)
    return Fernet(key.encode("utf-8")).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str, db: str) -> str:
    """Decrypt a stored string value."""
    if not value:
        return ""
    from cryptography.fernet import Fernet

    key = _get_or_create_encryption_key(db)
    return Fernet(key.encode("utf-8")).decrypt(str(value).encode("utf-8")).decode("utf-8")


class SettingsState(AppState):
    enable_developer_tools: bool = False
    form_error: str = ""
    form_success: str = ""

    # Email config
    email_display_name: str = ""
    email_address: str = ""
    email_imap_server: str = "imap.biz.rr.com"
    email_imap_port: int = 993
    email_smtp_server: str = "smtp.biz.rr.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_poll_interval: int = 10
    email_configured: bool = False

    # AI config
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-4-20250514"
    ai_configured: bool = False

    # Connection test feedback
    email_test_result: str = ""
    ai_test_result: str = ""

    def on_load(self):
        self._ensure_schema()
        self._load_settings()

    def reload_on_db_change(self):
        self.form_error = ""
        self.form_success = ""
        self.email_test_result = ""
        self.ai_test_result = ""
        self._ensure_schema()
        self._load_settings()

    def _ensure_schema(self):
        run_exec(
            """
            IF OBJECT_ID('dbo.AppSettings', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.AppSettings (
                    SettingKey NVARCHAR(100) NOT NULL PRIMARY KEY,
                    SettingValue NVARCHAR(1000) NULL,
                    UpdatedOn DATETIME2 NOT NULL CONSTRAINT DF_AppSettings_UpdatedOn DEFAULT (SYSDATETIME())
                );
            END
            """,
            db=self.db,
        )
        run_exec(
            """
            IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'EnableDeveloperTools')
            BEGIN
                INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
                VALUES ('EnableDeveloperTools', '0', SYSDATETIME());
            END
            """,
            db=self.db,
        )
        run_exec(
            """
            IF OBJECT_ID('dbo.EmailConfig', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.EmailConfig (
                    EmailConfigID      INT IDENTITY(1,1) PRIMARY KEY,
                    DisplayName        NVARCHAR(100)  NULL,
                    EmailAddress       NVARCHAR(200)  NULL,
                    IMAPServer         NVARCHAR(200)  NULL,
                    IMAPPort           INT            NOT NULL DEFAULT 993,
                    SMTPServer         NVARCHAR(200)  NULL,
                    SMTPPort           INT            NOT NULL DEFAULT 587,
                    Username           NVARCHAR(200)  NULL,
                    PasswordEncrypted  NVARCHAR(500)  NULL,
                    PollIntervalMin    INT            NOT NULL DEFAULT 10,
                    IsActive           BIT            NOT NULL DEFAULT 1,
                    CreatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
                    UpdatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME()
                );
                INSERT INTO dbo.EmailConfig (DisplayName, EmailAddress, IMAPServer, SMTPServer, Username)
                VALUES ('', '', 'imap.biz.rr.com', 'smtp.biz.rr.com', '');
            END
            """,
            db=self.db,
        )
        run_exec(
            """
            IF OBJECT_ID('dbo.AIConfig', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.AIConfig (
                    AIConfigID         INT IDENTITY(1,1) PRIMARY KEY,
                    APIKeyEncrypted    NVARCHAR(500)  NULL,
                    ModelName          NVARCHAR(100)  NOT NULL DEFAULT 'claude-sonnet-4-20250514',
                    IsActive           BIT            NOT NULL DEFAULT 1,
                    CreatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
                    UpdatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME()
                );
                INSERT INTO dbo.AIConfig (ModelName)
                VALUES ('claude-sonnet-4-20250514');
            END
            """,
            db=self.db,
        )

    def _load_settings(self):
        rows = run_query(
            "SELECT SettingValue FROM AppSettings WHERE SettingKey = 'EnableDeveloperTools'",
            db=self.db,
        )
        self.enable_developer_tools = bool(
            rows and str(rows[0].get("SettingValue") or "0").strip() in ("1", "true", "True", "yes", "Yes")
        )

        email_rows = run_query(
            "SELECT TOP 1 DisplayName, EmailAddress, IMAPServer, IMAPPort, "
            "SMTPServer, SMTPPort, Username, PasswordEncrypted, PollIntervalMin "
            "FROM EmailConfig WHERE IsActive = 1",
            db=self.db,
        )
        if email_rows:
            r = email_rows[0]
            self.email_display_name = str(r.get("DisplayName") or "")
            self.email_address = str(r.get("EmailAddress") or "")
            self.email_imap_server = str(r.get("IMAPServer") or "imap.biz.rr.com")
            self.email_imap_port = int(r.get("IMAPPort") or 993)
            self.email_smtp_server = str(r.get("SMTPServer") or "smtp.biz.rr.com")
            self.email_smtp_port = int(r.get("SMTPPort") or 587)
            self.email_username = str(r.get("Username") or "")
            self.email_password = ""
            self.email_poll_interval = int(r.get("PollIntervalMin") or 10)
            self.email_configured = bool(r.get("EmailAddress") and r.get("PasswordEncrypted"))
        else:
            self.email_display_name = ""
            self.email_address = ""
            self.email_imap_server = "imap.biz.rr.com"
            self.email_imap_port = 993
            self.email_smtp_server = "smtp.biz.rr.com"
            self.email_smtp_port = 587
            self.email_username = ""
            self.email_password = ""
            self.email_poll_interval = 10
            self.email_configured = False

        ai_rows = run_query(
            "SELECT TOP 1 APIKeyEncrypted, ModelName FROM AIConfig WHERE IsActive = 1",
            db=self.db,
        )
        if ai_rows:
            r = ai_rows[0]
            self.ai_api_key = ""
            self.ai_model = str(r.get("ModelName") or "claude-sonnet-4-20250514")
            self.ai_configured = bool(r.get("APIKeyEncrypted"))
        else:
            self.ai_api_key = ""
            self.ai_model = "claude-sonnet-4-20250514"
            self.ai_configured = False

    def set_enable_developer_tools(self, value: bool):
        self.enable_developer_tools = value
        run_exec(
            """
            UPDATE AppSettings
            SET SettingValue = ?, UpdatedOn = SYSDATETIME()
            WHERE SettingKey = 'EnableDeveloperTools'
            """,
            ("1" if value else "0",),
            db=self.db,
        )
        self.form_success = "Settings saved. Reload Lease Templates to apply this visibility change."
        self.form_error = ""

    def set_email_display_name(self, v: str):
        self.email_display_name = v
        run_exec(
            "UPDATE EmailConfig SET DisplayName=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,),
            db=self.db,
        )
        self.form_success = "Email display name saved."
        self.form_error = ""

    def set_email_address(self, v: str):
        self.email_address = v
        self.email_username = v
        run_exec(
            "UPDATE EmailConfig SET EmailAddress=?, Username=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v, v),
            db=self.db,
        )
        self._refresh_email_configured()
        self.form_success = "Email address saved."
        self.form_error = ""

    def set_email_imap_server(self, v: str):
        self.email_imap_server = v
        run_exec(
            "UPDATE EmailConfig SET IMAPServer=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,),
            db=self.db,
        )
        self.form_success = "IMAP server saved."
        self.form_error = ""

    def set_email_imap_port(self, v):
        try:
            port = int(v)
            self.email_imap_port = port
            run_exec(
                "UPDATE EmailConfig SET IMAPPort=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (port,),
                db=self.db,
            )
            self.form_success = "IMAP port saved."
            self.form_error = ""
        except (TypeError, ValueError):
            self.form_error = "IMAP port must be a number."
            self.form_success = ""

    def set_email_smtp_server(self, v: str):
        self.email_smtp_server = v
        run_exec(
            "UPDATE EmailConfig SET SMTPServer=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,),
            db=self.db,
        )
        self.form_success = "SMTP server saved."
        self.form_error = ""

    def set_email_smtp_port(self, v):
        try:
            port = int(v)
            self.email_smtp_port = port
            run_exec(
                "UPDATE EmailConfig SET SMTPPort=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (port,),
                db=self.db,
            )
            self.form_success = "SMTP port saved."
            self.form_error = ""
        except (TypeError, ValueError):
            self.form_error = "SMTP port must be a number."
            self.form_success = ""

    def set_email_poll_interval(self, v):
        try:
            interval = int(v)
            self.email_poll_interval = interval
            run_exec(
                "UPDATE EmailConfig SET PollIntervalMin=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (interval,),
                db=self.db,
            )
            self.form_success = "Email poll interval saved."
            self.form_error = ""
        except (TypeError, ValueError):
            self.form_error = "Poll interval must be a number."
            self.form_success = ""

    def set_email_password(self, v: str):
        self.email_password = v

    def save_email_password(self):
        if not self.email_password:
            return
        try:
            encrypted = encrypt_value(self.email_password, self.db)
            run_exec(
                "UPDATE EmailConfig SET PasswordEncrypted=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (encrypted,),
                db=self.db,
            )
            self.email_password = ""
            self._refresh_email_configured()
            self.form_success = "Email password saved."
            self.form_error = ""
        except Exception as e:
            self.form_error = f"Email password save failed: {str(e)}"
            self.form_success = ""

    def set_ai_api_key(self, v: str):
        self.ai_api_key = v

    def save_ai_api_key(self):
        if not self.ai_api_key:
            return
        try:
            encrypted = encrypt_value(self.ai_api_key, self.db)
            run_exec(
                "UPDATE AIConfig SET APIKeyEncrypted=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (encrypted,),
                db=self.db,
            )
            self.ai_api_key = ""
            self.ai_configured = True
            self.form_success = "AI API key saved."
            self.form_error = ""
        except Exception as e:
            self.form_error = f"AI API key save failed: {str(e)}"
            self.form_success = ""

    def set_ai_model(self, v: str):
        self.ai_model = v
        run_exec(
            "UPDATE AIConfig SET ModelName=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,),
            db=self.db,
        )
        self.form_success = "AI model saved."
        self.form_error = ""

    def _refresh_email_configured(self):
        rows = run_query(
            "SELECT TOP 1 EmailAddress, PasswordEncrypted FROM EmailConfig WHERE IsActive=1",
            db=self.db,
        )
        self.email_configured = bool(
            rows and rows[0].get("EmailAddress") and rows[0].get("PasswordEncrypted")
        )

    def test_email_connection(self):
        import imaplib
        import smtplib

        results = []
        self.email_test_result = ""
        self.form_error = ""
        self.form_success = ""

        pw_rows = run_query(
            "SELECT TOP 1 PasswordEncrypted FROM EmailConfig WHERE IsActive=1",
            db=self.db,
        )
        if not pw_rows or not pw_rows[0].get("PasswordEncrypted"):
            self.email_test_result = "No password saved. Save password first."
            return

        try:
            pw = decrypt_value(pw_rows[0]["PasswordEncrypted"], self.db)
        except Exception as e:
            self.email_test_result = f"Password decrypt failed: {str(e)}"
            return

        try:
            imap = imaplib.IMAP4_SSL(self.email_imap_server, self.email_imap_port)
            imap.login(self.email_username or self.email_address, pw)
            imap.logout()
            results.append("IMAP connected")
        except Exception as e:
            results.append(f"IMAP failed: {str(e)}")

        try:
            smtp = smtplib.SMTP(self.email_smtp_server, self.email_smtp_port, timeout=20)
            smtp.starttls()
            smtp.login(self.email_username or self.email_address, pw)
            smtp.quit()
            results.append("SMTP connected")
        except Exception as e:
            results.append(f"SMTP failed: {str(e)}")

        self.email_test_result = " | ".join(results)

    def test_ai_connection(self):
        self.ai_test_result = ""
        self.form_error = ""
        self.form_success = ""
        try:
            import anthropic

            key_rows = run_query(
                "SELECT TOP 1 APIKeyEncrypted FROM AIConfig WHERE IsActive=1",
                db=self.db,
            )
            if not key_rows or not key_rows[0].get("APIKeyEncrypted"):
                self.ai_test_result = "No API key saved. Save key first."
                return
            key = decrypt_value(key_rows[0]["APIKeyEncrypted"], self.db)
            client = anthropic.Anthropic(api_key=key)
            client.messages.create(
                model=self.ai_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            self.ai_test_result = "Anthropic API connected"
        except Exception as e:
            self.ai_test_result = f"API failed: {str(e)}"


def settings_content() -> rx.Component:
    return rx.box(
        rx.vstack(
        rx.heading("Settings", size="6", color=BRAND_DARK),
        rx.text("Global preferences for Lucid Property Manager.", size="2", color="#555"),
        rx.cond(
            SettingsState.form_error != "",
            rx.callout.root(rx.callout.text(SettingsState.form_error), color_scheme="red", width="100%"),
        ),
        rx.cond(
            SettingsState.form_success != "",
            rx.callout.root(rx.callout.text(SettingsState.form_success), color_scheme="green", width="100%"),
        ),
        rx.box(
            rx.vstack(
                rx.text("Developer Options", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Keep these off for normal workflows. Turn them on only when testing local files or developer-only utilities.",
                    size="2",
                    color="#666",
                ),
                rx.hstack(
                    rx.checkbox(
                        "Enable local test import tools",
                        checked=SettingsState.enable_developer_tools,
                        on_change=SettingsState.set_enable_developer_tools,
                    ),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%", "min_width": "100%", "max_width": "100%", "box_sizing": "border-box"},
        ),
        rx.box(
            rx.vstack(
                rx.text("Email Configuration", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Configure the dedicated property management mailbox. Used for sending and receiving tenant communications.",
                    size="2",
                    color="#666",
                ),
                rx.cond(
                    SettingsState.email_configured,
                    rx.callout.root(
                        rx.callout.text("Email configured"),
                        color_scheme="green",
                        width="100%",
                    ),
                    rx.callout.root(
                        rx.callout.text("Email not yet configured"),
                        color_scheme="amber",
                        width="100%",
                    ),
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Display Name", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_display_name,
                            on_change=SettingsState.set_email_display_name,
                            placeholder="Lucido Properties",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Email Address", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_address,
                            on_change=SettingsState.set_email_address,
                            placeholder="propmgmt@lucidoproperties.net",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    width="100%",
                    spacing="4",
                    flex_wrap="wrap",
                    gap="12px",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("IMAP Server", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_imap_server,
                            on_change=SettingsState.set_email_imap_server,
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("IMAP Port", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_imap_port.to_string(),
                            on_change=SettingsState.set_email_imap_port,
                            width="100%",
                        ),
                        width="120px",
                    ),
                    rx.vstack(
                        rx.text("SMTP Server", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_smtp_server,
                            on_change=SettingsState.set_email_smtp_server,
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("SMTP Port", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_smtp_port.to_string(),
                            on_change=SettingsState.set_email_smtp_port,
                            width="100%",
                        ),
                        width="120px",
                    ),
                    width="100%",
                    spacing="4",
                    flex_wrap="wrap",
                    gap="12px",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Password", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_password,
                            on_change=SettingsState.set_email_password,
                            on_blur=SettingsState.save_email_password,
                            placeholder="Enter password to update",
                            type="password",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Poll Interval (minutes)", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.email_poll_interval.to_string(),
                            on_change=SettingsState.set_email_poll_interval,
                            width="100%",
                        ),
                        width="180px",
                    ),
                    width="100%",
                    spacing="4",
                    flex_wrap="wrap",
                    gap="12px",
                ),
                rx.hstack(
                    rx.button(
                        "Test Connection",
                        on_click=SettingsState.test_email_connection,
                        variant="outline",
                        color_scheme="blue",
                    ),
                    rx.cond(
                        SettingsState.email_test_result != "",
                        rx.text(SettingsState.email_test_result, size="2"),
                    ),
                    align="center",
                    spacing="3",
                    flex_wrap="wrap",
                    gap="8px",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%", "min_width": "100%", "max_width": "100%", "box_sizing": "border-box"},
        ),
        rx.box(
            rx.vstack(
                rx.text("AI Configuration", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Anthropic API key for AI-powered features including thread summarization. Billed directly by Anthropic based on usage.",
                    size="2",
                    color="#666",
                ),
                rx.cond(
                    SettingsState.ai_configured,
                    rx.callout.root(
                        rx.callout.text("AI configured"),
                        color_scheme="green",
                        width="100%",
                    ),
                    rx.callout.root(
                        rx.callout.text("API key not yet configured"),
                        color_scheme="amber",
                        width="100%",
                    ),
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Anthropic API Key", size="2", color="#555"),
                        rx.input(
                            value=SettingsState.ai_api_key,
                            on_change=SettingsState.set_ai_api_key,
                            on_blur=SettingsState.save_ai_api_key,
                            placeholder="Enter API key to update",
                            type="password",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Model", size="2", color="#555"),
                        rx.select(
                            ["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
                            value=SettingsState.ai_model,
                            on_change=SettingsState.set_ai_model,
                        ),
                        width="280px",
                    ),
                    width="100%",
                    spacing="4",
                    align="end",
                    flex_wrap="wrap",
                    gap="12px",
                ),
                rx.hstack(
                    rx.button(
                        "Test Connection",
                        on_click=SettingsState.test_ai_connection,
                        variant="outline",
                        color_scheme="blue",
                    ),
                    rx.cond(
                        SettingsState.ai_test_result != "",
                        rx.text(SettingsState.ai_test_result, size="2"),
                    ),
                    align="center",
                    spacing="3",
                    flex_wrap="wrap",
                    gap="8px",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%", "min_width": "100%", "max_width": "100%", "box_sizing": "border-box"},
        ),
            spacing="4",
            width="100%",
            min_width="100%",
            max_width="100%",
            align_items="stretch",
            style={"box_sizing": "border-box"},
        ),
        padding="0",
        width=FULL_PAGE_WIDTH,
        min_width=FULL_PAGE_WIDTH,
        max_width=FULL_PAGE_WIDTH,
        flex_shrink="0",
        style={
            "box_sizing": "border-box",
            "overflow_x": "hidden",
            "display": "block",
        },
    )


def settings_page() -> rx.Component:
    return page_shell(settings_content(), current_path="/admin/settings")
