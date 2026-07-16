"""Admin Settings page.

Version: v1.2.2
Refactors encryption helpers to shared utilities in state.py.
Adds EmailConfig and AIConfig settings cards.
"""
from __future__ import annotations

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, encrypt_value, decrypt_value, send_email
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT


class AdminSettingsState(AppState):
    storage_root: str = DEFAULT_DOCUMENT_ROOT
    original_storage_root: str = DEFAULT_DOCUMENT_ROOT
    developer_tools_enabled: bool = False
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
    ai_model: str = "claude-sonnet-4-6"
    ai_configured: bool = False

    # Connection test feedback
    email_test_result: str = ""
    ai_test_result: str = ""

    @rx.var
    def storage_root_changed(self) -> bool:
        return str(self.storage_root or "").strip() != str(self.original_storage_root or "").strip()

    def on_load(self):
        self.form_error = ""
        self.form_success = ""
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
        run_exec("""
        IF OBJECT_ID('dbo.AppSettings', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.AppSettings (
                SettingKey NVARCHAR(100) NOT NULL PRIMARY KEY,
                SettingValue NVARCHAR(1000) NULL,
                UpdatedOn DATETIME2 NOT NULL CONSTRAINT DF_AppSettings_UpdatedOn DEFAULT (SYSDATETIME())
            );
        END
        """, db=self.db)
        run_exec("""
        IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'EnableDeveloperTools')
        BEGIN
            INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
            VALUES ('EnableDeveloperTools', '0', SYSDATETIME());
        END
        """, db=self.db)
        run_exec("""
        IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'LeaseDocumentStorageRoot')
        BEGIN
            INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
            VALUES ('LeaseDocumentStorageRoot', ?, SYSDATETIME());
        END
        """, (DEFAULT_DOCUMENT_ROOT,), db=self.db)
        run_exec("""
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
        """, db=self.db)
        run_exec("""
        IF OBJECT_ID('dbo.AIConfig', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.AIConfig (
                AIConfigID         INT IDENTITY(1,1) PRIMARY KEY,
                APIKeyEncrypted    NVARCHAR(500)  NULL,
                ModelName          NVARCHAR(100)  NOT NULL DEFAULT 'claude-sonnet-4-6',
                IsActive           BIT            NOT NULL DEFAULT 1,
                CreatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
                UpdatedOn          DATETIME2      NOT NULL DEFAULT SYSDATETIME()
            );
            INSERT INTO dbo.AIConfig (ModelName)
            VALUES ('claude-sonnet-4-6');
        END
        """, db=self.db)

    def _load_settings(self):
        rows = run_query(
            "SELECT SettingKey, SettingValue FROM dbo.AppSettings WHERE SettingKey IN ('EnableDeveloperTools', 'LeaseDocumentStorageRoot')",
            db=self.db,
        )
        settings = {str(r.get("SettingKey") or ""): str(r.get("SettingValue") or "") for r in rows}
        root = settings.get("LeaseDocumentStorageRoot", "").strip() or DEFAULT_DOCUMENT_ROOT
        self.storage_root = root
        self.original_storage_root = root
        self.developer_tools_enabled = settings.get("EnableDeveloperTools", "0").strip() in ("1", "true", "True", "yes", "Yes")

        email_rows = run_query(
            "SELECT TOP 1 DisplayName, EmailAddress, IMAPServer, IMAPPort, "
            "SMTPServer, SMTPPort, Username, PasswordEncrypted, PollIntervalMin "
            "FROM dbo.EmailConfig WHERE IsActive = 1",
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

        ai_rows = run_query(
            "SELECT TOP 1 APIKeyEncrypted, ModelName FROM dbo.AIConfig WHERE IsActive = 1",
            db=self.db,
        )
        if ai_rows:
            r = ai_rows[0]
            self.ai_api_key = ""
            self.ai_model = str(r.get("ModelName") or "claude-sonnet-4-6")
            self.ai_configured = bool(r.get("APIKeyEncrypted"))

    def _upsert_setting(self, key: str, value: str):
        run_exec("""
        MERGE dbo.AppSettings AS target
        USING (SELECT ? AS SettingKey, ? AS SettingValue) AS src
        ON target.SettingKey = src.SettingKey
        WHEN MATCHED THEN
            UPDATE SET SettingValue = src.SettingValue, UpdatedOn = SYSDATETIME()
        WHEN NOT MATCHED THEN
            INSERT (SettingKey, SettingValue, UpdatedOn)
            VALUES (src.SettingKey, src.SettingValue, SYSDATETIME());
        """, (key, value), db=self.db)

    def save_settings(self):
        self.form_error = ""
        self.form_success = ""
        root = str(self.storage_root or "").strip()
        if not root:
            self.form_error = "Lease document storage root is required."
            return
        try:
            self._ensure_schema()
            self._upsert_setting("LeaseDocumentStorageRoot", root)
            self._upsert_setting("EnableDeveloperTools", "1" if self.developer_tools_enabled else "0")
            self.original_storage_root = root
            self.form_success = "Settings saved. Reload Lease Documents to use updated settings."
        except Exception as ex:
            self.form_error = f"Could not save settings: {ex}"

    def reset_settings(self):
        self.form_error = ""
        self.form_success = ""
        self.email_test_result = ""
        self.ai_test_result = ""
        self._load_settings()

    def set_storage_root(self, v: str): self.storage_root = v
    def set_developer_tools_enabled(self, v: bool): self.developer_tools_enabled = v

    def set_email_display_name(self, v: str):
        self.email_display_name = v
        run_exec(
            "UPDATE dbo.EmailConfig SET DisplayName=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,), db=self.db,
        )

    def set_email_address(self, v: str):
        self.email_address = v
        self.email_username = v
        run_exec(
            "UPDATE dbo.EmailConfig SET EmailAddress=?, Username=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v, v), db=self.db,
        )
        self.email_configured = False

    def set_email_imap_server(self, v: str):
        self.email_imap_server = v
        run_exec(
            "UPDATE dbo.EmailConfig SET IMAPServer=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,), db=self.db,
        )

    def set_email_imap_port(self, v):
        try:
            port = int(v)
            self.email_imap_port = port
            run_exec(
                "UPDATE dbo.EmailConfig SET IMAPPort=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (port,), db=self.db,
            )
        except (TypeError, ValueError):
            pass

    def set_email_smtp_server(self, v: str):
        self.email_smtp_server = v
        run_exec(
            "UPDATE dbo.EmailConfig SET SMTPServer=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,), db=self.db,
        )

    def set_email_smtp_port(self, v):
        try:
            port = int(v)
            self.email_smtp_port = port
            run_exec(
                "UPDATE dbo.EmailConfig SET SMTPPort=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (port,), db=self.db,
            )
        except (TypeError, ValueError):
            pass

    def set_email_poll_interval(self, v):
        try:
            interval = int(v)
            self.email_poll_interval = interval
            run_exec(
                "UPDATE dbo.EmailConfig SET PollIntervalMin=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (interval,), db=self.db,
            )
        except (TypeError, ValueError):
            pass

    def set_email_password(self, v: str):
        self.email_password = v

    def save_email_password(self):
        self.form_error = ""
        self.form_success = ""
        if not self.email_password:
            return
        try:
            encrypted = encrypt_value(self.email_password, self.db)
            run_exec(
                "UPDATE dbo.EmailConfig SET PasswordEncrypted=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (encrypted,), db=self.db,
            )
            self.email_configured = bool(self.email_address and encrypted)
            self.email_password = ""
            self.form_success = "Email password saved."
        except Exception as ex:
            self.form_error = f"Could not save email password: {ex}"

    def set_ai_api_key(self, v: str):
        self.ai_api_key = v

    def save_ai_api_key(self):
        self.form_error = ""
        self.form_success = ""
        if not self.ai_api_key:
            return
        try:
            encrypted = encrypt_value(self.ai_api_key, self.db)
            run_exec(
                "UPDATE dbo.AIConfig SET APIKeyEncrypted=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
                (encrypted,), db=self.db,
            )
            self.ai_configured = True
            self.ai_api_key = ""
            self.form_success = "AI API key saved."
        except Exception as ex:
            self.form_error = f"Could not save AI API key: {ex}"

    def set_ai_model(self, v: str):
        self.ai_model = v
        run_exec(
            "UPDATE dbo.AIConfig SET ModelName=?, UpdatedOn=SYSDATETIME() WHERE IsActive=1",
            (v,), db=self.db,
        )

    def test_email_connection(self):
        import imaplib

        results = []
        self.email_test_result = ""

        try:
            pw_rows = run_query(
                "SELECT TOP 1 PasswordEncrypted FROM dbo.EmailConfig WHERE IsActive=1",
                db=self.db,
            )
            if not pw_rows or not pw_rows[0].get("PasswordEncrypted"):
                self.email_test_result = "No password saved. Save password first."
                return
            pw = decrypt_value(str(pw_rows[0]["PasswordEncrypted"]), self.db)
        except Exception as ex:
            self.email_test_result = f"Could not read saved password: {ex}"
            return

        username = (self.email_username or self.email_address or "").strip()
        imap_server = str(self.email_imap_server or "").strip()
        imap_port = int(self.email_imap_port or 143)

        def _try_imap_plain(host: str, port: int):
            imap = imaplib.IMAP4(host, port)
            imap.login(username, pw)
            imap.logout()

        def _try_imap_ssl(host: str, port: int):
            imap = imaplib.IMAP4_SSL(host, port)
            imap.login(username, pw)
            imap.logout()

        def _try_imap_starttls(host: str, port: int):
            imap = imaplib.IMAP4(host, port)
            imap.starttls()
            imap.login(username, pw)
            imap.logout()

        imap_errors = []
        try:
            if imap_port == 993:
                _try_imap_ssl(imap_server, imap_port)
            else:
                try:
                    _try_imap_plain(imap_server, imap_port)
                except Exception as ex_plain:
                    imap_errors.append(f"plain {imap_port}: {type(ex_plain).__name__}: {ex_plain}")
                    _try_imap_starttls(imap_server, imap_port)
            results.append("IMAP connected")
        except Exception as ex:
            imap_errors.append(f"configured {imap_port}: {type(ex).__name__}: {ex}")
            # Outlook uses IMAP Auto and often lands on 143 for this mailbox.
            # If the configured port fails, try 143 plain as a compatibility fallback.
            if imap_port != 143:
                try:
                    _try_imap_plain(imap_server, 143)
                    results.append("IMAP connected on 143")
                except Exception as ex_143:
                    imap_errors.append(f"fallback 143: {type(ex_143).__name__}: {ex_143}")
                    results.append("IMAP failed: " + " | ".join(imap_errors))
            else:
                results.append("IMAP failed: " + " | ".join(imap_errors))

        try:
            if not self.email_address.strip():
                results.append("SMTP failed: email address is required for test send")
            else:
                send_email(
                    to_address=self.email_address.strip(),
                    subject="LucidPM Email Configuration Test",
                    body=(
                        "This is a Lucid Property Manager email configuration test.\n\n"
                        "If you received this message, outbound SMTP sending is working."
                    ),
                    db=self.db,
                )
                results.append(f"SMTP test email sent to {self.email_address.strip()}")
        except Exception as ex:
            results.append(f"SMTP failed: {ex}")

        self.email_test_result = " | ".join(results)

    def test_ai_connection(self):
        try:
            import anthropic

            key_rows = run_query(
                "SELECT TOP 1 APIKeyEncrypted FROM dbo.AIConfig WHERE IsActive=1",
                db=self.db,
            )
            if not key_rows or not key_rows[0].get("APIKeyEncrypted"):
                self.ai_test_result = "No API key saved. Save key first."
                return
            key = decrypt_value(str(key_rows[0]["APIKeyEncrypted"]), self.db)
            client = anthropic.Anthropic(api_key=key)
            client.messages.create(
                model=self.ai_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            self.ai_test_result = "Anthropic API connected"
        except Exception as ex:
            self.ai_test_result = f"API failed: {ex}"


def admin_settings_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Admin Settings", size="6", color=BRAND_DARK),
        rx.text("Deployment-level settings for Lucid Property Manager.", size="2", color="#555"),
        rx.cond(AdminSettingsState.form_error != "", rx.callout.root(rx.callout.text(AdminSettingsState.form_error), color_scheme="red", width="100%")),
        rx.cond(AdminSettingsState.form_success != "", rx.callout.root(rx.callout.text(AdminSettingsState.form_success), color_scheme="green", width="100%")),
        rx.card(rx.vstack(
            rx.text("Lease document storage", size="4", weight="bold", color=BRAND_DARK),
            rx.text("Root folder used for uploaded lease PDFs, split sections, and generated packages.", size="2", color="#666"),
            rx.vstack(
                rx.text("Lease document storage root", size="1", color="#666"),
                rx.input(value=AdminSettingsState.storage_root, on_change=AdminSettingsState.set_storage_root, placeholder=DEFAULT_DOCUMENT_ROOT, width="100%"),
                spacing="1", width="100%",
            ),
            rx.cond(AdminSettingsState.storage_root_changed, rx.callout.root(rx.callout.text("Changing this path does not move existing files. Move existing files manually or old StoredFilePath references may break."), color_scheme="orange", width="100%")),
            spacing="3", width="100%", align_items="start",
        ), width="100%"),
        rx.card(rx.vstack(
            rx.text("Developer tools", size="4", weight="bold", color=BRAND_DARK),
            rx.checkbox("Enable developer-only local PDF import tools", checked=AdminSettingsState.developer_tools_enabled, on_change=AdminSettingsState.set_developer_tools_enabled),
            rx.text("When enabled, Lease Documents shows the local path import helper for testing.", size="2", color="#666"),
            spacing="3", width="100%", align_items="start",
        ), width="100%"),
        rx.card(
            rx.vstack(
                rx.text("Email Configuration", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Configure the dedicated property management mailbox. Used for sending and receiving tenant communications.",
                    size="2", color="#666",
                ),
                rx.cond(
                    AdminSettingsState.email_configured,
                    rx.callout.root(rx.callout.text("Email configured"), color_scheme="green", width="100%"),
                    rx.callout.root(rx.callout.text("Email not yet configured"), color_scheme="amber", width="100%"),
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Display Name", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_display_name, on_change=AdminSettingsState.set_email_display_name, placeholder="Lucido Properties", width="100%"),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Email Address", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_address, on_change=AdminSettingsState.set_email_address, placeholder="propmgmt@lucidoproperties.net", width="100%"),
                        width="100%",
                    ),
                    width="100%", spacing="4",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("IMAP Server", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_imap_server, on_change=AdminSettingsState.set_email_imap_server, width="100%"),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("IMAP Port", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_imap_port.to_string(), on_change=AdminSettingsState.set_email_imap_port, width="100%"),
                        width="90px",
                    ),
                    rx.vstack(
                        rx.text("SMTP Server", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_smtp_server, on_change=AdminSettingsState.set_email_smtp_server, width="100%"),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("SMTP Port", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_smtp_port.to_string(), on_change=AdminSettingsState.set_email_smtp_port, width="100%"),
                        width="90px",
                    ),
                    width="100%", spacing="4",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Password", size="2", color="#555"),
                        rx.input(
                            value=AdminSettingsState.email_password,
                            on_change=AdminSettingsState.set_email_password,
                            on_blur=AdminSettingsState.save_email_password,
                            placeholder="Enter password to update",
                            type="password",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Poll Interval (minutes)", size="2", color="#555"),
                        rx.input(value=AdminSettingsState.email_poll_interval.to_string(), on_change=AdminSettingsState.set_email_poll_interval, width="100%"),
                        width="180px",
                    ),
                    width="100%", spacing="4",
                ),
                rx.hstack(
                    rx.button("Test Connection", on_click=AdminSettingsState.test_email_connection, variant="outline", color_scheme="blue"),
                    rx.cond(AdminSettingsState.email_test_result != "", rx.text(AdminSettingsState.email_test_result, size="2")),
                    align="center", spacing="3",
                ),
                spacing="3", width="100%", align_items="start",
            ),
            width="100%",
        ),
        rx.card(
            rx.vstack(
                rx.text("AI Configuration", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Anthropic API key for AI-powered features including thread summarization. Billed directly by Anthropic based on usage.",
                    size="2", color="#666",
                ),
                rx.cond(
                    AdminSettingsState.ai_configured,
                    rx.callout.root(rx.callout.text("AI configured"), color_scheme="green", width="100%"),
                    rx.callout.root(rx.callout.text("API key not yet configured"), color_scheme="amber", width="100%"),
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Anthropic API Key", size="2", color="#555"),
                        rx.input(
                            value=AdminSettingsState.ai_api_key,
                            on_change=AdminSettingsState.set_ai_api_key,
                            on_blur=AdminSettingsState.save_ai_api_key,
                            placeholder="Enter API key to update",
                            type="password",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Model", size="2", color="#555"),
                        rx.select(
                            ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
                            value=AdminSettingsState.ai_model,
                            on_change=AdminSettingsState.set_ai_model,
                            width="100%",
                        ),
                        width="290px",
                    ),
                    width="100%", spacing="4", align="end",
                ),
                rx.hstack(
                    rx.button("Test Connection", on_click=AdminSettingsState.test_ai_connection, variant="outline", color_scheme="blue"),
                    rx.cond(AdminSettingsState.ai_test_result != "", rx.text(AdminSettingsState.ai_test_result, size="2")),
                    align="center", spacing="3",
                ),
                spacing="3", width="100%", align_items="start",
            ),
            width="100%",
        ),
        rx.hstack(
            rx.button("Save Settings", on_click=AdminSettingsState.save_settings, color_scheme="blue"),
            rx.button("Reset", on_click=AdminSettingsState.reset_settings, variant="soft", color_scheme="gray"),
            spacing="3",
        ),
        spacing="4", width="100%",
    )


def admin_settings_page() -> rx.Component:
    return page_shell(admin_settings_content(), current_path="/admin/settings")
