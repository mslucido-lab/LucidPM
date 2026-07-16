"""Admin Settings page."""
from __future__ import annotations
import reflex as rx
from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT

class AdminSettingsState(AppState):
    storage_root: str = DEFAULT_DOCUMENT_ROOT
    original_storage_root: str = DEFAULT_DOCUMENT_ROOT
    developer_tools_enabled: bool = False
    form_error: str = ""
    form_success: str = ""

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
        self._load_settings()

    def set_storage_root(self, v: str): self.storage_root = v
    def set_developer_tools_enabled(self, v: bool): self.developer_tools_enabled = v

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
        rx.hstack(
            rx.button("Save Settings", on_click=AdminSettingsState.save_settings, color_scheme="blue"),
            rx.button("Reset", on_click=AdminSettingsState.reset_settings, variant="soft", color_scheme="gray"),
            spacing="3",
        ),
        spacing="4", width="100%",
    )

def admin_settings_page() -> rx.Component:
    return page_shell(admin_settings_content(), current_path="/admin/settings")
