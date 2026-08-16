"""
Admin Settings page.

Stores simple app-level preferences in dbo.AppSettings.
"""

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK
from LucidPM_Reflex.components.sidebar import page_shell


class SettingsState(AppState):
    enable_developer_tools: bool = False
    form_error: str = ""
    form_success: str = ""

    def on_load(self):
        self._ensure_schema()
        self._load_settings()

    def reload_on_db_change(self):
        self.form_error = ""
        self.form_success = ""
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

    def _load_settings(self):
        rows = run_query(
            "SELECT SettingValue FROM AppSettings WHERE SettingKey = 'EnableDeveloperTools'",
            db=self.db,
        )
        self.enable_developer_tools = bool(
            rows and str(rows[0].get("SettingValue") or "0").strip() in ("1", "true", "True", "yes", "Yes")
        )

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


def settings_content() -> rx.Component:
    return rx.vstack(
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
        rx.card(
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
        ),
        spacing="4",
        width="100%",
    )


def settings_page() -> rx.Component:
    return page_shell(settings_content(), current_path="/admin/settings")
